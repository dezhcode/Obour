//! سازندهٔ کد اتصال کاتلین از روی کتابخانهٔ asotas-core:
//! cargo run -p uniffi-bindgen -- generate --library <libasotas_core> --language kotlin --out-dir <dir>
fn main() {
    uniffi::uniffi_bindgen_main()
}
