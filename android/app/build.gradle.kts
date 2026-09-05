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

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation(project(":shadownav-core"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
    testImplementation(libs.junit)
}
