plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.shadownav.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.shadownav.app"
        // API 29 is the floor, not a default. GnssStatus.CONSTELLATION_IRNSS --
        // the NavIC enumeration that makes the visibility panel possible --
        // lands at 29, so the feature we actually want sets the floor.
        // AGC needs API 33 and is treated as opportunistic, never required.
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        // Filament (and Step 3's map engine) ship per-ABI native .so files that
        // R8/shrinkResources cannot touch, so the ABI list is the dominant lever
        // on APK size once a 3D engine is in the build. Measured this session:
        // raw Filament alone added ~5.55 MB across armeabi-v7a + arm64-v8a
        // (2.38 MB / 3.15 MB uncompressed respectively) against a 2.23 MB
        // baseline -- arm64-only is chosen deliberately to claw roughly the
        // v7a share back, since minSdk 29 (Android 10+, 2019+) devices are
        // overwhelmingly 64-bit-capable and Google has required 64-bit support
        // for all new Play Store submissions since August 2019; a 32-bit-only
        // handset on this minSdk is vanishingly rare. Verified the connected
        // moto g64 5G is arm64. Revisit if a real 32-bit-only target device
        // turns up, or if Step 0's Play Store-scope decision favours an
        // Android App Bundle, which splits per-device automatically.
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            // R8 on, because the target is a low-end phone with limited
            // storage and the debug APK is 12 MB, most of it Material and
            // appcompat that the diagnostic UI barely touches.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // `.filamat` is Filament's own compiled-material binary format; leaving
    // it compressed in the APK means decompressing it on every cold load for
    // no benefit (it's already a dense binary), per Filament's own samples.
    androidResources {
        noCompress += "filamat"
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation(project(":shadownav-core"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
    implementation(libs.filament.android)
    // filamat-android (the runtime shader-compiler toolchain, measured at
    // ~8.9 MB) is deliberately NOT a dependency of the shipped app -- it was
    // used once, temporarily, to generate assets/materials/orb.filamat (see
    // that file's header comment / PLAN.md), then removed. Re-add only if a
    // new material needs compiling, and remove again afterwards.
    testImplementation(libs.junit)
}
