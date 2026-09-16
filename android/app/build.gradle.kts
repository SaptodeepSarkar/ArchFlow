plugins {
    id("com.android.application")
    kotlin("android")
}

// Firebase configuration is user/project-local and must not be required for
// a clean open-source checkout or for offline dictation builds.
if (file("google-services.json").isFile) {
    apply(plugin = "com.google.gms.google-services")
}

android { namespace = "org.vaani.keyboard"; compileSdk = 35
    defaultConfig {
        applicationId = "org.vaani.keyboard"; minSdk = 31; targetSdk = 35; versionCode = 100; versionName = "1.0.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}

kotlin { jvmToolchain(17) }

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    // BoM 33.x keeps the Android libraries compatible with Kotlin 2.0.21.
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-auth")
    implementation("com.google.firebase:firebase-firestore")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}
