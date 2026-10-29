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
        "tables": [{"kind": "queue", "game": "hokm", "found": 2, "need": 4},
                   {"kind": "playing", "id": "m1", "game": "ludo", "players": []}],
        "banned": false, "maintenance": false, "notice": "",
        "settings": {"ranked": true},
        "active_match": null, "active_game": null
    }"#;

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
