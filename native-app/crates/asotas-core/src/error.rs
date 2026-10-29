/// خطای درخواست به سرور. متن فارسی هر کد را رابط کاربری می سازد (مثل `ERR` در gc.js).
#[derive(Debug, thiserror::Error, uniffi::Error)]
pub enum ApiError {
    /// به سرور وصل نشد (اینترنت، DNS، تایم اوت)
    #[error("network: {detail}")]
    Network { detail: String },
    /// نشست برنامه بسته یا منقضی شده
    #[error("auth")]
    Auth,
    /// درخواست زیاد شد؛ چند ثانیه بعد دوباره
    #[error("rate")]
    Rate,
    /// خطای سرور با کد کوتاه (مثل `insufficient` یا `code_bad`)؛ کل جواب سرور در `extra_json`
    #[error("{code}")]
    Server { code: String, extra_json: String },
}

impl ApiError {
    pub(crate) fn network(e: impl std::fmt::Display) -> Self {
        ApiError::Network { detail: e.to_string() }
    }
}
