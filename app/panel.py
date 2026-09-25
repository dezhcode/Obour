"""لایه اتصال به پنل PasarGuard (احراز هویت با API Key).

دو اصل مهم این لایه:

۱) بدون وابستگی به User Template
   همه سرویس ها با create_user ساخته می شوند و حجم/مدت/گروه مستقیم
   فرستاده می شود. پس نیازی به دسترسی ساخت قالب در پنل نیست.

۲) تفکیک خطای امن از مبهم (حیاتی برای پول کاربر)
   PanelSafeError  : مطمئنیم درخواست به پنل نرسید یا رد شد. چیزی ساخته نشده.
                     -> امن است که تراکنش لغو و پول برگردانده شود.
   PanelAmbiguous  : ممکن است درخواست رسیده و کاربر ساخته شده باشد ولی
                     پاسخ گم شده. هرگز کورکورانه برنگردان، اول تایید بگیر.
"""
from __future__ import annotations

import inspect
import logging

import httpx
from pasarguard import (
    PasarguardAPI,
    Tools,
    UserCreate,
    UserModify,
    UserResponse,
    UserStatus,
)

from .config import Config
from .utils import GIB

log = logging.getLogger("obour.panel")

# کدهایی که یعنی پنل درخواست را دریافت و آگاهانه رد کرده (چیزی ساخته نشده)
_REJECT_CODES = (400, 401, 403, 404, 422)


class PanelError(Exception):
    """خطای پایه پنل."""


class PanelSafeError(PanelError):
    """قطعا چیزی روی پنل ساخته/تغییر نکرد. بازگشت پول امن است."""


class PanelAmbiguous(PanelError):
    """شاید ساخته شده باشد. قبل از بازگشت پول باید وضعیت را تایید کرد."""


class PanelNameTaken(PanelSafeError):
    """نام سرویس روی پنل از قبل وجود دارد (409).

    این خطا حتما امن است: پنل چیزی نساخته، فقط گفته این اسم گرفته شده.
    صدازننده باید با نام دیگری دوباره تلاش کند - نه اینکه سرویس موجود
    را تحویل کاربر بدهد.
    """


