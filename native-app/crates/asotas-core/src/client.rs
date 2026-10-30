//! گفتگو با سرور AsoTas. همان مسیرهایی که برنامهٔ Capacitor (static/app.js و gc.js) می زند:
//!
//! - `POST app/guest` حساب مهمان و توکن نشست (بار اول)
//! - `GET|POST api/<name>` با هدر `X-GC-Token`؛ اگر سرور ۴۰۱ داد یک حساب مهمان تازه و یک بار دیگر
//! - `POST app/login/...` ورود با تلگرام یا ایمیل؛ توکن تازه جای توکن قبلی می نشیند
//!
//! همهٔ متدها بلاک می شوند؛ کاتلین آنها را روی `Dispatchers.IO` صدا می زند.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::{json, Value};
use ureq::Agent;

use crate::error::ApiError;
use crate::games::*;
use crate::models::*;
use crate::store::TokenStore;

#[derive(uniffi::Object)]
pub struct Client {
    base: String,
    device: String,
    agent: Agent,
    store: TokenStore,
    /// دو درخواست هم زمان فقط یک حساب مهمان بسازند
    guest: Mutex<()>,
}

/// تنظیم میز (JSON از کاتلین)
fn cfg_value(cfg_json: &str) -> Result<Value, ApiError> {
    serde_json::from_str(cfg_json).map_err(|e| ApiError::Server { code: "bad_body".into(), extra_json: e.to_string() })
}

/// کلید یکتای هر خرید (۸ تا ۶۴ نویسهٔ A-Za-z0-9_-، api._idem)
fn idem() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    format!("n{t:x}_{:x}", N.fetch_add(1, Ordering::Relaxed))
}

