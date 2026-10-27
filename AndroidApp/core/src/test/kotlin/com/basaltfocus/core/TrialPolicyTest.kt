package com.basaltfocus.core

import org.junit.Assert.*
import org.junit.Test

class TrialPolicyTest {
    private val day = 86_400_000L
    private val start = 1_700_000_000_000L

    @Test fun missingTrialStartGrantsNeitherDaysNorAccess() {
        assertFalse(TrialPolicy.active(null, start))
        assertEquals(0, TrialPolicy.daysLeft(null, start))
        assertFalse(TrialPolicy.hasAccess(false, null, start))
    }

    @Test fun trialIncludesTheStartAndExpiresAtExactlySevenDays() {
        assertTrue(TrialPolicy.active(start, start))
        assertTrue(TrialPolicy.active(start, start + 7 * day - 1))
        assertFalse(TrialPolicy.active(start, start + 7 * day))
        assertFalse(TrialPolicy.active(start, start + 7 * day + 1))
    }

    @Test fun daysLeftRoundsUpIncludingTheFinalMillisecond() {
        for ((elapsed, expected) in listOf(0L to 7, 1L to 7, day - 1 to 7,
            day to 6, day + 1 to 6, 6 * day to 1, 7 * day - 1 to 1,
            7 * day to 0, 8 * day to 0)) {
            assertEquals("elapsed=$elapsed", expected, TrialPolicy.daysLeft(start, start + elapsed))
        }
    }

    @Test fun oneDayOfClockSkewIsAllowedAndDaysLeftNeverExceedsSeven() {
        assertTrue(TrialPolicy.active(start, start - day))
        assertTrue(TrialPolicy.active(start, start - day + 1))
        assertEquals(7, TrialPolicy.daysLeft(start, start - day))
        assertEquals(7, TrialPolicy.daysLeft(start, start - 1))
        assertFalse(TrialPolicy.active(start, start - day - 1))
        assertEquals(0, TrialPolicy.daysLeft(start, start - day - 1))
    }

    @Test fun licenseGrantsAccessRegardlessOfTrialState() {
        assertTrue(TrialPolicy.hasAccess(true, null, start))
        assertTrue(TrialPolicy.hasAccess(true, start, start + 8 * day))
        assertTrue(TrialPolicy.hasAccess(true, start, start - 2 * day))
        assertTrue(TrialPolicy.hasAccess(false, start, start + 2 * day))
        assertFalse(TrialPolicy.hasAccess(false, start, start + 7 * day))
        assertFalse(TrialPolicy.hasAccess(false, start, start - day - 1))
    }

    @Test fun earliestRetainsTheOldestKnownRecordInEitherOrder() {
        assertNull(TrialPolicy.earliest(null, null))
        assertEquals(start, TrialPolicy.earliest(start, null))
        assertEquals(start, TrialPolicy.earliest(null, start))
        assertEquals(start, TrialPolicy.earliest(start, start))
        assertEquals(start, TrialPolicy.earliest(start, start + day))
        assertEquals(start, TrialPolicy.earliest(start + day, start))
    }

    @Test fun epochZeroAndNegativeTimestampsAreKnownDates() {
        assertTrue(TrialPolicy.active(0L, 0L))
        assertTrue(TrialPolicy.active(-day, 0L))
        assertEquals(-day, TrialPolicy.earliest(-day, 0L))
    }

    @Test fun extremeDatesDoNotWrapIntoAnActiveTrial() {
        assertFalse(TrialPolicy.active(Long.MIN_VALUE, Long.MAX_VALUE))
        assertFalse(TrialPolicy.active(Long.MAX_VALUE, Long.MIN_VALUE))
        assertEquals(0, TrialPolicy.daysLeft(Long.MIN_VALUE, Long.MAX_VALUE))
        assertTrue(TrialPolicy.active(Long.MAX_VALUE, Long.MAX_VALUE))
        assertEquals(7, TrialPolicy.daysLeft(Long.MAX_VALUE, Long.MAX_VALUE))
    }
}
