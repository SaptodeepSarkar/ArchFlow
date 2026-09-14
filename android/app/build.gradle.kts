plugins {
    id("com.android.application")
    kotlin("android")
}

android { namespace = "org.vaani.keyboard"; compileSdk = 35
    defaultConfig { applicationId = "org.vaani.keyboard"; minSdk = 31; targetSdk = 35; versionCode = 1; versionName = "0.1.0" }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}

kotlin { jvmToolchain(17) }

dependencies { implementation("androidx.core:core-ktx:1.15.0") }
