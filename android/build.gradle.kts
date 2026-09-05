// Root build file. Plugins are declared but not applied here; the subprojects
// apply what they need. shadownav-core deliberately has no Android dependency
// so the estimator can be unit-tested on the JVM, which is where the parity
// tests against the Python golden vectors run.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.jvm) apply false
}
