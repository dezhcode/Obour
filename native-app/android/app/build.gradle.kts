// برنامهٔ نیتیو AsoTas: رابط کاربری کاتلین (Compose) + هستهٔ Rust (native-app/crates/asotas-core).
// پیش از این ساخت، کتابخانهٔ Rust در src/main/jniLibs و کد اتصالش در src/uniffi/kotlin ساخته می شود
// (native-app/build-rust.sh یا workflow «AsoTas Native»).
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// شماره نسخه از workflow می آید: -PgcVersionCode=12 -PgcVersionName=1.2.0
val vCode = (findProperty("gcVersionCode") as String?)?.toIntOrNull() ?: 1
val vName = (findProperty("gcVersionName") as String?) ?: "0.1.0"
// آدرس سرور: پیش فرض همان سرور مینی اپ؛ برای سرور آزمایشی -PgcServer=https://.../gc/
val server = (findProperty("gcServer") as String?) ?: "https://dezhcode.pyho.ir/obour/gc/"

android {
    namespace = "dezhcode.asotas"
    compileSdk = 36

    defaultConfig {
        // نام بستهٔ AsoTas در مایکت؛ نسخهٔ آزمایشی پسوند .dev دارد تا کنارش نصب شود
        applicationId = "dezhcode.AsoTas.app"
        minSdk = 24
        targetSdk = 36
        versionCode = vCode
        versionName = vName
        buildConfigField("String", "SERVER_URL", "\"$server\"")
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
    }

    signingConfigs {
        val ks = System.getenv("GC_KEYSTORE_FILE")
        if (!ks.isNullOrEmpty()) {
            create("release") {
                storeFile = file(ks)
                storePassword = System.getenv("GC_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("GC_KEY_ALIAS")
                keyPassword = System.getenv("GC_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release")
        }
    }

    sourceSets {
        getByName("main") {
            java.srcDir("src/uniffi/kotlin")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        jniLibs { useLegacyPackaging = false }
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    // عکس پروفایل
    implementation("io.coil-kt:coil-compose:2.7.0")

    // کد اتصال UniFFI با JNA کتابخانهٔ Rust را صدا می زند
    implementation("net.java.dev.jna:jna:5.17.0@aar")
}
