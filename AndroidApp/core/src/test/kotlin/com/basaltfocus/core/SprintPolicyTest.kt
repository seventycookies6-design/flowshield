package com.basaltfocus.core

import org.junit.Assert.*
import org.junit.Test

class SprintPolicyTest {
    private val start = 1_700_000_000_000L
    private fun sprint(shield: Shield = Shield.FIRM, minutes: Int = 25) =
        ActiveSprint("stable-sprint-id", start, minutes, shield)

    @Test fun aSprintCanStartOnlyWithAccessAndNoPersistedActiveSprint() {
        assertTrue(SprintPolicy.canStart(true, null))
        assertFalse(SprintPolicy.canStart(false, null))
        assertFalse(SprintPolicy.canStart(false, sprint()))
        assertFalse(SprintPolicy.canStart(true, sprint()))
        // Even expired/corrupt records must be settled before another start.
        assertFalse(SprintPolicy.canStart(true, sprint(minutes = 0)))
    }

    @Test fun endTimeIsDerivedFromTheOriginalStartAndPlannedMinutes() {
        val active = sprint()
        assertEquals(start + 1_500_000L, active.endsAt)
        assertEquals(start, active.lastSeenAt)
        assertEquals(0L, active.watchedMillis)
        assertEquals(start + 2_700_000L, sprint(minutes = 45).endsAt)
    }

    @Test fun heartbeatCreditsOnlyTheObservedStretchUpToItsCap() {
        val original = sprint()
        val first = original.heartbeat(start + 650)
        assertEquals(650L, first.watchedMillis)
        assertEquals(start + 650, first.lastSeenAt)
        val afterSuspension = first.heartbeat(start + 100_650)
        assertEquals(5_650L, afterSuspension.watchedMillis)
        assertEquals(start + 100_650, afterSuspension.lastSeenAt)
        assertEquals(0L, original.watchedMillis)
        assertEquals(original.id, afterSuspension.id)
        assertEquals(original.startedAt, afterSuspension.startedAt)
        assertEquals(original.shield, afterSuspension.shield)
        assertEquals(original.plannedMinutes, afterSuspension.plannedMinutes)
    }

    @Test fun heartbeatHonorsAnExplicitCapAndNeverCreditsANegativeCap() {
        assertEquals(1_000L, sprint().heartbeat(start + 2_000, 1_000).watchedMillis)
        assertEquals(0L, sprint().heartbeat(start + 2_000, 0).watchedMillis)
        assertEquals(0L, sprint().heartbeat(start + 2_000, -1).watchedMillis)
    }

    @Test fun duplicateHeartbeatAndClockRollbackCannotCreditTheSameTimeTwice() {
        val first = sprint().heartbeat(start + 1_000)
        assertEquals(first, first.heartbeat(start + 1_000))
        assertEquals(first, first.heartbeat(start + 500))
        assertEquals(first, first.heartbeat(start - 1))
        val next = first.heartbeat(start + 2_000)
        assertEquals(2_000L, next.watchedMillis)
    }

    @Test fun heartbeatNeverCreditsTimePastThePlannedEnd() {
        val nearEnd = sprint().copy(lastSeenAt = start + 1_499_000, watchedMillis = 1_499_000)
        val ended = nearEnd.heartbeat(start + 1_600_000)
        assertEquals(1_500_000L, ended.watchedMillis)
        assertEquals(ended.endsAt, ended.lastSeenAt)
        assertEquals(ended, ended.heartbeat(start + 2_000_000))
    }

    @Test fun watchedTotalsAreClampedWhenTheSavedRecordIsDamaged() {
        val tooLarge = sprint().copy(watchedMillis = Long.MAX_VALUE).heartbeat(start + 1_000)
        assertEquals(1_500_000L, tooLarge.watchedMillis)
        val negative = sprint().copy(watchedMillis = -10).heartbeat(start + 1_000)
        assertEquals(1_000L, negative.watchedMillis)
    }

    @Test fun restartResumesTheSameShieldWhileAnyTimeRemains() {
        for (shield in Shield.values()) {
            val active = sprint(shield)
            assertEquals(ResumeDecision.RESUME, active.resumeDecision(start))
            assertEquals(ResumeDecision.RESUME, active.resumeDecision(active.endsAt - 1))
            assertEquals(shield, active.heartbeat(start + 1_000).shield)
        }
    }

