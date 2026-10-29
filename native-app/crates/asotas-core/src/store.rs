//! توکن نشست روی گوشی (فایل `session.json` در پوشهٔ خصوصی برنامه).

use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

#[derive(Default, Serialize, Deserialize)]
struct Saved {
    token: String,
}

pub(crate) struct TokenStore {
    path: PathBuf,
    token: Mutex<Option<String>>,
}

impl TokenStore {
    pub fn open(dir: &str) -> Self {
        let path = PathBuf::from(dir).join("session.json");
        let token = fs::read_to_string(&path)
            .ok()
            .and_then(|s| serde_json::from_str::<Saved>(&s).ok())
            .map(|s| s.token)
            .filter(|t| !t.is_empty());
        TokenStore { path, token: Mutex::new(token) }
    }

    pub fn get(&self) -> Option<String> {
        self.token.lock().unwrap().clone()
    }

    /// توکن تازه (یا None برای خروج). اول در فایل موقت و بعد جابه جا تا نیمه نوشته نماند.
    pub fn set(&self, token: Option<String>) {
        let mut cur = self.token.lock().unwrap();
        let saved = Saved { token: token.clone().unwrap_or_default() };
        if let Some(dir) = self.path.parent() {
            let _ = fs::create_dir_all(dir);
        }
        let tmp = self.path.with_extension("tmp");
        if fs::write(&tmp, serde_json::to_vec(&saved).unwrap_or_default()).is_ok() {
            let _ = fs::rename(&tmp, &self.path);
        }
        *cur = token;
    }
}
