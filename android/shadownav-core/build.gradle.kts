// Pure Kotlin/JVM. No Android dependency, on purpose: the estimator is the part
// that must be provably identical to the Python implementation, and that proof
// runs as an ordinary JVM unit test rather than needing a device or emulator.
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlin.jvm)
}

java {
    // Java 17 bytecode is what Android accepts. The toolchain is not pinned:
    // only the JDK bundled with Android Studio (21) is installed here, and
    // pinning 17 would fail rather than degrade.
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    testImplementation(libs.junit)
}

tasks.test {
    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = false
    }
}
