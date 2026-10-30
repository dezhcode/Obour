//! میزها: صف ناشناس، میز دعوت، لابی و خود بازی (service.py و ludo.py سرور).
//! صف و لابی برای همهٔ بازی ها یکی است؛ وضعیت هر بازی مدل خودش را دارد (فعلا منچ).

use std::collections::HashMap;

use serde_json::Value;

use crate::models::{int, text};

fn opt(v: &Value) -> Option<String> {
    Some(text(v)).filter(|s| !s.is_empty())
}

fn yes(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        _ => false,
    }
}

/// وضعیت صف ناشناس (queue_status)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct QueueState {
    /// none، waiting یا matched
    pub state: String,
    pub match_id: Option<String>,
    pub found: i64,
    pub need: i64,
    pub waited: i64,
    /// چند ثانیهٔ دیگر ربات ها جای خالی را پر می کنند (فقط دوستانه)
    pub bots_in: Option<i64>,
    pub can_bots: bool,
    /// free یا ranked
    pub mode: String,
}

impl QueueState {
    pub(crate) fn from_json(v: &Value) -> Self {
        QueueState {
            state: text(&v["state"]),
            match_id: opt(&v["match"]),
            found: int(&v["found"]),
            need: int(&v["need"]),
            waited: int(&v["waited"]),
            bots_in: if v["bots_in"].is_null() { None } else { Some(int(&v["bots_in"])) },
            can_bots: yes(&v["can_bots"]),
            mode: opt(&v["cfg"]["mode"]).unwrap_or_else(|| "free".into()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Invited {
    pub match_id: String,
    pub code: String,
    /// لینک t.me ربات (اگر ربات تنظیم شده باشد)
    pub link: String,
}

/// کسی که سر میز دعوت نشسته
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Seat {
    pub color: String,
    pub name: String,
    pub av: i64,
    pub pic: Option<String>,
    pub me: bool,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Lobby {
    pub seats: Vec<Seat>,
    pub code: String,
    pub host: bool,
    pub link: String,
}

/// پیام گفتگوی سر میز (tchat.js)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct TableChat {
    pub id: i64,
    /// رنگ (منچ) یا صندلی (حکم) فرستنده
    pub color: String,
    pub text: String,
    pub at: i64,
    pub name: String,
    pub av: i64,
    pub pic: Option<String>,
    pub me: bool,
    /// کلید عمومی فرستنده برای کارت پروفایل (برای خودم خالی)
    pub pid: String,
}

/// نتیجهٔ میز تمام شده برای من
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct MatchResult {
    pub won: bool,
    pub coins: i64,
    pub cups: i64,
    /// لیگ و جام کل بعد از این بازی (فقط بازی رتبه ای)
    pub league: Option<String>,
    pub total_cups: i64,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct LudoPlayer {
    pub name: String,
    pub av: i64,
    pub pic: Option<String>,
    pub bot: bool,
    pub out: bool,
    pub me: bool,
}

/// یک رویداد میز منچ (تاس، حرکت، زدن، بی حرکت، سه شش)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct LudoEvent {
    pub seq: i64,
    /// roll، move، nomove، six3، ...
    pub t: String,
    pub c: String,
    pub v: i64,
    pub k: i64,
    pub from: i64,
    pub to: i64,
    pub fin: bool,
    /// مهره هایی که زده شدند: رنگ و شماره
    pub caps: Vec<String>,
    /// تاس یا حرکت را خود سرور زد (وقت تمام شد)
    pub auto: bool,
    /// چرا رفت (leave): timeout یا left
    pub why: String,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct LudoGame {
    pub order: Vec<String>,
    pub players: HashMap<String, LudoPlayer>,
    /// جای هر مهره: -۱ لانه، ۰ تا ۵۰ مسیر، ۵۱ تا ۵۵ راهرو، ۵۶ خانه
    pub pawns: HashMap<String, Vec<i64>>,
    pub turn: Option<String>,
    /// roll یا move
    pub phase: String,
    pub dice: Option<i64>,
    pub movable: Vec<i64>,
    pub deadline_ms: i64,
    pub turn_ms: i64,
    pub last: HashMap<String, i64>,
    pub done: HashMap<String, i64>,
    pub events: Vec<LudoEvent>,
    pub seq: i64,
    pub over: bool,
    pub winner: Option<String>,
    /// آمار من در این بازی: مهره هایی که زدم و شش هایی که آوردم
    pub caps: i64,
    pub sixes: i64,
    /// زمان شروع بازی (ثانیهٔ یونیکس)
    pub started: f64,
}

/// بازیکن حکم (صندلی "0" تا "3"، تیم = صندلی ٪ ۲)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct HokmPlayer {
    pub name: String,
    pub av: i64,
    pub pic: Option<String>,
    pub bot: bool,
    pub out: bool,
    pub me: bool,
    pub team: i64,
    /// تعداد برگ های دستش
    pub count: i64,
}

/// برگی که سر میز آمده: صندلی و برگ (۰ تا ۵۱؛ خال = برگ / ۱۳، ارزش = برگ ٪ ۱۳)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct Played {
    pub seat: String,
    pub card: i64,
}

/// رویداد میز حکم (hakem، trump، play، trick، hand، win، end)
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct HokmEvent {
    pub seq: i64,
    pub t: String,
    pub c: String,
    pub suit: Option<i64>,
    pub card: Option<i64>,
    pub team: Option<i64>,
    pub pts: i64,
    pub kot: bool,
    /// آس کشی دست اول (hakem): برگ هایی که رو باز پخش شد تا اولین آس
    pub draw: Vec<Played>,
    /// حاکم دست قبل (hakem)، حاکم این دست (deal و hand)
    pub prev: Option<String>,
    pub hakem: Option<String>,
    /// شمارهٔ دست (از ۰)
    pub hand: i64,
    /// دورهای برده و امتیاز هر تیم (trick و hand)
    pub tricks: Vec<i64>,
    pub score: Vec<i64>,
    /// حکم یا برگ را خود سرور زد (وقت تمام شد)
    pub auto: bool,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct HokmGame {
    pub players: HashMap<String, HokmPlayer>,
    pub me: Option<String>,
    pub hand: Vec<i64>,
    /// trump، play، collect، handover یا over
    pub phase: String,
    pub turn: Option<String>,
    pub hakem: String,
    pub trump: Option<i64>,
    pub trick: Vec<Played>,
    pub led: Option<i64>,
    pub last_trick: Vec<Played>,
    pub last_winner: Option<String>,
    /// دورهای بردهٔ هر تیم در این دست
    pub tricks: Vec<i64>,
    /// دست های بردهٔ هر تیم
    pub score: Vec<i64>,
    pub target: i64,
    pub hand_no: i64,
    pub legal: Vec<i64>,
    pub deadline_ms: i64,
    pub turn_ms: i64,
    pub events: Vec<HokmEvent>,
    pub seq: i64,
    pub over: bool,
    pub winner: Option<i64>,
    /// آمار من: دورهایی که بردم و بارهایی که حاکم شدم
    pub won_tricks: i64,
    pub hakem_times: i64,
    /// زمان شروع بازی (ثانیهٔ یونیکس)
    pub started: f64,
}

fn played(v: &Value) -> Vec<Played> {
    v.as_array().map(|a| a.iter().map(|x| Played { seat: int(&x[0]).to_string(), card: int(&x[1]) }).collect()).unwrap_or_default()
}

fn opt_int(v: &Value) -> Option<i64> {
    if v.is_null() { None } else { Some(int(v)) }
}

impl HokmGame {
    fn from_json(g: &Value, pic: &impl Fn(&Value) -> Option<String>) -> Self {
        HokmGame {
            players: map(&g["players"], |p| HokmPlayer {
                name: text(&p["name"]),
                av: int(&p["av"]).max(1),
                pic: pic(&p["pic"]),
                bot: yes(&p["bot"]),
                out: yes(&p["out"]),
                me: yes(&p["me"]),
                team: int(&p["team"]),
                count: int(&p["count"]),
            }),
            me: opt(&g["me"]),
            hand: ints(&g["hand"]),
            phase: text(&g["phase"]),
            turn: opt(&g["turn"]),
            hakem: text(&g["hakem"]),
            trump: opt_int(&g["trump"]),
            trick: played(&g["trick"]),
            led: opt_int(&g["led"]),
            last_trick: played(&g["last_trick"]["cards"]),
            last_winner: opt(&g["last_trick"]["winner"]),
            tricks: ints(&g["tricks"]),
            score: ints(&g["score"]),
            target: int(&g["target"]),
            hand_no: int(&g["hand_no"]),
            legal: ints(&g["legal"]),
            deadline_ms: int(&g["deadline_ms"]),
            turn_ms: int(&g["turn_ms"]),
            events: g["events"].as_array().map(|a| a.iter().map(|e| HokmEvent {
                seq: int(&e["seq"]),
                t: text(&e["t"]),
                c: text(&e["c"]),
                suit: opt_int(&e["suit"]),
                card: opt_int(&e["card"]),
                team: opt_int(&e["team"]),
                pts: int(&e["pts"]),
                kot: yes(&e["kot"]),
                draw: played(&e["draw"]),
                prev: opt(&e["prev"]),
                hakem: opt(&e["hakem"]),
                hand: int(&e["hand"]),
                tricks: ints(&e["tricks"]),
                score: ints(&e["score"]),
                auto: yes(&e["auto"]),
            }).collect()).unwrap_or_default(),
            seq: int(&g["seq"]),
            over: yes(&g["over"]),
            winner: opt_int(&g["winner"]),
            won_tricks: int(&g["stats"]["tricks"]),
            hakem_times: int(&g["stats"]["hakem"]),
            started: g["started"].as_f64().unwrap_or(0.0),
        }
    }
}

/// `GET <game>/match`: میز (لابی یا بازی) از دید من
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct MatchView {
    pub id: String,
    /// lobby، playing، over یا cancelled
    pub status: String,
    pub me: Option<String>,
    pub players: i64,
    pub pawns: i64,
    pub mode: String,
    pub lobby: Option<Lobby>,
    pub ludo: Option<LudoGame>,
    pub hokm: Option<HokmGame>,
    /// هدف حکم (۳ یا ۷ دست)
    pub target: i64,
    pub result: Option<MatchResult>,
    /// پیام های تازهٔ گفتگوی میز (فقط وقتی با chat پرسیده شود)
    pub chat: Vec<TableChat>,
}

fn map<T>(v: &Value, f: impl Fn(&Value) -> T) -> HashMap<String, T> {
    v.as_object().map(|o| o.iter().map(|(k, x)| (k.clone(), f(x))).collect()).unwrap_or_default()
}

fn ints(v: &Value) -> Vec<i64> {
    v.as_array().map(|a| a.iter().map(int).collect()).unwrap_or_default()
}

impl MatchView {
    pub(crate) fn from_json(v: &Value, game: &str, resolve: &impl Fn(&str) -> String) -> Self {
        let pic = |p: &Value| opt(p).map(|u| resolve(&u));
        let lobby = v.get("lobby").filter(|l| l.is_object()).map(|l| Lobby {
            seats: l["seats"].as_array().map(|a| a.iter().map(|s| Seat {
                color: text(&s["color"]),
                name: text(&s["name"]),
                av: int(&s["av"]).max(1),
                pic: pic(&s["pic"]),
                me: yes(&s["me"]),
            }).collect()).unwrap_or_default(),
            code: text(&l["code"]),
            host: yes(&l["host"]),
            link: text(&l["link"]),
        });
        let g = &v["game"];
        let ludo = (game == "ludo" && g.is_object()).then(|| LudoGame {
            order: g["order"].as_array().map(|a| a.iter().map(text).collect()).unwrap_or_default(),
            players: map(&g["players"], |p| LudoPlayer {
                name: text(&p["name"]),
                av: int(&p["av"]).max(1),
                pic: pic(&p["pic"]),
                bot: yes(&p["bot"]),
                out: yes(&p["out"]),
                me: yes(&p["me"]),
            }),
            pawns: map(&g["pawns"], ints),
            turn: opt(&g["turn"]),
            phase: text(&g["phase"]),
            dice: if g["dice"].is_null() { None } else { Some(int(&g["dice"])) },
            movable: ints(&g["movable"]),
            deadline_ms: int(&g["deadline_ms"]),
            turn_ms: int(&g["turn_ms"]),
            last: map(&g["last"], int),
            done: map(&g["done"], int),
            events: g["events"].as_array().map(|a| a.iter().map(|e| LudoEvent {
                seq: int(&e["seq"]),
                t: text(&e["t"]),
                c: text(&e["c"]),
                v: int(&e["v"]),
                k: int(&e["k"]),
                from: int(&e["frm"]),
                to: int(&e["to"]),
                fin: yes(&e["fin"]),
                caps: e["cap"].as_array().map(|a| a.iter().map(|x| format!("{}:{}", text(&x[0]), int(&x[1])))
                    .collect()).unwrap_or_default(),
                auto: yes(&e["auto"]),
                why: text(&e["why"]),
            }).collect()).unwrap_or_default(),
            seq: int(&g["seq"]),
            over: yes(&g["over"]),
            winner: opt(&g["winner"]),
            caps: int(&g["stats"]["caps"]),
            sixes: int(&g["stats"]["sixes"]),
            started: g["started"].as_f64().unwrap_or(0.0),
        });
        let r = &v["result"];
        MatchView {
            id: text(&v["id"]),
            status: text(&v["status"]),
            me: opt(&v["me"]),
            players: int(&v["cfg"]["players"]),
            pawns: int(&v["cfg"]["pawns"]),
            mode: opt(&v["cfg"]["mode"]).unwrap_or_else(|| "free".into()),
            lobby,
            ludo,
            hokm: (game == "hokm" && g.is_object()).then(|| HokmGame::from_json(g, &pic)),
            target: int(&v["cfg"]["target"]),
            result: r.is_object().then(|| MatchResult {
                won: yes(&r["won"]),
                coins: int(&r["coins"]),
                cups: int(&r["cups"]),
                league: opt(&r["rank"]["league"]),
                total_cups: int(&r["rank"]["cups"]),
            }),
            chat: v["chat"].as_array().map(|a| a.iter().map(|m| TableChat {
                id: int(&m["id"]),
                color: text(&m["color"]),
                text: text(&m["text"]),
                at: int(&m["at"]),
                name: text(&m["name"]),
                av: int(&m["av"]).max(1),
                pic: pic(&m["pic"]),
                me: yes(&m["me"]),
                pid: text(&m["pid"]),
            }).collect()).unwrap_or_default(),
        }
    }
}
