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

/// خلاصهٔ `GET /gc/api/me` برای صفحهٔ خانه
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Me {
    pub name: String,
    /// آدرس کامل عکس پروفایل (یا None)
    pub pic: Option<String>,
    /// سکه (فیلد points سرور)
    pub coins: i64,
    pub games: i64,
    pub wins: i64,
    pub bio: String,
    pub joined: i64,
    pub account: Account,
    pub daily: Daily,
    pub banned: bool,
    pub maintenance: bool,
    pub notice: String,
    pub ranked_enabled: bool,
    pub active_match: Option<String>,
    pub active_game: Option<String>,
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

/// کد ۶ رقمی فرستاده شد
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct EmailCode {
    pub email: String,
    /// اعتبار کد (ثانیه)
    pub ttl: i64,
    /// چند ثانیه بعد می شود کد تازه خواست
    pub resend: i64,
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

impl Me {
    /// `resolve` آدرس نسبی عکس (pic/...) را کامل می کند
    pub(crate) fn from_json(v: &Value, resolve: impl Fn(&str) -> String) -> Self {
        let p = &v["player"];
        Me {
            name: text(&p["name"]),
            pic: opt_text(&p["pic"]).map(|u| resolve(&u)),
            coins: int(&p["points"]),
            games: int(&p["games"]),
            wins: int(&p["wins"]),
            bio: text(&p["bio"]),
            joined: int(&p["joined"]),
            account: Account::from_json(&v["account"]),
            daily: Daily::from_json(&v["daily"]),
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