enum Req<'a> {
    Get(&'a [(String, String)]),
    Post(&'a Value),
}

impl Client {
    fn url(&self, path: &str) -> String {
        format!("{}{}", self.base, path.trim_start_matches('/'))
    }

    /// آدرس نسبی سرور (عکس پروفایل، عکس پیام) را کامل می کند؛ آدرس کامل دست نمی خورد
    fn resolve(&self, u: &str) -> String {
        if u.starts_with("pic/") || u.starts_with("media/") {
            self.url(u)
        } else {
            u.to_string()
        }
    }

    fn send(&self, path: &str, req: Req, token: Option<&str>) -> Result<Value, ApiError> {
        let url = self.url(path);
        let res = match req {
            Req::Get(query) => {
                let mut r = self.agent.get(&url).header("Cache-Control", "no-store");
                for (k, v) in query {
                    r = r.query(k, v);
                }
                if let Some(t) = token {
                    r = r.header("X-GC-Token", t);
                }
                r.call()
            }
            Req::Post(body) => {
                let mut r = self.agent.post(&url).header("Cache-Control", "no-store");
                if let Some(t) = token {
                    r = r.header("X-GC-Token", t);
                }
                r.send_json(body)
            }
        };
        let mut resp = res.map_err(ApiError::network)?;
        let status = resp.status().as_u16();
        let raw = resp.body_mut().read_to_string().map_err(ApiError::network)?;
        let body: Value = serde_json::from_str(&raw).unwrap_or(Value::Null);
        if (200..300).contains(&status) {
            return Ok(body);
        }
        let code = body["error"].as_str().unwrap_or("").to_string();
        Err(match (status, code.as_str()) {
            (401, _) | (_, "auth") => ApiError::Auth,
            (429, _) | (_, "rate") => ApiError::Rate,
            (_, "") => ApiError::Server { code: "server".into(), extra_json: raw },
            _ => ApiError::Server { code, extra_json: raw },
        })
    }

    /// توکن نشست؛ `fresh` یعنی توکن قبلی دیگر کار نمی کند و حساب مهمان تازه لازم است
    fn token(&self, fresh: bool) -> Result<String, ApiError> {
        let _one = self.guest.lock().unwrap();
        if fresh {
            self.store.set(None);
        }
        if let Some(t) = self.store.get() {
            return Ok(t);
        }
        let j = self.send("app/guest", Req::Post(&json!({ "device": self.device })), None)?;
        let t = text(&j["token"]);
        if t.is_empty() {
            return Err(ApiError::Server { code: "server".into(), extra_json: j.to_string() });
        }
        self.store.set(Some(t.clone()));
        Ok(t)
    }

    fn api(&self, name: &str, req: Req) -> Result<Value, ApiError> {
        let path = format!("api/{}", name.trim_matches('/'));
        let tok = self.token(false)?;
        let again = |req| self.send(&path, req, Some(&self.token(true)?));
        match req {
            Req::Get(q) => match self.send(&path, Req::Get(q), Some(&tok)) {
                Err(ApiError::Auth) => again(Req::Get(q)),
                r => r,
            },
            Req::Post(b) => match self.send(&path, Req::Post(b), Some(&tok)) {
                Err(ApiError::Auth) => again(Req::Post(b)),
                r => r,
            },
        }
    }

    /// درخواست ورود؛ توکن فعلی (اگر هست) می رود تا حساب مهمان همین گوشی به حساب تازه وصل شود
    fn login(&self, path: &str, body: Value) -> Result<Value, ApiError> {
        let cur = self.store.get();
        self.send(path, Req::Post(&body), cur.as_deref())
    }

    /// توکنی که سرور بعد از ورود داد جای توکن قبلی می نشیند
    fn keep(&self, j: &Value) {
        let t = text(&j["token"]);
        if !t.is_empty() {
            self.store.set(Some(t));
        }
    }
}

#[uniffi::export]
impl Client {
    /// `base_url` آدرس سرور با / آخر (مثل https://dezhcode.pyho.ir/obour/gc/)،
    /// `data_dir` پوشهٔ خصوصی برنامه، `device` اسم گوشی برای فهرست نشست ها
    #[uniffi::constructor]
    pub fn new(base_url: String, data_dir: String, device: String) -> Arc<Self> {
        let base = if base_url.ends_with('/') { base_url } else { format!("{base_url}/") };
        let agent: Agent = Agent::config_builder()
            .http_status_as_error(false)
            .timeout_global(Some(Duration::from_secs(45)))
            .user_agent(concat!("AsoTas-Native/", env!("CARGO_PKG_VERSION")))
            .build()
            .into();
        let device: String = device.chars().take(40).collect();
        Arc::new(Client { base, device, agent, store: TokenStore::open(&data_dir), guest: Mutex::new(()) })
    }

    /// این گوشی قبلا حساب (مهمان یا ورود کرده) دارد؟
    pub fn has_session(&self) -> bool {
        self.store.get().is_some()
    }

    pub fn me(&self) -> Result<Me, ApiError> {
        let j = self.api("me", Req::Get(&[]))?;
        Ok(Me::from_json(&j, |u| self.resolve(u)))
    }

    pub fn daily_claim(&self) -> Result<DailyClaim, ApiError> {
        let j = self.api("daily", Req::Post(&json!({})))?;
        Ok(DailyClaim { coins: int(&j["coins"]), balance: int(&j["points"]), daily: Daily::from_json(&j["daily"]) })
    }

    pub fn friends(&self) -> Result<Friends, ApiError> {
        let j = self.api("friends", Req::Get(&[]))?;
        Ok(Friends::from_json(&j, |u| self.resolve(u)))
    }

    // ---------- دوستان (social.py) ----------
    /// پیدا کردن با یوزرنیم
    pub fn friend_find(&self, name: String) -> Result<UserCard, ApiError> {
        let j = self.api("friends/find", Req::Get(&[("n".to_string(), name)]))?;
        Ok(UserCard::from_json(&j, &|u: &str| self.resolve(u)))
    }

    /// پروفایل یک نفر (کارت دوست)
    pub fn friend_user(&self, uid: String) -> Result<UserCard, ApiError> {
        let j = self.api("friends/user", Req::Get(&[("u".to_string(), uid)]))?;
        Ok(UserCard::from_json(&j, &|u: &str| self.resolve(u)))
    }

    /// درخواست دوستی؛ رابطهٔ تازه (outgoing یا اگر او هم خواسته بود friend)
    pub fn friend_request(&self, uid: String) -> Result<String, ApiError> {
        Ok(text(&self.api("friends/request", Req::Post(&json!({ "uid": uid })))?["relation"]))
    }

    pub fn friend_accept(&self, uid: String) -> Result<String, ApiError> {
        Ok(text(&self.api("friends/accept", Req::Post(&json!({ "uid": uid })))?["relation"]))
    }

    /// رد درخواست، پس گرفتن درخواست یا حذف از دوستان
    pub fn friend_drop(&self, uid: String) -> Result<String, ApiError> {
        Ok(text(&self.api("friends/drop", Req::Post(&json!({ "uid": uid })))?["relation"]))
    }

    pub fn friend_block(&self, uid: String, on: bool) -> Result<String, ApiError> {
        Ok(text(&self.api("friends/block", Req::Post(&json!({ "uid": uid, "on": on })))?["relation"]))
    }

    /// پیام های خصوصی با یک دوست (since = آخرین id دیده شده، ۰ برای همه)
    pub fn dm(&self, uid: String, since: i64) -> Result<DmChat, ApiError> {
        let q = [("u".to_string(), uid), ("since".to_string(), since.max(0).to_string())];
        let j = self.api("dm", Req::Get(&q))?;
        Ok(DmChat::from_json(&j, &|u: &str| self.resolve(u)))
    }

    pub fn dm_send(&self, uid: String, message: String) -> Result<i64, ApiError> {
        Ok(int(&self.api("dm", Req::Post(&json!({ "uid": uid, "text": message })))?["id"]))
    }

    /// میز آزاد می سازد و کارت دعوتش را در چت دوست می گذارد
    pub fn dm_invite(&self, uid: String, game: String) -> Result<GameInvite, ApiError> {
        let j = self.api("dm/invite", Req::Post(&json!({ "uid": uid, "game": game })))?;
        Ok(GameInvite { match_id: text(&j["match"]), code: text(&j["code"]), game: text(&j["game"]) })
    }

    // ---------- میزها (برای همهٔ بازی ها؛ cfg_json مثل {"players":2,"pawns":2,"mode":"free"}) ----------

    /// صف ناشناس؛ با "solo": true (دوستانه) میز با ربات همان جا ساخته می شود
    pub fn queue_join(&self, game: String, cfg_json: String) -> Result<QueueState, ApiError> {
        let body = json!({ "cfg": cfg_value(&cfg_json)? });
        Ok(QueueState::from_json(&self.api(&format!("{game}/queue"), Req::Post(&body))?))
    }

    pub fn queue_status(&self, game: String) -> Result<QueueState, ApiError> {
        Ok(QueueState::from_json(&self.api(&format!("{game}/queue"), Req::Get(&[]))?))
    }

    /// منتظر نمی مانم: ربات ها جای خالی را پر کنند
    pub fn queue_bots(&self, game: String) -> Result<QueueState, ApiError> {
        Ok(QueueState::from_json(&self.api(&format!("{game}/queue/bots"), Req::Post(&json!({})))?))
    }

    pub fn queue_leave(&self, game: String) -> Result<(), ApiError> {
        self.api(&format!("{game}/queue/leave"), Req::Post(&json!({})))?;
        Ok(())
    }

    /// میز دعوت دوستانه با لینک و کد
    pub fn invite_create(&self, game: String, cfg_json: String) -> Result<Invited, ApiError> {
        let j = self.api(&format!("{game}/invite"), Req::Post(&json!({ "cfg": cfg_value(&cfg_json)? })))?;
        Ok(Invited { match_id: text(&j["match"]), code: text(&j["code"]), link: text(&j["link"]) })
    }

    /// نشستن سر میز دعوت با کد؛ شناسهٔ میز
    pub fn invite_join(&self, game: String, code: String) -> Result<String, ApiError> {
        Ok(text(&self.api(&format!("{game}/join"), Req::Post(&json!({ "code": code })))?["match"]))
    }

    /// سازندهٔ میز شروع می کند (جای خالی با ربات)
    pub fn lobby_start(&self, game: String, match_id: String) -> Result<(), ApiError> {
        self.api(&format!("{game}/start"), Req::Post(&json!({ "match": match_id })))?;
        Ok(())
    }

    /// بلند شدن از میز یا ترک بازی
    pub fn leave_match(&self, game: String, match_id: String) -> Result<(), ApiError> {
        self.api(&format!("{game}/leave"), Req::Post(&json!({ "match": match_id })))?;
        Ok(())
    }

    /// میز از دید من؛ since = آخرین رویداد دیده شده
    /// chat: شمارهٔ آخرین پیام گفتگوی میز که دیده ام؛ پیام های بعدی در chat می آیند (None یعنی گفتگو نخواه)
    pub fn match_view(&self, game: String, match_id: String, since: i64, chat: Option<i64>) -> Result<MatchView, ApiError> {
        let mut q = vec![("id".to_string(), match_id), ("since".to_string(), since.max(0).to_string())];
        if let Some(c) = chat {
            q.push(("chat".to_string(), c.max(0).to_string()));
        }
        let j = self.api(&format!("{game}/match"), Req::Get(&q))?;
        Ok(MatchView::from_json(&j, &game, &|u: &str| self.resolve(u)))
    }

    /// پیامی در گفتگوی سر میز (حداکثر ۱۴۰ نویسه)؛ شمارهٔ پیام برمی گردد
    pub fn table_chat(&self, game: String, match_id: String, text: String) -> Result<i64, ApiError> {
        let j = self.api(&format!("{game}/chat"), Req::Post(&json!({ "match": match_id, "text": text })))?;
        Ok(int(&j["id"]))
    }

    /// حرکت در بازی (منچ: roll، move با k = شمارهٔ مهره)؛ میز تازه برمی گردد
    pub fn act(&self, game: String, match_id: String, action: String, k: Option<i64>, since: i64) -> Result<MatchView, ApiError> {
        let body = json!({ "match": match_id, "k": k, "since": since.max(0) });
        let j = self.api(&format!("{game}/{action}"), Req::Post(&body))?;
        Ok(MatchView::from_json(&j, &game, &|u: &str| self.resolve(u)))
    }

    // ---------- فروشگاه ظاهر و پروفایل ----------
    pub fn styles(&self) -> Result<Styles, ApiError> {
        Ok(Styles::from_json(&self.api("style", Req::Get(&[]))?))
    }

    /// خرید (و انتخاب) یک طرح؛ کلید یکتای هر خرید تا لمس دوباره دوبار کم نکند
    pub fn style_buy(&self, id: String) -> Result<Styles, ApiError> {
        Ok(Styles::from_json(&self.api("style/buy", Req::Post(&json!({ "id": id, "idem": idem() })))?))
    }

    pub fn style_use(&self, id: String) -> Result<Styles, ApiError> {
        Ok(Styles::from_json(&self.api("style/use", Req::Post(&json!({ "id": id })))?))
    }

    pub fn profile(&self) -> Result<Profile, ApiError> {
        Ok(Profile::from_json(&self.api("profile", Req::Get(&[]))?))
    }

    /// «درباره من» (تا ۸۰ نویسه) و کاور؛ None یعنی دست نخورد. bio تازه برمی گردد
    pub fn save_profile(&self, bio: Option<String>, cover: Option<String>) -> Result<String, ApiError> {
        let mut body = json!({});
        if let Some(b) = bio {
            body["bio"] = json!(b.chars().take(80).collect::<String>());
        }
        if let Some(c) = cover {
            body["cover"] = json!(c);
        }
        Ok(text(&self.api("settings", Req::Post(&body))?["bio"]))
    }

    /// تنظیم روشن/خاموش روی سرور (sound، tutorial، show_spend)
    pub fn set_flag(&self, name: String, on: bool) -> Result<(), ApiError> {
        let mut body = json!({});
        body[name] = json!(on);
        self.api("settings", Req::Post(&body))?;
        Ok(())
    }

    /// کارت «اسمت تو بازی اینه» دیده شد و دیگر نمی آید
    pub fn name_seen(&self) -> Result<(), ApiError> {
        self.api("name/seen", Req::Post(&json!({})))?;
        Ok(())
    }

    pub fn name_check(&self, name: String) -> Result<NameCheck, ApiError> {
        let j = self.api("name/check", Req::Get(&[("n".to_string(), name)]))?;
        Ok(NameCheck::from_json(&j))
    }

    /// یوزرنیم تازه؛ نام نهایی (بعد از یکدست سازی سرور) برمی گردد
    pub fn set_name(&self, name: String) -> Result<String, ApiError> {
        let j = self.api("name", Req::Post(&json!({ "name": name })))?;
        Ok(text(&j["name"]))
    }

    /// هر اندپوینت دیگر (GET)؛ جواب خام JSON تا صفحه هایی که هنوز مدل ندارند هم کار کنند
    pub fn api_get(&self, name: String, query: HashMap<String, String>) -> Result<String, ApiError> {
        let mut q: Vec<(String, String)> = query.into_iter().collect();
        q.sort();
        Ok(self.api(&name, Req::Get(&q))?.to_string())
    }

    /// هر اندپوینت دیگر (POST) با بدنهٔ JSON
    pub fn api_post(&self, name: String, body_json: String) -> Result<String, ApiError> {
        let body: Value = serde_json::from_str(&body_json)
            .map_err(|e| ApiError::Server { code: "bad_body".into(), extra_json: e.to_string() })?;
        Ok(self.api(&name, Req::Post(&body))?.to_string())
    }

    pub fn login_telegram_start(&self) -> Result<TelegramLogin, ApiError> {
        let j = self.login("app/login/tg", json!({ "device": self.device }))?;
        Ok(TelegramLogin { link: text(&j["link"]), poll: text(&j["poll"]), ttl: int(&j["ttl"]) })
    }

    pub fn login_telegram_check(&self, poll: String) -> Result<TelegramCheck, ApiError> {
        let j = self.login("app/login/tg/check", json!({ "poll": poll }))?;
        let state = TelegramState::from_str(j["state"].as_str().unwrap_or(""));
        if state == TelegramState::Ok {
            self.keep(&j);
        }
        let account = j.get("account").filter(|a| a.is_object()).map(Account::from_json);
        Ok(TelegramCheck { state, account })
    }

    pub fn login_email_start(&self, email: String) -> Result<EmailCode, ApiError> {
        let j = self.login("app/login/email", json!({ "email": email.trim() }))?;
        Ok(EmailCode { email: text(&j["email"]), ttl: int(&j["ttl"]), resend: int(&j["resend"]) })
    }

    pub fn login_email_verify(&self, email: String, code: String) -> Result<Account, ApiError> {
        let body = json!({ "email": email.trim(), "code": code.trim(), "device": self.device });
        let j = self.login("app/login/email/verify", body)?;
        self.keep(&j);
        Ok(Account::from_json(&j["account"]))
    }

    /// خروج: نشست روی سرور بسته و توکن گوشی پاک می شود (بار بعد حساب مهمان تازه)
    pub fn logout(&self) {
        if let Some(t) = self.store.get() {
            let _ = self.send("app/logout", Req::Post(&json!({})), Some(&t));
        }
        self.store.set(None);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use mockito::{Matcher, Server};

    const ME: &str = r#"{
        "player": {"name": "tasi_42", "av": 5, "points": "1250", "games": 9, "wins": 4, "bio": "", "pic": "pic/abc",
                   "joined": 1700000000, "name_hint": true},
        "account": {"kind": "email", "email": "a@b.ir"},
        "daily": {"claimed": false, "day": 2, "next": 3, "plan": [10, 20, 30]},
        "social": {"requests": 2, "unread": 7},
        "ranks": {"hokm": {"cups": 120, "league": "نقره‌ای"}, "ludo": {"cups": 30}},
        "history": [{"kind": "daily", "amount": 10, "note": "جایزهٔ روز ۱", "status": "approved", "created_at": 1700000000}],
        "tables": [{"kind": "queue", "game": "hokm", "found": 2, "need": 4},
                   {"kind": "playing", "id": "m1", "game": "ludo", "players": []}],
        "banned": false, "maintenance": false, "notice": "",
        "settings": {"ranked": true},
        "active_match": null, "active_game": null
    }"#;

    #[test]
    fn social_chat_shop_profile() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("t".into()));
        server.mock("GET", "/gc/api/friends/find").match_query(Matcher::UrlEncoded("n".into(), "sara".into()))
            .with_body(r#"{"user": {"uid": "u2", "name": "sara", "av": 4, "pic": "", "bio": "hi", "games": 12, "wins": 5}, "relation": "none"}"#).create();
        let req = server.mock("POST", "/gc/api/friends/request").match_body(Matcher::Json(json!({ "uid": "u2" })))
            .with_body(r#"{"relation": "outgoing"}"#).expect(1).create();
        server.mock("POST", "/gc/api/friends/block").match_body(Matcher::Json(json!({ "uid": "u2", "on": false })))
            .with_body(r#"{"relation": "none"}"#).create();
        server.mock("GET", "/gc/api/dm").match_query(Matcher::AllOf(vec![
            Matcher::UrlEncoded("u".into(), "u2".into()), Matcher::UrlEncoded("since".into(), "7".into())]))
            .with_body(r#"{"user": {"uid": "u2", "name": "sara", "av": 4, "pic": "", "online": true, "playing": null, "seen": 0},
                "relation": "friend", "messages": [
                {"id": 8, "me": false, "kind": "text", "text": "salam", "at": 1700000000},
                {"id": 9, "me": true, "kind": "invite", "text": "دعوت به حکم", "at": 1700000060, "meta": {"game": "hokm", "code": "AB12", "match": "m9"}}]}"#).create();
        server.mock("POST", "/gc/api/dm").match_body(Matcher::Json(json!({ "uid": "u2", "text": "بزن بریم!" })))
            .with_body(r#"{"id": 10}"#).create();
        server.mock("POST", "/gc/api/style/buy").match_body(Matcher::PartialJson(json!({ "id": "table:b" })))
            .with_body(r#"{"items": [{"id": "table:a", "kind": "table", "look": "a", "name": "میز کلاسیک", "price": 0, "owned": true, "on": false},
                {"id": "table:b", "kind": "table", "look": "b", "name": "میز کافه شب", "price": 80, "owned": true, "on": true}],
                "table": "b", "cards": "a", "points": 40}"#).create();
        server.mock("GET", "/gc/api/profile").with_body(r#"{"games": [{"game": "hokm", "games": 4, "wins": 3, "prize": 0}],
            "recent": [{"game": "hokm", "won": true, "prize": 6, "at": 1700000000, "cups": 20, "mode": "ranked"}]}"#).create();
        server.mock("POST", "/gc/api/settings").match_body(Matcher::Json(json!({ "bio": "عاشق حکم" })))
            .with_body(r#"{"ok": true, "bio": "عاشق حکم", "cover": "gc"}"#).create();
        let c = client(&server, &dir);

        let u = c.friend_find("sara".into()).unwrap();
        assert_eq!((u.person.uid.as_str(), u.games, u.wins, u.relation.as_str()), ("u2", 12, 5, "none"));
        assert_eq!(c.friend_request("u2".into()).unwrap(), "outgoing");
        req.assert();
        assert_eq!(c.friend_block("u2".into(), false).unwrap(), "none");

        let chat = c.dm("u2".into(), 7).unwrap();
        assert!(chat.user.online);
        assert_eq!(chat.messages.len(), 2);
        assert_eq!((chat.messages[1].kind.as_str(), chat.messages[1].game.as_deref(), chat.messages[1].code.as_deref()), ("invite", Some("hokm"), Some("AB12")));
        assert_eq!(chat.messages[0].game, None);
        assert_eq!(c.dm_send("u2".into(), "بزن بریم!".into()).unwrap(), 10);

        let s = c.style_buy("table:b".into()).unwrap();
        assert_eq!((s.table.as_str(), s.points, s.items.len()), ("b", 40, 2));
        assert!(s.items[1].on && s.items[1].owned);

        let p = c.profile().unwrap();
        assert_eq!((p.games[0].wins, p.recent[0].cups, p.recent[0].mode.as_str()), (3, 20, "ranked"));
        assert_eq!(c.save_profile(Some("عاشق حکم".into()), None).unwrap(), "عاشق حکم");
        assert_ne!(idem(), idem());
    }

    #[test]
    fn tables_and_ludo() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("t".into()));
        server.mock("POST", "/gc/api/ludo/queue").match_body(Matcher::Json(json!({ "cfg": { "players": 2, "pawns": 2, "mode": "free" } })))
            .with_body(r#"{"state": "waiting", "waited": 3, "cfg": {"players": 2, "mode": "free"}, "found": 1, "need": 2, "bots_in": 12, "can_bots": true}"#).create();
        server.mock("POST", "/gc/api/ludo/queue/bots").with_body(r#"{"state": "matched", "match": "m7"}"#).create();
        server.mock("POST", "/gc/api/ludo/invite")
            .with_body(r#"{"match": "m8", "code": "XY12", "link": "https://t.me/bot?start=ludo_XY12"}"#).create();
        server.mock("GET", "/gc/api/ludo/match").match_query(Matcher::UrlEncoded("id".into(), "m8".into()))
            .with_body(r#"{"id": "m8", "status": "lobby", "cfg": {"players": 2, "pawns": 2, "mode": "free"}, "me": "yellow",
                "lobby": {"seats": [{"color": "yellow", "name": "tasi", "av": 3, "pic": "", "me": true}], "code": "XY12", "host": true, "link": "L"}}"#).create();
        server.mock("POST", "/gc/api/ludo/roll").match_body(Matcher::Json(json!({ "match": "m7", "k": null, "since": 4 })))
            .with_body(r#"{"id": "m7", "status": "playing", "cfg": {"players": 2, "pawns": 2, "mode": "free"}, "me": "yellow",
                "game": {"order": ["red", "yellow"], "players": {"red": {"name": "bot", "av": 2, "pic": "", "bot": true, "out": false, "me": false},
                    "yellow": {"name": "tasi", "av": 3, "pic": "", "bot": false, "out": false, "me": true}},
                    "pawns": {"red": [-1, 5], "yellow": [-1, -1]}, "turn": "yellow", "phase": "move", "dice": 6, "movable": [0, 1],
                    "deadline_ms": 18000, "turn_ms": 20000, "last": {"yellow": 6}, "done": {"red": 0, "yellow": 0},
                    "events": [{"seq": 5, "t": "roll", "c": "yellow", "v": 6, "auto": false},
                               {"seq": 6, "t": "move", "c": "red", "k": 1, "frm": 3, "to": 5, "cap": [["yellow", 0]], "fin": false}],
                    "seq": 6, "over": false, "winner": null, "stats": {"caps": 2, "sixes": 3}, "started": 1700000000.5},
                "result": {"won": true, "coins": 80, "cups": 12, "rank": {"cups": 240, "games": 9, "wins": 5, "league": "نقره‌ای"}}}"#).create();
        let c = client(&server, &dir);

        let q = c.queue_join("ludo".into(), r#"{"players":2,"pawns":2,"mode":"free"}"#.into()).unwrap();
        assert_eq!((q.state.as_str(), q.found, q.need, q.bots_in, q.can_bots), ("waiting", 1, 2, Some(12), true));
        assert_eq!(c.queue_bots("ludo".into()).unwrap().match_id.as_deref(), Some("m7"));
        let inv = c.invite_create("ludo".into(), r#"{"players":2,"pawns":2,"mode":"free"}"#.into()).unwrap();
        assert_eq!((inv.match_id.as_str(), inv.code.as_str()), ("m8", "XY12"));

        let lobby = c.match_view("ludo".into(), "m8".into(), 0, None).unwrap();
        let l = lobby.lobby.unwrap();
        assert!(l.host && l.seats[0].me);
        assert_eq!((lobby.status.as_str(), lobby.players, lobby.ludo), ("lobby", 2, None));

        let v = c.act("ludo".into(), "m7".into(), "roll".into(), None, 4).unwrap();
        let g = v.ludo.unwrap();
        assert_eq!((g.dice, g.movable.clone(), g.turn.as_deref()), (Some(6), vec![0, 1], Some("yellow")));
        assert_eq!(g.pawns["red"], vec![-1, 5]);
        assert!(g.players["yellow"].me && g.players["red"].bot);
        assert_eq!((g.events.len(), g.events[1].from, g.events[1].to, g.events[1].caps.clone()), (2, 3, 5, vec!["yellow:0".to_string()]));
        assert_eq!((g.caps, g.sixes, g.started, g.events[0].auto), (2, 3, 1700000000.5, false));
        let r = v.result.unwrap();
        assert_eq!((r.cups, r.league.as_deref(), r.total_cups), (12, Some("نقره‌ای"), 240));
        assert!(c.queue_join("ludo".into(), "not json".into()).is_err());
        assert!(lobby.chat.is_empty());
    }

    #[test]
    fn table_chat() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("t".into()));
        server.mock("GET", "/gc/api/hokm/match")
            .match_query(Matcher::AllOf(vec![Matcher::UrlEncoded("id".into(), "h1".into()), Matcher::UrlEncoded("chat".into(), "3".into())]))
            .with_body(r#"{"id": "h1", "status": "playing", "cfg": {"players": 4}, "me": "0",
                "chat": [{"id": 4, "color": "1", "text": "سلام!", "at": 1700000000, "name": "brave_tiger", "av": 7, "pic": "", "me": false, "pid": "p9"},
                         {"id": 5, "color": "0", "text": "خوش‌بازی!", "at": 1700000001, "name": "tasi", "av": 3, "pic": "pic/ab", "me": true, "pid": ""}]}"#).create();
        server.mock("POST", "/gc/api/hokm/chat").match_body(Matcher::Json(json!({ "match": "h1", "text": "زود باش" })))
            .with_body(r#"{"ok": true, "id": 6}"#).create();
        server.mock("POST", "/gc/api/hokm/chat").match_body(Matcher::Json(json!({ "match": "h1", "text": "x" })))
            .with_status(400).with_body(r#"{"error": "chat_slow"}"#).create();
        let c = client(&server, &dir);

        let v = c.match_view("hokm".into(), "h1".into(), 0, Some(3)).unwrap();
        assert_eq!(v.chat.len(), 2);
        assert_eq!((v.chat[0].id, v.chat[0].color.as_str(), v.chat[0].name.as_str(), v.chat[0].me, v.chat[0].pid.as_str()), (4, "1", "brave_tiger", false, "p9"));
        assert!(v.chat[1].me && v.chat[1].pic.as_deref().is_some_and(|p| p.ends_with("pic/ab")));
        assert_eq!(c.table_chat("hokm".into(), "h1".into(), "زود باش".into()).unwrap(), 6);
        assert!(matches!(c.table_chat("hokm".into(), "h1".into(), "x".into()), Err(ApiError::Server { code, .. }) if code == "chat_slow"));
    }

    #[test]
    fn hokm_view() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("t".into()));
        server.mock("POST", "/gc/api/hokm/play").match_body(Matcher::Json(json!({ "match": "h1", "k": 12, "since": 9 })))
            .with_body(r#"{"id": "h1", "status": "playing", "cfg": {"game": "hokm", "target": 3, "mode": "free"}, "me": "0",
                "game": {"order": ["0","1","2","3"], "me": "0",
                    "players": {"0": {"name": "tasi", "av": 3, "pic": "", "bot": false, "out": false, "me": true, "team": 0, "count": 12},
                                "1": {"name": "b1", "av": 2, "pic": "", "bot": true, "out": false, "me": false, "team": 1, "count": 12}},
                    "hand": [1, 14, 27], "phase": "play", "turn": "1", "hakem": "0", "trump": 1,
                    "trick": [[0, 12]], "led": 0, "last_trick": {"cards": [[3, 5], [0, 7]], "winner": "0"},
                    "tricks": [2, 1], "score": [1, 0], "target": 3, "hand_no": 1, "legal": [],
                    "deadline_ms": 15000, "turn_ms": 20000,
                    "events": [{"seq": 10, "t": "play", "c": "0", "card": 12, "auto": false},
                               {"seq": 11, "t": "hand", "team": 0, "pts": 2, "kot": true, "tricks": [7, 0], "score": [3, 0], "hakem": "0"}],
                    "seq": 11, "over": false, "winner": null}}"#).create();
        let c = client(&server, &dir);

        let v = c.act("hokm".into(), "h1".into(), "play".into(), Some(12), 9).unwrap();
        assert_eq!((v.target, v.ludo.is_none()), (3, true));
        let g = v.hokm.unwrap();
        assert_eq!((g.trump, g.led, g.turn.as_deref(), g.hakem.as_str()), (Some(1), Some(0), Some("1"), "0"));
        assert_eq!(g.trick, vec![Played { seat: "0".into(), card: 12 }]);
        assert_eq!((g.last_trick.len(), g.last_winner.as_deref()), (2, Some("0")));
        assert_eq!((g.tricks.clone(), g.score.clone(), g.hand.clone()), (vec![2, 1], vec![1, 0], vec![1, 14, 27]));
        assert!(g.players["0"].me && g.players["1"].bot);
        assert_eq!((g.players["1"].team, g.players["0"].count), (1, 12));
        assert_eq!((g.events[0].card, g.events[1].team, g.events[1].pts, g.events[1].kot), (Some(12), Some(0), 2, true));
    }

    #[test]
    fn level_matches_mini_app() {
        let l = level(0, 0);
        assert_eq!((l.lv, l.xp, l.left), (1, 0, 100));
        let l = level(9, 4); // ۱۵۰ تجربه: سطح ۲ از ۱۰۰ تا ۲۵۰
        assert_eq!((l.lv, l.left), (2, 100));
        assert!((l.frac - 50.0 / 150.0).abs() < 1e-9);
        let l = level(30, 10); // ۴۵۰ = ۱۰۰ + ۱۵۰ + ۲۰۰ ← درست اول سطح ۴
        assert_eq!((l.lv, l.left), (4, 250));
        assert!(l.frac.abs() < 1e-9);
    }

    #[test]
    fn friends_and_names() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("t".into()));
        server.mock("GET", "/gc/api/friends").with_body(r#"{
            "friends": [{"uid": "u1", "name": "kian", "av": 3, "pic": "pic/u1", "bio": "", "online": true,
                         "playing": "hokm", "seen": 1700000000, "unread": 2},
                        {"uid": "u2", "name": "sara", "av": 0, "pic": "", "online": false, "playing": null}],
            "incoming": [{"uid": "u3", "name": "neg", "av": 2, "pic": ""}], "outgoing": [], "blocked": []}"#).create();
        server.mock("GET", "/gc/api/name/check").match_query(Matcher::UrlEncoded("n".into(), "kian".into()))
            .with_body(r#"{"name": "kian", "ok": false, "error": "name_taken", "suggest": ["kian_1", "kian22"]}"#).create();
        let seen = server.mock("POST", "/gc/api/name/seen").with_body(r#"{"ok": true}"#).expect(1).create();
        server.mock("POST", "/gc/api/name").match_body(Matcher::Json(json!({ "name": "Tasi_9" })))
            .with_body(r#"{"name": "tasi_9", "name_next": 0, "name_hint": false}"#).create();
        let c = client(&server, &dir);

        let f = c.friends().unwrap();
        assert_eq!(f.friends.len(), 2);
        assert_eq!(f.friends[0].person.pic.as_deref(), Some(format!("{}/gc/pic/u1", server.url()).as_str()));
        assert!(f.friends[0].online);
        assert_eq!(f.friends[0].playing.as_deref(), Some("hokm"));
        assert_eq!((f.friends[1].person.av, f.friends[1].person.pic.clone()), (1, None));
        assert_eq!(f.incoming[0].name, "neg");

        let n = c.name_check("kian".into()).unwrap();
        assert!(!n.ok);
        assert_eq!(n.error.as_deref(), Some("name_taken"));
        assert_eq!(n.suggest, vec!["kian_1", "kian22"]);
        c.name_seen().unwrap();
        seen.assert();
        assert_eq!(c.set_name("Tasi_9".into()).unwrap(), "tasi_9");
    }

    fn client(server: &Server, dir: &tempfile::TempDir) -> Arc<Client> {
        Client::new(format!("{}/gc", server.url()), dir.path().to_string_lossy().into(), "Pixel 9".into())
    }

    #[test]
    fn guest_once_then_reused_and_saved() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        let guest = server
            .mock("POST", "/gc/app/guest")
            .match_body(Matcher::Json(json!({ "device": "Pixel 9" })))
            .with_body(r#"{"token":"g1"}"#)
            .expect(1)
            .create();
        let me = server.mock("GET", "/gc/api/me").match_header("x-gc-token", "g1").with_body(ME).expect(2).create();

        let c = client(&server, &dir);
        assert!(!c.has_session());
        let m = c.me().unwrap();
        c.me().unwrap();
        guest.assert();
        me.assert();

        assert_eq!(m.name, "tasi_42");
        assert_eq!(m.coins, 1250);
        assert_eq!(m.pic.as_deref(), Some(format!("{}/gc/pic/abc", server.url()).as_str()));
        assert_eq!(m.account, Account { kind: AccountKind::Email, email: Some("a@b.ir".into()) });
        assert_eq!(m.daily.plan, vec![10, 20, 30]);
        assert!(m.ranked_enabled);
        assert_eq!(m.active_match, None);
        assert_eq!((m.av, m.level.lv, m.name_hint), (5, 2, true));
        assert_eq!((m.requests, m.unread), (2, 7));
        assert_eq!(m.tables.len(), 2);
        assert_eq!((m.tables[0].kind.as_str(), m.tables[0].game.as_str(), m.tables[0].found, m.tables[0].need), ("queue", "hokm", 2, 4));
        assert_eq!(m.tables[1].id.as_deref(), Some("m1"));
        assert_eq!((m.cover.as_str(), m.max_cups, m.sound), ("gc", 120, true));
        assert_eq!((m.history.len(), m.history[0].amount, m.history[0].at), (1, 10, 1700000000));

        // برنامه دوباره باز شد: همان توکن از فایل
        assert!(client(&server, &dir).has_session());
    }

    #[test]
    fn expired_session_gets_new_guest_and_retries_once() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("old".into()));
        let stale = server.mock("GET", "/gc/api/me").match_header("x-gc-token", "old").with_status(401)
            .with_body(r#"{"error":"auth"}"#).expect(1).create();
        let guest = server.mock("POST", "/gc/app/guest").with_body(r#"{"token":"new"}"#).expect(1).create();
        let fresh = server.mock("GET", "/gc/api/me").match_header("x-gc-token", "new").with_body(ME).expect(1).create();

        assert_eq!(client(&server, &dir).me().unwrap().name, "tasi_42");
        stale.assert();
        guest.assert();
        fresh.assert();
    }

    #[test]
    fn server_error_codes() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("t".into()));
        server.mock("POST", "/gc/api/daily").with_status(400).with_body(r#"{"error":"daily_done"}"#).create();
        server.mock("GET", "/gc/api/friends").with_status(429).with_body(r#"{"error":"rate"}"#).create();
        server.mock("GET", "/gc/api/profile").with_status(500).with_body("oops").create();
        let c = client(&server, &dir);

        assert!(matches!(c.daily_claim(), Err(ApiError::Server { code, .. }) if code == "daily_done"));
        assert!(matches!(c.api_get("friends".into(), HashMap::new()), Err(ApiError::Rate)));
        assert!(matches!(c.api_get("profile".into(), HashMap::new()), Err(ApiError::Server { code, .. }) if code == "server"));
    }

    #[test]
    fn network_error() {
        let dir = tempfile::tempdir().unwrap();
        let c = Client::new("http://127.0.0.1:9/gc/".into(), dir.path().to_string_lossy().into(), "x".into());
        assert!(matches!(c.me(), Err(ApiError::Network { .. })));
    }

    #[test]
    fn email_login_replaces_token() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("guest".into()));
        server.mock("POST", "/gc/app/login/email").match_body(Matcher::Json(json!({ "email": "a@b.ir" })))
            .with_body(r#"{"ok":true,"email":"a@b.ir","ttl":600,"resend":60}"#).create();
        let verify = server.mock("POST", "/gc/app/login/email/verify").match_header("x-gc-token", "guest")
            .match_body(Matcher::Json(json!({ "email": "a@b.ir", "code": "123456", "device": "Pixel 9" })))
            .with_body(r#"{"token":"acct","account":{"kind":"email","email":"a@b.ir"}}"#).expect(1).create();
        let bad = server.mock("POST", "/gc/app/login/email/verify").match_body(Matcher::PartialJson(json!({ "code": "000000" })))
            .with_status(400).with_body(r#"{"error":"code_bad","left":3}"#).create();
        let c = client(&server, &dir);

        let sent = c.login_email_start(" a@b.ir ".into()).unwrap();
        assert_eq!((sent.ttl, sent.resend), (600, 60));
        match c.login_email_verify("a@b.ir".into(), "000000".into()) {
            Err(ApiError::Server { code, extra_json }) => {
                assert_eq!(code, "code_bad");
                assert!(extra_json.contains("\"left\":3"));
            }
            other => panic!("{other:?}"),
        }
        bad.assert();
        let acct = c.login_email_verify("a@b.ir".into(), "123456".into()).unwrap();
        verify.assert();
        assert_eq!(acct.kind, AccountKind::Email);
        assert_eq!(c.store.get().as_deref(), Some("acct"));
    }

    #[test]
    fn telegram_login_states() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        server.mock("POST", "/gc/app/login/tg")
            .with_body(r#"{"link":"https://t.me/asotas_bot?start=login_x","poll":"p1","ttl":600}"#).create();
        server.mock("POST", "/gc/app/login/tg/check").match_body(Matcher::Json(json!({ "poll": "p1" })))
            .with_body(r#"{"state":"wait"}"#).expect(1).create();
        server.mock("POST", "/gc/app/login/tg/check").match_body(Matcher::Json(json!({ "poll": "p2" })))
            .with_body(r#"{"state":"ok","token":"tg","account":{"kind":"telegram"}}"#).create();
        server.mock("POST", "/gc/app/login/tg/check").match_body(Matcher::Json(json!({ "poll": "p3" })))
            .with_body(r#"{"state":"no"}"#).create();
        let c = client(&server, &dir);

        let l = c.login_telegram_start().unwrap();
        assert!(l.link.starts_with("https://t.me/"));
        assert_eq!(c.login_telegram_check("p1".into()).unwrap().state, TelegramState::Waiting);
        assert_eq!(c.login_telegram_check("p3".into()).unwrap().state, TelegramState::Denied);
        assert!(!c.has_session());
        let ok = c.login_telegram_check("p2".into()).unwrap();
        assert_eq!(ok.state, TelegramState::Ok);
        assert_eq!(ok.account.map(|a| a.kind), Some(AccountKind::Telegram));
        assert_eq!(c.store.get().as_deref(), Some("tg"));
    }

    #[test]
    fn logout_clears_token() {
        let mut server = Server::new();
        let dir = tempfile::tempdir().unwrap();
        TokenStore::open(&dir.path().to_string_lossy()).set(Some("t".into()));
        let out = server.mock("POST", "/gc/app/logout").match_header("x-gc-token", "t").with_body(r#"{"ok":true}"#).expect(1).create();
        let c = client(&server, &dir);
        c.logout();
        out.assert();
        assert!(!c.has_session());
        assert!(!client(&server, &dir).has_session());
    }
}
