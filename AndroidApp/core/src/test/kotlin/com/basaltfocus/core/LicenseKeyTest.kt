package com.basaltfocus.core

import java.util.Locale
import org.junit.Assert.*
import org.junit.Test

class LicenseKeyTest {
    private val alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    private val valid = "FS-0123-4567-89AB-CDEQ"

    @Test fun normalizesLikeTheServerWithoutRemovingHyphens() {
        assertEquals("", LicenseKey.normalize(null))
        assertEquals("", LicenseKey.normalize(" \t_\r\n"))
        assertEquals(valid, LicenseKey.normalize(" \tfs-0123-_4567-89ab-cdeq\r\n"))
        assertEquals(valid, LicenseKey.normalize("\ufefffs-0123-\u00a04567-89ab-cdeq\u3000"))
        assertEquals("FS0123456789ABCDEQ", LicenseKey.normalize("fs0123456789abcdeq"))
        assertEquals("FS-00\u008500", LicenseKey.normalize("fs-00\u008500"))
    }

    @Test fun acceptsServerChecksumFixturesIncludingEveryAlphabetSymbol() {
        assertTrue(LicenseKey.isWellFormed(valid))
        assertTrue(LicenseKey.isWellFormed(" fs-0123-4567-89ab-cdeq "))
        assertTrue(LicenseKey.isWellFormed("FS-0000-0000-0000-0000"))
        for (symbol in alphabet) {
            // Fifteen identical values have weight sum 225, congruent to 1 mod 32.
            assertTrue(LicenseKey.isWellFormed("FS-" + List(4) { symbol.toString().repeat(4) }.joinToString("-")))
        }
    }

    @Test fun everyPositionUsesItsExactOddWeight() {
        val checks = "13579BDFHKNQSVX"
        for (position in 0 until 15) {
            val body = CharArray(16) { '0' }
            body[position] = '1'
            body[15] = checks[position]
            val key = "FS-" + body.concatToString().chunked(4).joinToString("-")
            assertTrue("payload position $position: $key", LicenseKey.isWellFormed(key))
        }
    }

    @Test fun rejectsEverySingleSymbolSubstitutionIncludingTheChecksum() {
        val body = "0123456789ABCDEQ"
        for (position in body.indices) {
            for (replacement in alphabet.filter { it != body[position] }) {
                val changed = body.toCharArray().also { it[position] = replacement }.concatToString()
                val key = "FS-" + changed.chunked(4).joinToString("-")
                assertFalse("position $position, replacement $replacement", LicenseKey.isWellFormed(key))
            }
        }
    }

    @Test fun rejectsMalformedKeysRatherThanInventingMissingFormattingOrAmbiguousSymbols() {
        for (key in listOf(null, "", "FS", "FS-0123-4567-89AB-CDE0", "FS0123456789ABCDEQ",
            "FS_0123_4567_89AB_CDEQ", "BS-0123-4567-89AB-CDEQ", "FS-012-34567-89AB-CDEQ",
            "FS-0123-4567-89AB-CDE", "FS-0123-4567-89AB-CDEQQ", "FS-0123-4567-89AB-CDEQ-",
            "FS-0123-4567-89AB-CDEQ!", "FS-0123-4567-89AB-CDEI", "FS-0123-4567-89AB-CDEL",
            "FS-0123-4567-89AB-CDEO", "FS-0123-4567-89AB-CDEU", "FS–0123-4567-89AB-CDEQ")) {
            assertFalse("key=$key", LicenseKey.isWellFormed(key))
        }
    }

    @Test fun normalizationIsIndependentOfDeviceLocale() {
        val original = Locale.getDefault()
        try {
            Locale.setDefault(Locale.forLanguageTag("tr-TR"))
            assertEquals("FS-I", LicenseKey.normalize("fs-i"))
            assertTrue(LicenseKey.isWellFormed(valid.lowercase(Locale.ROOT)))
        } finally {
            Locale.setDefault(original)
        }
    }
}
