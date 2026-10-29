//! هستهٔ برنامهٔ نیتیو AsoTas: هر چیزی که به رابط کاربری ربط ندارد.
//!
//! - `client`: گفتگو با سرور AsoTas (همان API مینی اپ زیر `/gc/`)؛ حساب مهمان، ورود با تلگرام و ایمیل
//! - `store`: نگه داشتن توکن نشست روی گوشی
//! - `models`: داده هایی که به رابط کاربری (کاتلین) داده می شود
//!
//! کاتلین از راه UniFFI به این کتابخانه وصل است؛ کد اتصال از روی همین فایل ها ساخته می شود.

uniffi::setup_scaffolding!();

mod client;
mod error;
mod models;
mod store;

pub use client::Client;
pub use error::ApiError;
pub use models::*;
