package com.basaltfocus.core

import java.util.Locale

object LicenseKey {
    private const val alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    private val format = Regex("FS(?:-[0-9A-HJKMNP-TV-Z]{4}){4}")

    // ECMAScript \s, as used by Server/licensekey.js. NEL and zero-width space are not included.
    private val formatting = Regex("[\\s_\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")

    fun normalize(input: String?): String =
        input.orEmpty().uppercase(Locale.ROOT).replace(formatting, "")

    /** A typo check only. Access still requires the server's license validation. */
    fun isWellFormed(input: String?): Boolean {
        val normalized = normalize(input)
        if (!format.matches(normalized)) return false
        val body = normalized.substring(3).replace("-", "")
        var sum = 0
        for (index in 0 until 15) {
            sum += alphabet.indexOf(body[index]) * (2 * index + 1)
        }
        return body[15] == alphabet[sum % alphabet.length]
    }
}
