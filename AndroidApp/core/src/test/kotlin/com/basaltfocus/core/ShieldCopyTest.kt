package com.basaltfocus.core

import java.util.Locale
import org.junit.Assert.*
import org.junit.Test

class ShieldCopyTest {
    @Test fun everyShieldPromisesOnlyNoticesAndHomeNavigation() {
        for (shield in Shield.values()) {
            val copy = ShieldCopy.promise(shield).lowercase(Locale.ROOT)
            assertTrue("$shield needs a notice promise", copy.contains("notice"))
            for (claim in listOf("close", "kill", "terminate", "uninstall", "impossible")) {
                assertFalse("$shield makes unsupported claim: $claim", copy.contains(claim))
            }
            if (shield != Shield.SOFT) assertTrue(copy, copy.contains("home"))
        }
    }

    @Test fun onlySealedPromisesToLockTheList() {
        assertFalse(ShieldCopy.promise(Shield.SOFT).contains("lock", ignoreCase = true))
        assertFalse(ShieldCopy.promise(Shield.FIRM).contains("lock", ignoreCase = true))
        val sealed = ShieldCopy.promise(Shield.SEALED).lowercase(Locale.ROOT)
        assertTrue(sealed, sealed.contains("locks the list"))
        assertTrue(sealed, sealed.contains("sprint ends"))
    }
}
