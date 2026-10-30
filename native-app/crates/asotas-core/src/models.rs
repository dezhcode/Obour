//! داده هایی که به رابط کاربری می رسد. از JSON سرور با تحمل بالا خوانده می شود:
//! فیلدی که نباشد یا نوعش فرق کند مقدار پیش فرض می گیرد و صفحه از کار نمی افتد.

use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Enum)]
pub enum AccountKind {
    Guest,
    Email,
    Telegram,
}

/// حساب این گوشی: مهمان، ایمیل یا همان حساب مینی اپ تلگرام
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Account {
    pub kind: AccountKind,
    pub email: Option<String>,
}

/// جایزهٔ ورود روزانه: روز چندم پشت سر هم و سکهٔ هر روز
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Daily {
    pub claimed: bool,
    pub day: i64,
    pub next: i64,
    pub plan: Vec<i64>,
}

/// سطح بازیکن (همان level() در gc.js): هر بازی ۱۰ و هر برد ۱۵ تجربه؛ سطح بعد هر بار ۵۰ تجربه گران تر
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Level {
    pub lv: i64,
    pub xp: i64,
    /// تجربهٔ باقی تا سطح بعد
    pub left: i64,
    /// پیشرفت در همین سطح، ۰ تا ۱
    pub frac: f64,
}

/// میز باز کاربر برای «میزای دیگه‌ت» در خانه (service.my_tables)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct TableInfo {
    /// queue (در صف)، lobby (منتظر بازیکن) یا playing
    pub kind: String,
    pub game: String,
    pub id: Option<String>,
    pub found: i64,
    pub need: i64,
    /// نوبت من است (فقط بازی در جریان)
    pub my_turn: bool,
    /// سازندهٔ میز دعوت منم
    pub host: bool,
}

/// خلاصهٔ `GET /gc/api/me` برای صفحهٔ خانه
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Me {
    pub name: String,
    /// آدرس کامل عکس پروفایل (یا None)
    pub pic: Option<String>,
    /// شمارهٔ رنگ آواتار (av)
    pub av: i64,
    /// سکه (فیلد points سرور)
    pub coins: i64,
    pub games: i64,
    pub wins: i64,
    pub level: Level,
    pub bio: String,
    pub joined: i64,
    /// یوزرنیم تازه هنوز به کاربر نشان داده نشده (کارت «اسمت تو بازی اینه»)
    pub name_hint: bool,
    pub account: Account,
    pub daily: Daily,
    /// درخواست های دوستی تازه و پیام های خوانده نشده
    pub requests: i64,
    pub unread: i64,
    pub tables: Vec<TableInfo>,
    /// کاور پروفایل (gc) و همهٔ کاورها
    pub cover: String,
    /// دست های حکم هفت به صفر (برای نشان ها)
    pub kots: i64,
    /// بیشترین جام در یکی از بازی های رتبه ای (نشان لیگ)
    pub max_cups: i64,
    pub sound: bool,
    /// تاریخچهٔ سکه
    pub history: Vec<Ledger>,
    pub banned: bool,
    pub maintenance: bool,
    pub notice: String,
    pub ranked_enabled: bool,
    pub active_match: Option<String>,
    pub active_game: Option<String>,
}

/// یک بازیکن دیگر (social.public)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Person {
    pub uid: String,
    pub name: String,
    pub av: i64,
    pub pic: Option<String>,
    pub bio: String,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Friend {
    pub person: Person,
    pub online: bool,
    /// بازی که الان سرش است (hokm، ludo، ...) یا None
    pub playing: Option<String>,
    /// آخرین بار آنلاین (ثانیهٔ یونیکس)
    pub seen: i64,
    pub unread: i64,
}

/// کارت یک بازیکن (friends/find و friends/user): همان آدم، کارنامه و وضعیت، و رابطه با من
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct UserCard {
    pub person: Person,
    pub games: i64,
    pub wins: i64,
    pub joined: i64,
    pub online: bool,
    pub playing: Option<String>,
    pub seen: i64,
    /// none، outgoing، incoming، friend، blocked یا self
    pub relation: String,
}

/// یک پیام خصوصی؛ دعوت به بازی بازی و کد میز را هم دارد
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct DmMessage {
    pub id: i64,
    pub me: bool,
    /// text یا invite
    pub kind: String,
    pub text: String,
    pub at: i64,
    pub game: Option<String>,
    pub code: Option<String>,
    /// شناسهٔ میز دعوت
    pub match_id: Option<String>,
}