    @Test fun elapsedSprintIsCompletedAtExactlyHalfWatchedAndInterruptedBelowHalf() {
        val active = sprint()
        assertEquals(ResumeDecision.INTERRUPTED, active.copy(watchedMillis = 749_999).resumeDecision(active.endsAt))
        assertEquals(ResumeDecision.COMPLETED, active.copy(watchedMillis = 750_000).resumeDecision(active.endsAt))
        assertEquals(ResumeDecision.COMPLETED, active.copy(watchedMillis = 750_001).resumeDecision(active.endsAt + 1))
        assertEquals(ResumeDecision.INTERRUPTED, active.resumeDecision(active.endsAt))
        assertEquals(ResumeDecision.INTERRUPTED, active.copy(watchedMillis = -1).resumeDecision(active.endsAt))
        assertEquals(ResumeDecision.COMPLETED, active.copy(watchedMillis = Long.MAX_VALUE).resumeDecision(active.endsAt))
    }

    @Test fun recoveryDoesNotInferWatchedTimeFromTheLastSeenTimestamp() {
        val active = sprint().copy(lastSeenAt = start + 1_499_000, watchedMillis = 1_000)
        assertEquals(ResumeDecision.INTERRUPTED, active.resumeDecision(active.endsAt + 1))
        repeat(3) {
            assertEquals(ResumeDecision.INTERRUPTED, active.resumeDecision(active.endsAt + 1))
        }
        assertEquals(1_000L, active.watchedMillis)
    }

    @Test fun invalidDurationAndOverflowingEndDatesAreDiscarded() {
        for (minutes in listOf(Int.MIN_VALUE, -1, 0)) {
            assertEquals(ResumeDecision.DISCARD, sprint(minutes = minutes).resumeDecision(start))
        }
        val overflow = sprint().copy(startedAt = Long.MAX_VALUE)
        assertEquals(ResumeDecision.DISCARD, overflow.resumeDecision(Long.MAX_VALUE))
    }

    @Test fun graceCancellationNeverRequiresAConfirmationRequestOrPhrase() {
        for (shield in Shield.values()) {
            assertTrue(SprintPolicy.canEnd(sprint(shield), start + 119_999, null, 0, null))
        }
    }

    @Test fun softCanEndImmediatelyAtAndAfterTheGraceBoundary() {
        assertTrue(SprintPolicy.canEnd(sprint(Shield.SOFT), start + 120_000, null, 0, null))
        assertTrue(SprintPolicy.canEnd(sprint(Shield.SOFT), start + 120_001, null, 0, null))
    }

    @Test fun firmRequiresAnExplicitRequestAndFiveElapsedMonotonicSeconds() {
        val active = sprint(Shield.FIRM)
        assertFalse(SprintPolicy.canEnd(active, start + 120_000, null, 10_000, null))
        assertFalse(SprintPolicy.canEnd(active, start + 120_000, 1_000, 5_999, null))
        assertTrue(SprintPolicy.canEnd(active, start + 120_000, 1_000, 6_000, null))
        assertTrue(SprintPolicy.canEnd(active, start + 120_000, 1_000, 6_001, null))
    }

    @Test fun sealedRequiresBothThirtyElapsedMonotonicSecondsAndThePhrase() {
        val active = sprint(Shield.SEALED)
        assertFalse(SprintPolicy.canEnd(active, start + 120_000, null, 99_000, "end my sprint"))
        assertFalse(SprintPolicy.canEnd(active, start + 120_000, 1_000, 30_999, "end my sprint"))
        assertFalse(SprintPolicy.canEnd(active, start + 120_000, 1_000, 31_000, null))
        assertFalse(SprintPolicy.canEnd(active, start + 120_000, 1_000, 31_000, "end your sprint"))
        assertTrue(SprintPolicy.canEnd(active, start + 120_000, 1_000, 31_000, "  END\tmy sprint "))
    }

    @Test fun movingWallTimeForwardCannotBypassTheMonotonicWait() {
        val active = sprint(Shield.FIRM)
        assertFalse(SprintPolicy.canEnd(active, start + 600_000, 1_000, 1_001, null))
        assertFalse(SprintPolicy.canEnd(active, start + 600_000, 2_000, 1_000, null))
        assertFalse(SprintPolicy.canEnd(active, start + 600_000, Long.MIN_VALUE, Long.MAX_VALUE, null))
    }

    @Test fun expiredOrInvalidSprintsCannotBeAuthorizedAsEarlyEnds() {
        for (shield in Shield.values()) {
            val active = sprint(shield)
            assertFalse(SprintPolicy.canEnd(active, active.endsAt, 0, 100_000, "end my sprint"))
            assertFalse(SprintPolicy.canEnd(active.copy(plannedMinutes = 0), start, 0, 100_000, "end my sprint"))
        }
    }
}
