plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

val basaltId = providers.gradleProperty("basaltApplicationId").get()
val licenseOrigin = providers.gradleProperty("basaltLicenseBaseUrl")
    .orElse("https://flowshield-license-server.onrender.com").get()
require(licenseOrigin.startsWith("https://") || licenseOrigin.startsWith("http://"))

android {
    namespace = basaltId
    compileSdk = 36
    defaultConfig {
        applicationId = basaltId
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "LICENSE_BASE_URL", "\"${licenseOrigin.replace("\\", "\\\\").replace("\"", "\\\"")}\"")
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    lint { abortOnError = true; checkReleaseBuilds = true }
    testOptions { unitTests.isIncludeAndroidResources = true }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}
kotlin { jvmToolchain(21) }
ksp { arg("room.schemaLocation", "$projectDir/schemas") }

// Read the shared token source directly: no independently maintained Android colors.
val generateTokens = tasks.register("generateTokens") {
    val source = rootProject.file("../design/tokens.json")
    val destination = layout.buildDirectory.dir("generated/basaltAssets")
    inputs.file(source)
    outputs.dir(destination)
    doLast {
        val folder = destination.get().asFile.apply { mkdirs() }
        source.copyTo(folder.resolve("tokens.json"), overwrite = true)
    }
}
android.sourceSets["main"].assets.directories += layout.buildDirectory.dir("generated/basaltAssets").get().asFile.path
tasks.named("preBuild") { dependsOn(generateTokens) }

dependencies {
    implementation(project(":core"))
    // Later stable BOMs require compileSdk 37; use the latest compatible with 36.
    implementation(platform("androidx.compose:compose-bom:2026.06.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.window:window:1.5.1")
    implementation("androidx.datastore:datastore-preferences:1.3.0")
    implementation("androidx.room:room-runtime:2.8.5")
    implementation("androidx.room:room-ktx:2.8.5")
    ksp("androidx.room:room-compiler:2.8.5")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    implementation("com.squareup.okhttp3:okhttp:5.4.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
    testImplementation("org.robolectric:robolectric:4.16.1")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
