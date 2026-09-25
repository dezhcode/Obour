"""حداقل لازم برای کار با شبکه TON، بدون کتابخانه بیرونی.

کتابخانه های پایتونی TON (pytoniq، tonsdk و ...) وابستگی های کامپایلی
دارند (PyNaCl، bitarray و ...) که روی هاست سی پنل نصبشان دردسر است. ما
فقط چهار کار لازم داریم و هر چهار کوچک اند:

1. خواندن و ساختن آدرس (شکل خام 0:hex و شکل کاربرپسند UQ.../EQ...)
2. ساختن سلول (Cell) و سریال کردنش به BOC؛ برای کامنت و انتقال جتون
3. خواندن BOC که Toncenter برمی گرداند (بدنه پیام های ورودی)
4. خواندن کامنت متنی و بدنه internal_transfer جتون از آن سلول ها

هش سلول لازم نیست: ما قرارداد نمی سازیم و امضا نمی کنیم؛ کیف پول کاربر
امضا می کند و فقط بدنه پیام را از ما می گیرد.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

# ═══════════════════ آدرس ═══════════════════

_BOUNCEABLE = 0x11
_NON_BOUNCEABLE = 0x51
_TESTNET = 0x80


class TonError(ValueError):
    """آدرس یا BOC خراب."""


def _crc16(data: bytes) -> int:
    """CRC16-XMODEM، همان که در آخر آدرس کاربرپسند TON می آید."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


@dataclass(frozen=True)
class Address:
    workchain: int
    hash: bytes  # ۳۲ بایت

    @classmethod
    def parse(cls, text: str) -> "Address":
        """0:hex یا شکل کاربرپسند (base64 یا base64url، ۴۸ نویسه)."""
        s = (text or "").strip()
        if ":" in s:
            wc, _, hx = s.partition(":")
            try:
                h = bytes.fromhex(hx)
                w = int(wc)
            except ValueError as exc:
                raise TonError("آدرس خام نامعتبر") from exc
            if len(h) != 32 or w not in (0, -1):
                raise TonError("آدرس خام نامعتبر")
            return cls(w, h)
        if len(s) != 48:
            raise TonError("طول آدرس نامعتبر")
        try:
            raw = base64.urlsafe_b64decode(s.replace("+", "-").replace("/", "_"))
        except Exception as exc:  # noqa: BLE001
            raise TonError("آدرس نامعتبر") from exc
        if len(raw) != 36 or _crc16(raw[:34]) != int.from_bytes(raw[34:], "big"):
            raise TonError("چک سام آدرس نمی خواند")
        tag = raw[0] & ~_TESTNET
        if tag not in (_BOUNCEABLE, _NON_BOUNCEABLE):
            raise TonError("نوع آدرس نامعتبر")
        wc = raw[1] - 256 if raw[1] > 127 else raw[1]
        return cls(wc, raw[2:34])

    @property
    def raw(self) -> str:
        return f"{self.workchain}:{self.hash.hex()}"

    def friendly(self, *, bounceable: bool = False, testnet: bool = False) -> str:
        """UQ/EQ برای mainnet و 0Q/kQ برای testnet.

        برای کیف پول ها شکل non-bounceable (UQ) درست است: اگر کیف پول
        هنوز فعال نشده باشد، پیام bounceable پس زده می شود و پول برمی گردد.
        """
        tag = _BOUNCEABLE if bounceable else _NON_BOUNCEABLE
        if testnet:
            tag |= _TESTNET
        body = bytes([tag, self.workchain & 0xFF]) + self.hash
        return base64.urlsafe_b64encode(body + _crc16(body).to_bytes(2, "big")).decode()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Address) and (self.workchain, self.hash) == (other.workchain, other.hash)

    def __hash__(self) -> int:
        return hash((self.workchain, self.hash))


def same_address(a: str | None, b: str | None) -> bool:
    try:
        return Address.parse(a or "") == Address.parse(b or "")
    except TonError:
        return False


# ═══════════════════ سلول ═══════════════════