/// `GET dm`: طرف گفتگو، رابطه و پیام ها
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct DmChat {
    pub user: Friend,
    pub relation: String,
    pub messages: Vec<DmMessage>,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct GameInvite {
    pub match_id: String,
    pub code: String,
    pub game: String,
}

/// یک طرح میز یا ورق حکم در فروشگاه
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct StyleItem {
    pub id: String,
    /// table یا cards
    pub kind: String,
    pub look: String,
    pub name: String,
    pub price: i64,
    pub owned: bool,
    pub on: bool,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Styles {
    pub items: Vec<StyleItem>,
    pub table: String,
    pub cards: String,
    pub points: i64,
}

/// یک ردیف تاریخچهٔ سکه
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Ledger {
    pub kind: String,
    pub amount: i64,
    pub note: String,
    pub status: String,
    pub at: i64,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct GameStat {
    pub game: String,
    pub games: i64,
    pub wins: i64,
    pub prize: i64,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct RecentGame {
    pub game: String,
    pub won: bool,
    pub prize: i64,
    pub at: i64,
    pub cups: i64,
    /// free، ranked یا stake
    pub mode: String,
}

/// `GET profile`: کارنامهٔ هر بازی و آخرین بازی ها
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Profile {
    pub games: Vec<GameStat>,
    pub recent: Vec<RecentGame>,
}

/// `GET /gc/api/friends`
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Friends {
    pub friends: Vec<Friend>,
    pub incoming: Vec<Person>,
    pub outgoing: Vec<Person>,
    pub blocked: Vec<Person>,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct DailyClaim {
    /// سکه ای که همین الان گرفت
    pub coins: i64,
    /// موجودی تازه
    pub balance: i64,
    pub daily: Daily,
}

/// شروع ورود با تلگرام: لینک ربات را باز کن و هر ۲ ثانیه `poll` را بپرس
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct TelegramLogin {
    pub link: String,
    pub poll: String,
    pub ttl: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Enum)]
pub enum TelegramState {
    /// هنوز در تلگرام تأیید نشده
    Waiting,
    /// تأیید شد؛ توکن تازه ذخیره شد
    Ok,
    /// در تلگرام «نه» زد
    Denied,
    /// وقت لینک تمام شد
    Expired,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct TelegramCheck {
    pub state: TelegramState,
    pub account: Option<Account>,
}

/// `GET name/check`: یوزرنیم پیشنهادی قبول است یا نه (و اگر گرفته شده، چند پیشنهاد)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct NameCheck {
    pub name: String,
    pub ok: bool,
    pub error: Option<String>,
    pub suggest: Vec<String>,
}

impl NameCheck {
    pub(crate) fn from_json(v: &Value) -> Self {
        NameCheck {
            name: text(&v["name"]),
            ok: truthy(&v["ok"]),
            error: opt_text(&v["error"]),
            suggest: v["suggest"].as_array().map(|a| a.iter().map(text).collect()).unwrap_or_default(),
        }
    }
}

/// کد ۶ رقمی فرستاده شد
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct EmailCode {
    pub email: String,
    /// اعتبار کد (ثانیه)
    pub ttl: i64,
    /// چند ثانیه بعد می شود کد تازه خواست
    pub resend: i64,
}

/// پاپ آپ پنل مدیریت (gate.popup_view)؛ با باز شدن برنامه نشان داده می شود
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Popup {
    /// نسخه: هر بار ادمین ذخیره کند بالا می رود؛ هر نسخه یک بار دیده می شود
    pub v: i64,
    pub title: String,
    pub text: String,
    pub img: Option<String>,
    /// دکمه (برچسب و لینک)؛ هر دو باید باشند
    pub btn: String,
    pub url: String,
    /// once (یک بار) یا always (هر بار باز شدن برنامه)
    pub mode: String,
}

impl Popup {
    pub(crate) fn from_json(v: &Value, resolve: impl Fn(&str) -> String) -> Option<Self> {
        if !v.is_object() {
            return None;
        }
        Some(Popup {
            v: int(&v["v"]),
            title: text(&v["title"]),
            text: text(&v["text"]),
            img: opt_text(&v["img"]).map(|u| resolve(&u)),
            btn: text(&v["btn"]),
            url: text(&v["url"]),
            mode: opt_text(&v["mode"]).unwrap_or_else(|| "once".into()),
        })
    }
}

/// دکمهٔ زیر پیام صندوق: صفحهٔ مینی اپ (خالی = خانه، ludo-lobby.html، shop.html ...)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct InboxButton {
    pub page: String,
    pub label: String,
}

/// پیام صندوق: همگانی (broadcast) یا مستقیم از ادمین (admin)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct InboxItem {
    pub id: String,
    pub kind: String,
    pub text: String,
    pub img: Option<String>,
    pub buttons: Vec<InboxButton>,
    pub at: i64,
}

impl InboxItem {
    pub(crate) fn from_json(v: &Value, resolve: &impl Fn(&str) -> String) -> Self {
        InboxItem {
            id: text(&v["id"]),
            kind: text(&v["kind"]),
            text: text(&v["text"]),
            img: opt_text(&v["img"]).map(|u| resolve(&u)),
            buttons: v["buttons"].as_array().map(|a| a.iter().map(|b| InboxButton { page: text(&b["page"]), label: text(&b["label"]) }).collect())
                .unwrap_or_default(),
            at: int(&v["at"]),
        }
    }
}

// ---------- خواندن JSON با تحمل ----------

pub(crate) fn int(v: &Value) -> i64 {
    v.as_i64()
        .or_else(|| v.as_f64().map(|f| f as i64))
        .or_else(|| v.as_str().and_then(|s| s.trim().parse().ok()))
        .or_else(|| v.as_bool().map(i64::from))
        .unwrap_or(0)
}

pub(crate) fn text(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        _ => String::new(),
    }
}

fn opt_text(v: &Value) -> Option<String> {
    Some(text(v)).filter(|s| !s.is_empty())
}

fn truthy(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
        Value::Null => false,
    }
}