class Panel:
    def __init__(self, cfg: Config) -> None:
        if not cfg.panel_base_url:
            raise PanelSafeError("PANEL_BASE_URL تنظیم نشده است")
        self.base_url = cfg.panel_base_url
        # اگر group_id تنظیم نشده باشد یا all باشد، همه گروه های پنل استفاده می شوند
        self._group_id = cfg.panel_group_id
        self._all_groups = cfg.panel_group_all
        self._groups_cache: list[int] | None = None
        # اندپوینت هایی که یک بار 403/404 داده اند - دیگر امتحان نمی شوند
        self._dead_endpoints: set[str] = set()
        # احراز هویت: SDK رسمی با Bearer token کار می کند (get_token با یوزر/پسورد).
        # بعضی بیلدها api_key هم می پذیرند. هر دو حالت پشتیبانی می شود.
        self._username = cfg.panel_username
        self._password = cfg.panel_password
        self._api_key = cfg.panel_api_key or ""
        self._token: str | None = None

        kwargs = {
            "base_url": cfg.panel_base_url,
            "verify": cfg.panel_verify_ssl,
            "timeout": cfg.panel_timeout,
        }
        if self._api_key and "api_key" in inspect.signature(PasarguardAPI).parameters:
            kwargs["api_key"] = self._api_key
            self._native_key = True
        else:
            self._native_key = False
        self._api = PasarguardAPI(**kwargs)
        # اگر SDK از api_key پشتیبانی نکند، هدر را دستی روی کلاینت می گذاریم
        if self._api_key and not self._native_key:
            try:
                self._api.client.headers["X-API-Key"] = self._api_key
            except Exception:  # noqa: BLE001
                log.warning("نتوانستیم هدر X-API-Key را روی کلاینت SDK بگذاریم")
        self._http = httpx.AsyncClient(
            base_url=cfg.panel_base_url,
            verify=cfg.panel_verify_ssl,
            timeout=cfg.panel_timeout,
        )

    async def _auth(self) -> dict:
        """آرگومان احراز هویت برای متدهای SDK.

        اگر یوزر/پسورد داده شده باشد، Bearer token گرفته و کش می شود.
        اگر فقط API Key باشد، هدر از قبل ست شده و آرگومانی لازم نیست.
        """
        if self._native_key or not (self._username and self._password):
            return {}
        if self._token is None:
            try:
                tok = await self._api.get_token(
                    username=self._username, password=self._password
                )
                self._token = getattr(tok, "access_token", None) or str(tok)
            except Exception as exc:  # noqa: BLE001
                raise PanelSafeError(f"ورود به پنل ناموفق بود: {exc}") from exc
        return {"token": self._token}

    async def _http_headers(self) -> dict:
        """هدر احراز هویت برای درخواست های مستقیم HTTP."""
        if self._api_key:
            return {"X-API-Key": self._api_key}
        auth = await self._auth()
        if auth.get("token"):
            return {"Authorization": f"Bearer {auth['token']}"}
        return {}

    async def close(self) -> None:
        await self._http.aclose()
        await self._api.close()

    # ---------- طبقه بندی خطا ----------
    @staticmethod
    def _classify_write(exc: Exception, action: str) -> PanelError:
        """خطای عملیات نوشتن را به امن یا مبهم تبدیل می کند."""
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            if code == 409:
                # نام تکراری. قبلا مبهم حساب می شد و چون get_user بعدی
                # کاربرِ *از قبل موجود* را پیدا می کرد، ربات آن را به
                # عنوان سرویس تازه تحویل می داد و پول هم می گرفت.
                return PanelNameTaken(f"نام روی پنل گرفته شده است ({action})")
            if code in _REJECT_CODES:
                return PanelSafeError(f"پنل درخواست را رد کرد ({action}: {code})")
            return PanelAmbiguous(f"پاسخ نامشخص از پنل ({action}: {code})")
        return PanelAmbiguous(f"ارتباط با پنل نامشخص ({action}: {type(exc).__name__})")

    # ---------- گروه ها ----------
    @property
    def uses_all_groups(self) -> bool:
        """آیا ربات از همه گروه های پنل استفاده می کند؟"""
        return self._all_groups

    async def fetch_group_ids(self, force: bool = False) -> list[int]:
        """آیدی گروه هایی که سرویس با آن ها ساخته می شود.

        اگر PANEL_GROUP_ID عددی باشد -> فقط همان.
        اگر all یا خالی باشد -> همه گروه های موجود پنل (با کش).
        """
        if not self._all_groups and self._group_id:
            return [self._group_id]

        if self._groups_cache is not None and not force:
            return self._groups_cache

        ids = await self._read_all_groups()
        if not ids:
            raise PanelSafeError(
                "هیچ گروهی در پنل پیدا نشد. PANEL_GROUP_ID را دستی تنظیم کن."
            )
        self._groups_cache = ids
        log.info("گروه های پنل: %s", ids)
        return ids

    async def _read_all_groups(self) -> list[int]:
        """خواندن لیست گروه ها.

        ترتیب عمدی است: اندپوینت simple اول امتحان می شود چون با دسترسی
        اپراتور هم کار می کند. متد SDK و اندپوینت کامل نیاز به sudo دارند و
        اگر یک بار 403 بدهند دیگر امتحان نمی شوند (تا لاگ شلوغ نشود).
        """
        headers = await self._http_headers()
        for path in ("/api/groups/simple", "/api/groups"):
            if path in self._dead_endpoints:
                continue
            try:
                r = await self._http.get(path, headers=headers)
                if r.status_code in (401, 403, 404):
                    self._dead_endpoints.add(path)
                    log.info("اندپوینت %s دسترسی ندارد (%s) - دیگر امتحان نمی شود", path, r.status_code)
                    continue
                if r.status_code != 200:
                    continue
                ids = self._extract_ids(r.json())
                if ids:
                    return ids
            except Exception as exc:  # noqa: BLE001
                log.warning("خواندن گروه ها از %s ناموفق: %s", path, exc)

        # آخرین تلاش: متد رسمی SDK (نیاز به دسترسی sudo)
        fn = getattr(self._api, "get_all_groups", None)
        if fn is not None and "sdk" not in self._dead_endpoints:
            try:
                data = await fn(**await self._auth())
                ids = self._extract_ids(
                    data.model_dump(mode="json") if hasattr(data, "model_dump") else data
                )
                if ids:
                    return ids
            except Exception as exc:  # noqa: BLE001
                self._dead_endpoints.add("sdk")
                log.info("get_all_groups در دسترس نیست (%s) - دیگر امتحان نمی شود", exc)
        return []

    @staticmethod
    def _extract_ids(data) -> list[int]:
        """استخراج آیدی از پاسخ، چه لیست ساده باشد چه دیکشنری صفحه بندی شده."""
        items = data
        if isinstance(data, dict):
            for key in ("groups", "items", "data", "results"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
            else:
                items = []
        ids: list[int] = []
        for it in items or []:
            gid = it.get("id") if isinstance(it, dict) else it
            if isinstance(gid, int):
                ids.append(gid)
            elif isinstance(gid, str) and gid.isdigit():
                ids.append(int(gid))
        return ids

    # ---------- ساخت (بدون قالب) ----------
    async def username_taken(self, username: str) -> bool:
        """آیا این نام روی پنل وجود دارد؟

        اگر نتوانیم بفهمیم (پنل در دسترس نیست)، False برمی گردانیم تا
        جریان خرید متوقف نشود؛ در آن حالت خطای 409 موقع ساخت، کار را
        درست می کند.
        """
        try:
            return await self.get_user(username) is not None
        except Exception:  # noqa: BLE001
            log.warning("بررسی نام %s روی پنل ناموفق بود", username, exc_info=True)
            return False

    async def create_service(
        self, username: str, data_bytes: int, days: int, note: str = ""
    ) -> UserResponse:
        """ساخت سرویس با حجم و مدت دلخواه - بدون نیاز به User Template.

        برای هر دو حالت استفاده می شود: پلن آماده و ساخت دلخواه.
        """
        auth = await self._auth()

        # گروه ها را خودمان می خوانیم (با کش) و صریح می فرستیم.
        #
        # چرا create_user_in_all_groups مستقیم صدا زده نمی شود؟
        # آن متد در SDK قبل از هر ساخت یک درخواست get_groups_simple می زند.
        # یعنی هر خرید به دو درخواست وابسته می شد و اگر پنل لحظه ای بالا
        # نمی آمد، خطای 5xx روی همان خواندن گروه ها می خورد و به اشتباه
        # وضعیت مبهم می گرفت - در حالی که قطعا هیچ کاربری ساخته نشده بود.
        group_ids: list[int] | None = None
        try:
            group_ids = await self.fetch_group_ids()
        except PanelError:
            log.warning("خواندن گروه ها ناموفق بود، به create_user_in_all_groups برمی گردیم")

        if group_ids:
            try:
                return await self._api.create_user(
                    UserCreate(
                        username=username,
                        data_limit=data_bytes,
                        expire=Tools.days(days),
                        group_ids=group_ids,
                        status=UserStatus.ACTIVE,
                        note=note or None,
                    ),
                    **auth,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("create_user failed for %s: %s", username, exc)
                raise self._classify_write(exc, "create") from exc

        # مسیر پشتیبان: اگر اصلا نتوانستیم گروه ها را بخوانیم
        if self._all_groups:
            fn = getattr(self._api, "create_user_in_all_groups", None)
            if fn is not None:
                try:
                    return await fn(
                        UserCreate(
                            username=username,
                            data_limit=data_bytes,
                            expire=Tools.days(days),
                            status=UserStatus.ACTIVE,
                            note=note or None,
                        ),
                        **auth,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("create_user_in_all_groups failed for %s: %s", username, exc)
                    raise self._classify_write(exc, "create") from exc

        raise PanelSafeError("گروه های پنل خوانده نشدند و سرویس ساخته نشد")

    # ---------- خواندن ----------
    async def get_user(self, username: str) -> UserResponse | None:
        """خواندن کاربر. None یعنی وجود ندارد (۴۰۴)."""
        try:
            return await self._api.get_user(username, **await self._auth())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise PanelSafeError(f"خواندن کاربر ناموفق ({exc.response.status_code})") from exc
        except Exception as exc:  # noqa: BLE001
            raise PanelSafeError(f"خواندن کاربر ناموفق ({type(exc).__name__})") from exc

    async def exists(self, username: str) -> bool | None:
        """آیا کاربر روی پنل هست؟ None یعنی نتوانستیم بفهمیم."""
        try:
            return await self.get_user(username) is not None
        except PanelError:
            return None

    async def health(self) -> bool:
        try:
            return await self._api.get_system_stats(**await self._auth()) is not None
        except Exception:  # noqa: BLE001
            return False

    # ---------- تمدید ----------
    async def renew(self, username: str, data_bytes: int, days: int) -> UserResponse:
        """تمدید همان اکانت: حجم و انقضای جدید (لینک ساب ثابت می ماند)."""
        try:
            resp = await self._api.modify_user(
                username=username,
                user=UserModify(
                    data_limit=data_bytes,
                    expire=Tools.days(days),
                    status=UserStatus.ACTIVE,
                ),
                **await self._auth(),
            )
            # صفر کردن مصرف قبلی تا حجم تازه کامل در دسترس باشد
            await self._reset_usage(username)
            return resp
        except Exception as exc:  # noqa: BLE001
            log.warning("panel renew failed for %s: %s", username, exc)
            raise self._classify_write(exc, "renew") from exc

    async def _reset_usage(self, username: str) -> None:
        """صفر کردن مصرف کاربر.

        نام این متد بین نسخه های SDK فرق می کند و در مستندات عمومی نیامده،
        پس چند حالت امتحان و در نهایت درخواست مستقیم HTTP زده می شود.
        """
        for name in ("reset_user_data_usage", "reset_user_usage", "reset_usage"):
            fn = getattr(self._api, name, None)
            if fn is None:
                continue
            try:
                await fn(username, **await self._auth())
                return
            except TypeError:
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("reset usage (%s) ناموفق: %s", name, exc)
                return
        # حالت آخر: فراخوانی مستقیم اندپوینت
        try:
            r = await self._http.post(
                f"/api/user/{username}/reset", headers=await self._http_headers()
            )
            if r.status_code >= 400:
                log.warning("reset usage HTTP %s برای %s", r.status_code, username)
        except Exception as exc:  # noqa: BLE001
            log.warning("reset usage ناموفق برای %s: %s", username, exc)

    async def revert_renew(
        self, username: str, old_data_limit: int | None, old_expire
    ) -> bool:
        """برگشت تمدید. True یعنی مطمئنیم برگشت انجام شد."""
        try:
            await self._api.modify_user(
                username=username,
                user=UserModify(data_limit=old_data_limit, expire=old_expire),
                **await self._auth(),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("revert_renew failed for %s: %s", username, exc)
            return False

    # ---------- ابطال لینک اشتراک ----------
    async def revoke_sub(self, username: str) -> UserResponse | None:
        """لینک ساب قبلی را باطل و یک لینک تازه صادر می کند.

        در سورس پنل، سرویس مربوطه `revoke_user_sub(db, username, admin)`
        است و مسیر REST آن `POST /api/user/{username}/revoke_sub`.
        نسخه های تازه تر پنل مسیرهای مبتنی بر آیدی را ترجیح می دهند
        (`/api/user/by-id/{id}/...`) و مسیر مبتنی بر نام را منسوخ اعلام
        کرده اند، پس هر دو امتحان می شود.

        خروجی None یعنی هیچ راهی جواب نداد؛ در آن حالت صدازننده **نباید**
        لینک ذخیره شده را عوض کند، وگرنه لینک درست کاربر را با یک لینک
        بی اثر جایگزین می کنیم.
        """
        # ۱) اگر SDK متد آماده دارد، همان بهترین راه است
        for name in ("revoke_user_sub", "revoke_sub", "reset_user_sub"):
            fn = getattr(self._api, name, None)
            if fn is None:
                continue
            try:
                resp = await fn(username, **await self._auth())
                log.info("ابطال ساب %s با متد %s انجام شد", username, name)
                return resp
            except TypeError:
                continue  # امضای متد فرق دارد، بعدی را امتحان کن
            except Exception as exc:  # noqa: BLE001
                log.warning("revoke_sub (%s) ناموفق: %s", name, exc)
                return None

        # ۲) فراخوانی مستقیم REST. اول مسیر نام محور، بعد مسیر آیدی محور
        headers = await self._http_headers()
        paths = [f"/api/user/{username}/revoke_sub"]
        # خواندن کاربر فقط برای ساختن مسیر آیدی محور است. اگر پنل در
        # دسترس نباشد (۵۲۲ کلادفلر و مانند آن) نباید استثنا از اینجا
        # بیرون بزند و هندلر را بترکاند - با همان مسیر نام محور ادامه
        # می دهیم و اگر آن هم نشد، None برمی گردد و پیام مودبانه
        # نمایش داده می شود.
        try:
            current = await self.get_user(username)
            user_id = getattr(current, "id", None)
        except PanelError as exc:
            log.warning("خواندن کاربر برای revoke_sub نشد: %s", exc)
            user_id = None
        if user_id:
            paths.append(f"/api/user/by-id/{user_id}/revoke_sub")

        for path in paths:
            try:
                r = await self._http.post(path, headers=headers)
            except Exception as exc:  # noqa: BLE001
                log.warning("revoke_sub درخواست %s ناموفق: %s", path, exc)
                continue
            if r.status_code < 400:
                log.info("ابطال ساب %s از مسیر %s انجام شد", username, path)
                return await self.get_user(username)
            if r.status_code in (404, 405):
                continue  # این مسیر در این نسخه وجود ندارد، بعدی
            log.warning("revoke_sub HTTP %s برای %s (%s)", r.status_code, username, path)
            return None

        log.error(
            "ابطال ساب برای %s با هیچ روشی انجام نشد. "
            "نسخه پنل یا SDK ممکن است این عملیات را با نام دیگری ارائه کند.",
            username,
        )
        return None

    # ---------- دستگاه های ثبت شده (HWID) ----------
    # پنل از نسخه ۵ برای هر کاربر شناسه سخت افزاری دستگاه ها را نگه
    # می دارد (جدول user_hwids با device_os و os_version و device_model).
    # نام متد در SDK و مسیر REST بین نسخه ها فرق می کند، پس مثل ابطال
    # ساب، چند نام و چند مسیر امتحان و نتیجه موفق کش می شود.
    # پنل رسما این را «HWID» می نامد (نه «دستگاه»)؛ کد اپراتور و روتر
    # پنل هم به همین اسم تفکیک شده اند (app/operation/hwid.py و
    # app/routers/hwid.py)، پس این اسم ها محتمل ترین حدس اند - ولی چون
    # مستندات عمومی دقیق مسیر REST را نمی دهد، چند حالت رایج هم اضافه
    # شده و در صورت شکست همه، /hwid ادمین دقیقا نشان می دهد کدام ها
    # امتحان شدند و هرکدام چه جواب داد.
    _HWID_SDK_GET = (
        "get_user_hwids",
        "list_user_hwids",
        "get_hwids",
        "user_hwids",
        "hwids",
    )
    _HWID_SDK_RESET = (
        "reset_user_hwids",
        "delete_user_hwids",
        "remove_user_hwids",
        "reset_hwids",
        "clear_user_hwids",
    )

    async def _hwid_paths(self, username: str) -> list[str]:
        """مسیرهای محتمل، به ترتیب احتمال درست بودن.

        لاگ واقعی نشان داد `/api/user/<نام>/hwids` جواب ۴۲۲ می دهد، نه
        ۴۰۴. یعنی مسیر وجود دارد ولی ورودی را نمی پذیرد - تقریبا همیشه
        یعنی پارامتر باید عددی باشد (آیدی داخلی کاربر) نه نام کاربری.
        پس اول شکل عددی امتحان می شود.
        """
        paths: list[str] = []
        # مثل revoke_sub: نبود پنل نباید صفحه دستگاه ها را بترکاند
        try:
            current = await self.get_user(username)
            user_id = getattr(current, "id", None)
        except PanelError as exc:
            log.warning("خواندن کاربر برای مسیر HWID نشد: %s", exc)
            user_id = None

        if user_id:
            paths += [
                f"/api/user/{user_id}/hwids",
                f"/api/user/{user_id}/hwid",
                f"/api/hwid/{user_id}",
                f"/api/hwid/user/{user_id}",
            ]
        paths += [
            f"/api/user/{username}/hwids",
            f"/api/user/{username}/hwid",
            f"/api/hwid/{username}",
            f"/api/hwids/{username}",
        ]
        return paths

    @staticmethod
    def _hwid_rows(data) -> list[dict]:  # noqa: ANN001
        """نرمال سازی خروجی: پنل گاهی لیست خام و گاهی {items: [...]} می دهد."""
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        if isinstance(data, dict):
            for key in ("hwids", "items", "devices", "data"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            return []
        out = []
        for row in data:
            if hasattr(row, "model_dump"):
                row = row.model_dump(mode="json")
            if isinstance(row, dict):
                out.append(row)
            elif isinstance(row, str):
                out.append({"hwid": row})
        return out

    async def get_hwids(
        self, username: str, trace: list[str] | None = None
    ) -> list[dict] | None:
        """دستگاه های ثبت شده کاربر.

        None یعنی این قابلیت روی پنل در دسترس نیست (نسخه قدیمی یا HWID
        خاموش). لیست خالی یعنی قابلیت هست ولی هنوز دستگاهی ثبت نشده.
        تفاوت این دو مهم است، چون پیام کاربر کاملا فرق می کند.

        نکته مهم: یک جواب غیر ۲۰۰ روی یک مسیر حدسی به معنی غلط بودن
        *همه* مسیرها نیست - باید همه حدس ها امتحان شوند و فقط اگر همه
        شکست خوردند None برگردد. حالت قبلی با اولین جواب غیر ۴۰۴ کامل
        متوقف می شد که باعث می شد این صفحه هیچ وقت دستگاه نشان ندهد
        حتی وقتی یکی از مسیرهای بعدی درست بود.

        trace اگر داده شود، هر تلاش (متد یا مسیر) و نتیجه اش برای
        دستور ادمین /hwid در آن ثبت می شود.
        """
        # متد SDK را با هر دو شکل ورودی امتحان می کنیم: نام کاربری و
        # آیدی عددی. لاگ واقعی نشان داد شکل نام کاربری ۴۲۲ می گیرد،
        # یعنی این اندپوینت آیدی عددی می خواهد.
        candidates: list = [username]
        try:
            current = await self.get_user(username)
            uid = getattr(current, "id", None)
            if uid:
                candidates.insert(0, uid)
        except PanelError:
            pass

        for name in self._HWID_SDK_GET:
            fn = getattr(self._api, name, None)
            if fn is None:
                continue
            for arg in candidates:
                try:
                    rows = self._hwid_rows(await fn(arg, **await self._auth()))
                    if trace is not None:
                        trace.append(f"✅ متد {name}({arg!r}) -> {len(rows)} مورد")
                    return rows
                except TypeError as exc:
                    if trace is not None:
                        trace.append(f"⏭ متد {name} امضای متفاوت دارد ({exc})")
                    break
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "خواندن دستگاه ها با متد %s(%r) ناموفق: %s", name, arg, exc
                    )
                    if trace is not None:
                        trace.append(f"❌ متد {name}({arg!r}): {exc}")
                    continue

        headers = await self._http_headers()
        for path in await self._hwid_paths(username):
            if path in self._dead_endpoints:
                if trace is not None:
                    trace.append(f"⏭ {path} (قبلا ۴۰۴/۴۰۵ داده)")
                continue
            try:
                r = await self._http.get(path, headers=headers)
            except Exception as exc:  # noqa: BLE001
                log.warning("خواندن دستگاه ها از %s ناموفق: %s", path, exc)
                if trace is not None:
                    trace.append(f"❌ {path}: {exc}")
                continue
            if r.status_code == 200:
                rows = self._hwid_rows(r.json())
                if trace is not None:
                    trace.append(f"✅ {path} -> {len(rows)} مورد")
                return rows
            if r.status_code in (404, 405, 422):
                # ۴۲۲ یعنی مسیر هست ولی این شکل ورودی را نمی پذیرد؛
                # مثل ۴۰۴ علامت می خورد تا دفعه بعد وقت تلف نشود.
                self._dead_endpoints.add(path)
            if trace is not None:
                trace.append(f"❌ {path}: HTTP {r.status_code}")
            # مهم: اینجا return نمی کنیم - مسیر بعدی هم امتحان می شود
        return None

    async def reset_hwids(self, username: str) -> bool:
        """خروج همه دستگاه ها (پاک کردن HWIDهای ثبت شده).

        مثل get_hwids: یک جواب بد روی یک مسیر حدسی باعث نمی شود از
        امتحان بقیه مسیرها صرف نظر کنیم.
        """
        for name in self._HWID_SDK_RESET:
            fn = getattr(self._api, name, None)
            if fn is None:
                continue
            try:
                await fn(username, **await self._auth())
                log.info("دستگاه های %s با متد %s پاک شد", username, name)
                return True
            except TypeError:
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("پاک کردن دستگاه ها (%s) ناموفق: %s", name, exc)
                continue

        headers = await self._http_headers()
        for path in await self._hwid_paths(username):
            try:
                r = await self._http.delete(path, headers=headers)
            except Exception as exc:  # noqa: BLE001
                log.warning("حذف دستگاه ها از %s ناموفق: %s", path, exc)
                continue
            if r.status_code < 400:
                log.info("دستگاه های %s از مسیر %s پاک شد", username, path)
                return True
            log.warning("حذف دستگاه HTTP %s برای %s (%s)", r.status_code, username, path)
            # مهم: اینجا هم return نمی کنیم - مسیر بعدی هم امتحان می شود
        return False

    def hwid_capability(self) -> str:
        """برای check_setup: قابلیت دستگاه ها از چه راهی انجام می شود."""
        for name in self._HWID_SDK_GET:
            if getattr(self._api, name, None) is not None:
                return f"متد SDK: {name}"
        return "بدون متد SDK - از مسیر REST استفاده می شود"

    def revoke_capability(self) -> str:
        """توضیح کوتاه از اینکه ابطال ساب از چه راهی انجام می شود.

        فقط برای check_setup است تا قبل از اتکا به این قابلیت بدانی
        SDK متد آماده دارد یا باید از REST استفاده شود.
        """
        for name in ("revoke_user_sub", "revoke_sub", "reset_user_sub"):
            if getattr(self._api, name, None) is not None:
                return f"متد SDK: {name}"
        return "بدون متد SDK - از مسیر REST استفاده می شود"

    # ---------- حذف ----------
    async def remove(self, username: str) -> bool:
        """حذف کاربر. True یعنی مطمئنیم حذف شد (یا از اول نبود)."""
        try:
            await self._api.remove_user(username, **await self._auth())
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return True
            log.warning("panel remove failed for %s: %s", username, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("panel remove failed for %s: %s", username, exc)
            return False


def gb_bytes(gb: float) -> int:
    return int(gb * GIB)


def mb_bytes(mb: float) -> int:
    return int(mb * 1024 * 1024)


def sub_url_of(user: UserResponse, base_url: str) -> str:
    url = user.subscription_url or ""
    if url.startswith("http"):
        return url
    if url:
        return f"{base_url.rstrip('/')}/{url.lstrip('/')}"
    return ""
