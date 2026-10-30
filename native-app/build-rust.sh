#!/usr/bin/env bash
# کتابخانهٔ Rust (asotas-core) برای اندروید و کد اتصال کاتلینش.
# نیاز: Rust با هدف های اندروید، cargo-ndk و NDK اندروید (ANDROID_NDK_HOME).
#   rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android
#   cargo install cargo-ndk --locked
# خروجی:
#   android/app/src/main/jniLibs/<abi>/libasotas_core.so
#   android/app/src/uniffi/kotlin/dezhcode/asotas/core/asotas_core.kt
set -euo pipefail
cd "$(dirname "$0")"

APP=android/app/src
rm -rf "$APP/main/jniLibs" "$APP/uniffi"

cargo ndk -t arm64-v8a -t armeabi-v7a -t x86_64 -o "$APP/main/jniLibs" build --release -p asotas-core

# کد اتصال از روی خود کتابخانه (فهرست تابع ها و نوع ها داخل آن است). نسخهٔ release اندروید
# strip شده و این فهرست را ندارد، پس از ساخت debug همین سیستم خوانده می شود؛
# uniffi.toml صریح داده می شود تا پکیج کاتلین dezhcode.asotas.core باشد
cargo build -q -p asotas-core
HOSTLIB=target/debug/libasotas_core.so
[ -f "$HOSTLIB" ] || HOSTLIB=target/debug/libasotas_core.dylib
cargo run -q -p uniffi-bindgen -- generate \
  --library "$HOSTLIB" \
  --config crates/asotas-core/uniffi.toml \
  --language kotlin --no-format --out-dir "$APP/uniffi/kotlin"

ls -l "$APP"/main/jniLibs/*/
KT="$APP/uniffi/kotlin/dezhcode/asotas/core/asotas_core.kt"
if [ ! -f "$KT" ]; then
  echo "::error::Kotlin bindings are not at $KT; generated: $(find "$APP/uniffi" -type f | tr '\n' ' ')"
  exit 1
fi
echo "::notice::Kotlin bindings: $(grep -m1 '^package ' "$KT")"
