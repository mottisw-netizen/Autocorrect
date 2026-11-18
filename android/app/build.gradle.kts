plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

fun prop(name: String) = (project.findProperty(name) as String?) ?: ""
val serverUrl = prop("autocorrectServerUrl")
val defaultMode = prop("autocorrectDefaultMode").ifEmpty { "server" }
val defaultModel = prop("autocorrectDefaultModel")

android {
    namespace = "com.autocorrect.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.autocorrect.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "DEFAULT_SERVER_URL", "\"$serverUrl\"")
        buildConfigField("String", "DEFAULT_MODE", "\"$defaultMode\"")
        buildConfigField("String", "DEFAULT_MODEL", "\"$defaultModel\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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