impl Account {
    pub(crate) fn from_json(v: &Value) -> Self {
        let kind = match v["kind"].as_str() {
            Some("telegram") => AccountKind::Telegram,
            Some("email") => AccountKind::Email,
            _ => AccountKind::Guest,
        };
        Account { kind, email: opt_text(&v["email"]) }
    }
}

impl Daily {
    pub(crate) fn from_json(v: &Value) -> Self {
        Daily {
            claimed: truthy(&v["claimed"]),
            day: int(&v["day"]),
            next: int(&v["next"]),
            plan: v["plan"].as_array().map(|a| a.iter().map(int).collect()).unwrap_or_default(),
        }
    }
}

#[uniffi::export]
pub fn level(games: i64, wins: i64) -> Level {
    let xp = games.max(0) * 10 + wins.max(0) * 15;
    let (mut lv, mut base, mut need) = (1, 0, 100);
    while xp >= base + need {
        base += need;
        lv += 1;
        need = 100 + (lv - 1) * 50;
    }
    Level { lv, xp, left: base + need - xp, frac: (xp - base) as f64 / need as f64 }
}

impl TableInfo {
    fn from_json(v: &Value) -> Self {
        TableInfo {
            kind: text(&v["kind"]),
            game: text(&v["game"]),
            id: opt_text(&v["id"]),
            found: int(&v["found"]),
            need: int(&v["need"]),
            my_turn: truthy(&v["my_turn"]),
            host: truthy(&v["host"]),
        }
    }
}

impl Person {
    pub(crate) fn from_json(v: &Value, resolve: &impl Fn(&str) -> String) -> Self {
        Person {
            uid: text(&v["uid"]),
            name: text(&v["name"]),
            av: int(&v["av"]).max(1),
            pic: opt_text(&v["pic"]).map(|u| resolve(&u)),
            bio: text(&v["bio"]),
        }
    }
}

fn list<T>(v: &Value, f: impl Fn(&Value) -> T) -> Vec<T> {
    v.as_array().map(|a| a.iter().map(f).collect()).unwrap_or_default()
}

impl Friend {
    pub(crate) fn from_json(f: &Value, resolve: &impl Fn(&str) -> String) -> Self {
        Friend {
            person: Person::from_json(f, resolve),
            online: truthy(&f["online"]),
            playing: opt_text(&f["playing"]),
            seen: int(&f["seen"]),
            unread: int(&f["unread"]),
        }
    }
}

impl UserCard {
    pub(crate) fn from_json(v: &Value, resolve: &impl Fn(&str) -> String) -> Self {
        let u = &v["user"];
        UserCard {
            person: Person::from_json(u, resolve),
            games: int(&u["games"]),
            wins: int(&u["wins"]),
            joined: int(&u["joined"]),
            online: truthy(&u["online"]),
            playing: opt_text(&u["playing"]),
            seen: int(&u["seen"]),
            relation: text(&v["relation"]),
        }
    }
}

