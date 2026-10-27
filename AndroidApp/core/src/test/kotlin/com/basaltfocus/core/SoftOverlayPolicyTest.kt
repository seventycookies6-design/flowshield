package com.basaltfocus.core

import org.junit.Assert.*
import org.junit.Test

class SoftOverlayPolicyTest {
    private val app = "com.example.distraction"
    private val other = "com.example.other"

    @Test fun repeatedSweepsShowOneNoticePerSighting() {
        val policy = SoftOverlayPolicy()
        assertTrue(policy.shouldShow(app, 0))
        assertFalse(policy.shouldShow(app, 650))
        assertFalse(policy.shouldShow(app, 50_000))
        assertEquals(1, policy.tries)
        assertTrue(policy.leftForeground())
        assertFalse(policy.leftForeground())
        assertTrue(policy.shouldShow(app, 51_000))
        assertEquals(2, policy.tries)
    }

    @Test fun switchingBlockedAppsCreatesANewSightingAndUsesASprintWideTryCount() {
        val policy = SoftOverlayPolicy()
        assertTrue(policy.shouldShow(app, 0))
        assertTrue(policy.shouldShow(other, 1))
        assertTrue(policy.shouldShow(app, 2))
        assertEquals(3, policy.tries)
        assertEquals(0, policy.turnedBack)
    }

    @Test fun allowWaitEscalatesFiveTenTwentyThenThirtySeconds() {
        for ((tryNumber, wait) in listOf(Int.MIN_VALUE to 5_000L, 0 to 5_000L, 1 to 5_000L,
            2 to 10_000L, 3 to 20_000L, 4 to 30_000L, 5 to 30_000L, Int.MAX_VALUE to 30_000L)) {
            assertEquals("try $tryNumber", wait, SoftOverlayPolicy.allowWaitMillis(tryNumber))
        }
    }

    @Test fun allowanceIsPerAppAndExpiresAtExactlyFiveMinutes() {
        val policy = SoftOverlayPolicy()
        assertTrue(policy.shouldShow(app, 1_000))
        policy.allowFiveMinutes(app, 1_000)
        assertEquals(0, policy.turnedBack)
        assertFalse(policy.leftForeground())
        assertTrue(policy.isQuiet(app, 300_999))
        assertFalse(policy.isQuiet(other, 1_000))
        assertFalse(policy.isQuiet(app, 301_000))
        assertTrue(policy.shouldShow(other, 2_000))
        policy.leftForeground()
        assertTrue(policy.shouldShow(app, 301_000))
        assertEquals(3, policy.tries)
    }

    @Test fun pollingDuringAllowanceDoesNotCreateMoreTriesOrARepeatedNoticeAtExpiry() {
        val policy = SoftOverlayPolicy()
        policy.shouldShow(app, 0)
        policy.allowFiveMinutes(app, 0)
        assertFalse(policy.shouldShow(app, 1))
        policy.leftForeground()
        assertFalse(policy.shouldShow(app, 299_999))
        assertFalse(policy.shouldShow(app, 300_000))
        assertEquals(1, policy.tries)
        policy.leftForeground()
        assertTrue(policy.shouldShow(app, 300_001))
        assertEquals(2, policy.tries)
    }

    @Test fun backToWorkCountsATurnBackAndQuietsOnlyThatAppForFiveSeconds() {
        val policy = SoftOverlayPolicy()
        policy.shouldShow(app, 0)
        policy.backToWork(app, 1_000)
        assertEquals(1, policy.turnedBack)
        assertEquals(1, policy.tries)
        assertFalse(policy.leftForeground())
        assertTrue(policy.isQuiet(app, 5_999))
        assertFalse(policy.isQuiet(other, 1_001))
        assertFalse(policy.isQuiet(app, 6_000))
        assertTrue(policy.shouldShow(app, 6_000))
    }

    @Test fun caseDifferencesDoNotCreateNewSightingsOrBypassQuietWindows() {
        val policy = SoftOverlayPolicy()
        assertTrue(policy.shouldShow(app, 0))
        assertFalse(policy.shouldShow(app.uppercase(), 1))
        policy.allowFiveMinutes(app.uppercase(), 1)
        assertTrue(policy.isQuiet(app, 2))
        assertFalse(policy.shouldShow(app, 2))
    }

    @Test fun resetClearsAllowancesSightingsAndAllSprintCounters() {
        val policy = SoftOverlayPolicy()
        policy.shouldShow(app, 0)
        policy.backToWork(app, 0)
        policy.shouldShow(other, 1)
        policy.allowFiveMinutes(other, 1)
        policy.reset()
        assertEquals(0, policy.tries)
        assertEquals(0, policy.turnedBack)
        assertFalse(policy.isQuiet(app, 2))
        assertFalse(policy.isQuiet(other, 2))
        assertFalse(policy.leftForeground())
        assertTrue(policy.shouldShow(other, 2))
        assertEquals(1, policy.tries)
    }
}
