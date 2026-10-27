package com.basaltfocus.app.license

import org.junit.Assert.*
import org.junit.Test

class LicensePolicyTest {
    @Test
    fun nondefinitiveResultsPreserveTheCacheWithoutAnExpiry() {
        val offline = LicenseResult(message = "Couldn't reach the license server.")
        repeat(100) {
            assertTrue(LicenseCachePolicy.keepAccess(true, offline))
            assertFalse(LicenseCachePolicy.keepAccess(false, offline))
        }
        // Even a stray isPro flag is not a verdict without definitive=true.
        assertFalse(LicenseCachePolicy.keepAccess(false, offline.copy(isPro = true)))
    }

    @Test
    fun anyDefinitiveVerdictReplacesTheCache() {
        for (cached in listOf(false, true)) {
            for (pro in listOf(false, true)) {
                assertEquals(pro, LicenseCachePolicy.keepAccess(cached,
                    LicenseResult(isPro = pro, definitive = true, status = "future_status", message = "Result")))
            }
        }
    }

    @Test
    fun waitingCopyChangesAtExactlyEightSeconds() {
        assertEquals("Contacting the license server…", LicenseWaitCopy.messageFor(0.0))
        assertEquals(LicenseWaitCopy.ContactingMessage, LicenseWaitCopy.messageFor(7.999))
        assertEquals("The server is waking up. This can take up to a minute.", LicenseWaitCopy.messageFor(8.0))
        assertEquals(LicenseWaitCopy.WakingUpMessage, LicenseWaitCopy.messageFor(72.0))
    }

    @Test
    fun windowsRetryScheduleIsSeventyTwoSecondsWithinTheBudget() {
        assertEquals(listOf(2.0, 5.0), LicenseWaitCopy.RetryDelaysSeconds)
        assertEquals(3, LicenseWaitCopy.TotalAttempts)
        assertEquals(35.0, LicenseWaitCopy.timeoutForAttempt(1), 0.0)
        assertEquals(15.0, LicenseWaitCopy.timeoutForAttempt(2), 0.0)
        assertEquals(15.0, LicenseWaitCopy.timeoutForAttempt(3), 0.0)
        val total = (1..LicenseWaitCopy.TotalAttempts).sumOf(LicenseWaitCopy::timeoutForAttempt) +
            LicenseWaitCopy.RetryDelaysSeconds.sum()
        assertEquals(72.0, total, 0.0)
        assertEquals(total, LicenseWaitCopy.TotalBudgetSeconds, 0.0)
        assertTrue(total <= 75.0)
    }

    @Test
    fun androidIdentityUsesTheFullNamespacedSha256() {
        assertEquals("ff782453e0d5848b4a56f3c3e674ae6a744a5c0528238f811925f49b053197a3",
            DeviceIdentity.hash("9774d56d682e549c"))
        assertEquals(64, DeviceIdentity.hash("9774d56d682e549c").length)
        assertNotEquals(DeviceIdentity.hash("9774d56d682e549c"), DeviceIdentity.hash("9774d56d682e549d"))
    }
}