impl DmChat {
    pub(crate) fn from_json(v: &Value, resolve: &impl Fn(&str) -> String) -> Self {
        DmChat {
            user: Friend::from_json(&v["user"], resolve),
            relation: text(&v["relation"]),
            messages: list(&v["messages"], |m| DmMessage {
                id: int(&m["id"]),
                me: truthy(&m["me"]),
                kind: text(&m["kind"]),
                text: text(&m["text"]),
                at: int(&m["at"]),
                game: opt_text(&m["meta"]["game"]),
                code: opt_text(&m["meta"]["code"]),
                match_id: opt_text(&m["meta"]["match"]),
            }),
        }
    }
}

impl Styles {
    pub(crate) fn from_json(v: &Value) -> Self {
        Styles {
            items: list(&v["items"], |i| StyleItem {
                id: text(&i["id"]),
                kind: text(&i["kind"]),
                look: text(&i["look"]),
                name: text(&i["name"]),
                price: int(&i["price"]),
                owned: truthy(&i["owned"]),
                on: truthy(&i["on"]),
            }),
            table: text(&v["table"]),
            cards: text(&v["cards"]),
            points: int(&v["points"]),
        }
    }
}

impl Profile {
    pub(crate) fn from_json(v: &Value) -> Self {
        Profile {
            games: list(&v["games"], |g| GameStat { game: text(&g["game"]), games: int(&g["games"]), wins: int(&g["wins"]), prize: int(&g["prize"]) }),
            recent: list(&v["recent"], |r| RecentGame {
                game: text(&r["game"]),
                won: truthy(&r["won"]),
                prize: int(&r["prize"]),
                at: int(&r["at"]),
                cups: int(&r["cups"]),
                mode: opt_text(&r["mode"]).unwrap_or_else(|| "free".into()),
            }),
        }
    }
}

impl Friends {
    pub(crate) fn from_json(v: &Value, resolve: impl Fn(&str) -> String) -> Self {
        let people = |k: &str| -> Vec<Person> {
            v[k].as_array().map(|a| a.iter().map(|p| Person::from_json(p, &resolve)).collect()).unwrap_or_default()
        };
        let friends = list(&v["friends"], |f| Friend::from_json(f, &resolve));
        Friends { friends, incoming: people("incoming"), outgoing: people("outgoing"), blocked: people("blocked") }
    }
}

impl Me {
    /// `resolve` آدرس نسبی عکس (pic/...) را کامل می کند
    pub(crate) fn from_json(v: &Value, resolve: impl Fn(&str) -> String) -> Self {
        let p = &v["player"];
        let (games, wins) = (int(&p["games"]), int(&p["wins"]));
        Me {
            name: text(&p["name"]),
            pic: opt_text(&p["pic"]).map(|u| resolve(&u)),
            av: int(&p["av"]).max(1),
            coins: int(&p["points"]),
            games,
            wins,
            level: level(games, wins),
            bio: text(&p["bio"]),
            joined: int(&p["joined"]),
            name_hint: truthy(&p["name_hint"]),
            account: Account::from_json(&v["account"]),
            daily: Daily::from_json(&v["daily"]),
            requests: int(&v["social"]["requests"]),
            unread: int(&v["social"]["unread"]),
            tables: list(&v["tables"], TableInfo::from_json),
            cover: opt_text(&p["cover"]).unwrap_or_else(|| "gc".into()),
            kots: int(&p["kots"]),
            max_cups: v["ranks"].as_object().map(|o| o.values().map(|r| int(&r["cups"])).max().unwrap_or(0)).unwrap_or(0).max(0),
            sound: p.get("sound").map(truthy).unwrap_or(true),
            history: list(&v["history"], |l| Ledger {
                kind: text(&l["kind"]),
                amount: int(&l["amount"]),
                note: text(&l["note"]),
                status: text(&l["status"]),
                at: int(&l["created_at"]),
            }),
            banned: truthy(&v["banned"]),
            maintenance: truthy(&v["maintenance"]),
            notice: text(&v["notice"]),
            ranked_enabled: truthy(&v["settings"]["ranked"]),
            active_match: opt_text(&v["active_match"]),
            active_game: opt_text(&v["active_game"]),
        }
    }
}

impl TelegramState {
    pub(crate) fn from_str(s: &str) -> Self {
        match s {
            "ok" => TelegramState::Ok,
            "expired" => TelegramState::Expired,
            "no" | "denied" | "rejected" => TelegramState::Denied,
            _ => TelegramState::Waiting,
        }
    }
}
