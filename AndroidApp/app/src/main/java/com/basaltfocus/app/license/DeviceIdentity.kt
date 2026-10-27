package com.basaltfocus.app.license

import java.security.MessageDigest

object DeviceIdentity {
    /** Only this full, namespaced hash leaves the phone; the caller supplies ANDROID_ID. */
    fun hash(androidId: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("FlowShield.device.v1|android|$androidId".toByteArray(Charsets.UTF_8))
        val hex = "0123456789abcdef"
        return buildString(64) {
            for (byte in digest) {
                val value = byte.toInt() and 0xff
                append(hex[value ushr 4])
                append(hex[value and 0xf])
            }
        }
    }
}
