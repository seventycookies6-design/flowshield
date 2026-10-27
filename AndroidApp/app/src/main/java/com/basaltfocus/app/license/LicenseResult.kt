package com.basaltfocus.app.license

/** A nondefinitive response says nothing about whether a cached license is still active. */
data class LicenseResult(
    val isPro: Boolean = false,
    val definitive: Boolean = false,
    val status: String = "error",
    val message: String,
    val email: String? = null,
    val licenseKey: String? = null,
    val deviceCount: Int = 0,
    val deviceLimit: Int = 0
)