@dataclass
class Cell:
    bits: str = ""          # رشته ای از "0" و "1"؛ ساده و برای این اندازه کافی
    refs: list["Cell"] = field(default_factory=list)

    # ---------- سریال ----------
    def _descriptor_and_data(self) -> bytes:
        n = len(self.bits)
        d1 = len(self.refs)
        d2 = (n // 8) + ((n + 7) // 8)
        padded = self.bits
        if n % 8:
            padded += "1" + "0" * (7 - n % 8)
        data = int(padded, 2).to_bytes(len(padded) // 8, "big") if padded else b""
        return bytes([d1, d2]) + data

    def to_boc(self) -> str:
        """BOC با یک ریشه، بدون index و crc (کیف پول ها همین را می پذیرند)."""
        # BOC ترتیب توپولوژیک می خواهد: هر ارجاع به سلولی با شماره بزرگ تر.
        # عکسِ ترتیب پس ترتیبی DFS همین را می دهد، حتی اگر یک سلول در چند
        # جا تکرار شده باشد.
        post: list[Cell] = []
        done: set[int] = set()

        def visit(c: "Cell") -> None:
            if id(c) in done:
                return
            done.add(id(c))
            for r in c.refs:
                visit(r)
            post.append(c)

        visit(self)
        order = post[::-1]
        seen = {id(c): i for i, c in enumerate(order)}
        count = len(order)
        ref_size = max(1, (count.bit_length() + 7) // 8)
        payload = b""
        for c in order:
            payload += c._descriptor_and_data()
            for r in c.refs:
                payload += seen[id(r)].to_bytes(ref_size, "big")
        off_size = max(1, (len(payload).bit_length() + 7) // 8)
        out = bytes.fromhex("b5ee9c72")
        out += bytes([ref_size])            # flags=0 (بدون idx و crc) + size
        out += bytes([off_size])
        out += count.to_bytes(ref_size, "big")   # cells
        out += (1).to_bytes(ref_size, "big")     # roots
        out += (0).to_bytes(ref_size, "big")     # absent
        out += len(payload).to_bytes(off_size, "big")
        out += (0).to_bytes(ref_size, "big")     # شماره ریشه
        out += payload
        return base64.b64encode(out).decode()

    # ---------- خواندن ----------
    @classmethod
    def from_boc(cls, b64: str) -> "Cell":
        try:
            data = base64.b64decode(b64 + "=" * (-len(b64) % 4))
        except Exception as exc:  # noqa: BLE001
            raise TonError("BOC نامعتبر") from exc
        if data[:4] != bytes.fromhex("b5ee9c72"):
            raise TonError("سرآیند BOC پشتیبانی نمی شود")
        flags = data[4]
        has_idx = bool(flags & 0x80)
        size = flags & 0x07
        off_size = data[5]
        p = 6

        def take(n: int) -> int:
            nonlocal p
            v = int.from_bytes(data[p:p + n], "big")
            p += n
            return v

        cells_n = take(size)
        roots_n = take(size)
        take(size)                       # absent
        tot = take(off_size)
        roots = [take(size) for _ in range(roots_n)]
        if has_idx:
            p += cells_n * off_size
        end = p + tot
        raw: list[tuple[str, list[int]]] = []
        while p < end and len(raw) < cells_n:
            d1, d2 = data[p], data[p + 1]
            p += 2
            nrefs = d1 & 7
            if d1 & 8:
                raise TonError("سلول exotic پشتیبانی نمی شود")
            nbytes = (d2 + 1) // 2
            chunk = data[p:p + nbytes]
            p += nbytes
            bits = "".join(f"{b:08b}" for b in chunk)
            if d2 % 2:  # بایت آخر ناقص است: تا آخرین ۱ بریده می شود
                bits = bits[: len(bits.rstrip("0")) - 1]
            refs = [take(size) for _ in range(nrefs)]
            raw.append((bits, refs))
        if len(raw) != cells_n or not roots:
            raise TonError("BOC ناقص")
        built: list[Cell | None] = [None] * cells_n
        for i in range(cells_n - 1, -1, -1):
            bits, refs = raw[i]
            built[i] = cls(bits, [built[r] for r in refs])  # type: ignore[misc]
        return built[roots[0]]  # type: ignore[return-value]

    def slice(self) -> "Slice":
        return Slice(self)


class Builder:
    def __init__(self) -> None:
        self.bits: list[str] = []
        self.refs: list[Cell] = []

    def uint(self, value: int, n: int) -> "Builder":
        if value < 0 or value >= (1 << n):
            raise TonError("عدد در این تعداد بیت جا نمی شود")
        if n:
            self.bits.append(format(value, f"0{n}b"))
        return self

    def int_(self, value: int, n: int) -> "Builder":
        return self.uint(value & ((1 << n) - 1), n)

    def bit(self, v: bool) -> "Builder":
        self.bits.append("1" if v else "0")
        return self

    def coins(self, value: int) -> "Builder":
        """VarUInteger 16: طول به بایت در ۴ بیت، بعد خود عدد."""
        if value == 0:
            return self.uint(0, 4)
        n = (value.bit_length() + 7) // 8
        return self.uint(n, 4).uint(value, n * 8)

    def address(self, addr: Address | None) -> "Builder":
        if addr is None:
            return self.uint(0, 2)       # addr_none
        return self.uint(0b100, 3).int_(addr.workchain, 8).uint(int.from_bytes(addr.hash, "big"), 256)

    def raw_bytes(self, b: bytes) -> "Builder":
        for byte in b:
            self.uint(byte, 8)
        return self

    def ref(self, cell: Cell) -> "Builder":
        if len(self.refs) >= 4:
            raise TonError("سلول بیش از ۴ ارجاع ندارد")
        self.refs.append(cell)
        return self

    def end(self) -> Cell:
        bits = "".join(self.bits)
        if len(bits) > 1023:
            raise TonError("سلول بیش از ۱۰۲۳ بیت")
        return Cell(bits, list(self.refs))


class Slice:
    def __init__(self, cell: Cell) -> None:
        self.cell = cell
        self.pos = 0
        self.ref_pos = 0

    @property
    def remaining(self) -> int:
        return len(self.cell.bits) - self.pos

    def uint(self, n: int) -> int:
        if self.remaining < n:
            raise TonError("سلول کوتاه است")
        v = int(self.cell.bits[self.pos:self.pos + n] or "0", 2)
        self.pos += n
        return v

    def int_(self, n: int) -> int:
        v = self.uint(n)
        return v - (1 << n) if n and v >> (n - 1) else v

    def bit(self) -> bool:
        return bool(self.uint(1))

    def coins(self) -> int:
        n = self.uint(4)
        return self.uint(n * 8) if n else 0

    def address(self) -> Address | None:
        kind = self.uint(2)
        if kind == 0:
            return None
        if kind != 0b10:
            raise TonError("نوع آدرس پشتیبانی نمی شود")
        if self.bit():                   # anycast
            raise TonError("anycast پشتیبانی نمی شود")
        wc = self.int_(8)
        return Address(wc, self.uint(256).to_bytes(32, "big"))

    def ref(self) -> Cell:
        if self.ref_pos >= len(self.cell.refs):
            raise TonError("ارجاع کم است")
        c = self.cell.refs[self.ref_pos]
        self.ref_pos += 1
        return c

    def rest_bytes(self) -> bytes:
        n = self.remaining - self.remaining % 8
        out = self.uint(n).to_bytes(n // 8, "big") if n else b""
        return out


# ═══════════════════ پیام ها ═══════════════════

OP_COMMENT = 0
OP_JETTON_TRANSFER = 0x0F8A7EA5
OP_JETTON_INTERNAL_TRANSFER = 0x178D4519


def comment_cell(text: str) -> Cell:
    """کامنت متنی: ۳۲ بیت صفر و بعد متن UTF-8 (زنجیره ای اگر بلند باشد)."""
    data = text.encode("utf-8")
    first = 127 - 4                      # ۱۲۷ بایت جا، ۴ بایت برای op
    chunks = [data[:first]] + [data[i:i + 127] for i in range(first, len(data), 127)]
    tail: Cell | None = None
    for i in range(len(chunks) - 1, -1, -1):
        b = Builder()
        if i == 0:
            b.uint(OP_COMMENT, 32)
        b.raw_bytes(chunks[i])
        if tail is not None:
            b.ref(tail)
        tail = b.end()
    return tail  # type: ignore[return-value]


def read_snake_text(s: Slice) -> str:
    out = s.rest_bytes()
    cell = s.cell
    idx = s.ref_pos
    while idx < len(cell.refs):
        cell = cell.refs[idx]
        idx = 0
        sl = cell.slice()
        out += sl.rest_bytes()
    return out.decode("utf-8", errors="replace")


def read_comment(cell: Cell | None) -> str | None:
    """اگر سلول یک کامنت متنی باشد متنش، وگرنه None."""
    if cell is None:
        return None
    try:
        s = cell.slice()
        if s.remaining < 32 or s.uint(32) != OP_COMMENT:
            return None
        return read_snake_text(s)
    except TonError:
        return None


def jetton_transfer_body(
    *,
    amount: int,
    destination: Address,
    response: Address,
    comment: str,
    forward_ton: int = 1,
    query_id: int = 0,
) -> Cell:
    """بدنه transfer استاندارد TEP-74 که به کیف پول جتونِ خودِ کاربر می رود."""
    return (
        Builder()
        .uint(OP_JETTON_TRANSFER, 32)
        .uint(query_id, 64)
        .coins(amount)
        .address(destination)
        .address(response)
        .bit(False)                      # custom_payload: هیچ
        .coins(forward_ton)
        .bit(True)                       # forward_payload در ارجاع
        .ref(comment_cell(comment))
        .end()
    )


@dataclass
class JettonIn:
    amount: int
    sender: Address | None
    comment: str | None


def read_internal_transfer(cell: Cell) -> JettonIn | None:
    """بدنه internal_transfer که به کیف پول جتون ما رسیده.

    این پیام فقط وقتی پذیرفته می شود (تراکنش aborted نمی شود) که از یک
    کیف پول جتون همان مستر آمده باشد؛ پس اگر تراکنش موفق بوده، مبلغ و
    کامنتش واقعی است.
    """
    try:
        s = cell.slice()
        if s.uint(32) != OP_JETTON_INTERNAL_TRANSFER:
            return None
        s.uint(64)
        amount = s.coins()
        sender = s.address()
        s.address()                      # response_address
        s.coins()                        # forward_ton_amount
        comment = None
        if s.remaining >= 1:
            if s.bit():
                comment = read_comment(s.ref())
            elif s.remaining >= 32:
                if s.uint(32) == OP_COMMENT:
                    comment = read_snake_text(s)
        return JettonIn(amount, sender, comment)
    except TonError:
        return None


def address_slice_boc(addr: Address) -> str:
    """آدرس داخل یک سلول؛ ورودی get_wallet_address مستر جتون."""
    return Builder().address(addr).end().to_boc()


def address_from_boc(b64: str) -> Address | None:
    try:
        return Cell.from_boc(b64).slice().address()
    except (TonError, IndexError):
        return None
