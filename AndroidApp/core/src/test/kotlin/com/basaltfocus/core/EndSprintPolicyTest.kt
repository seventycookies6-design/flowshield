package com.basaltfocus.core

import org.junit.Assert.*
import org.junit.Test

class EndSprintPolicyTest {
    @Test fun everyShieldCanCancelStrictlyBeforeTwoMinutes() {
        for (shield in Shield.values()) {
            for (elapsed in listOf(Long.MIN_VALUE, -1L, 0L, 119_999L)) {
                assertEquals("$shield at $elapsed", EndFlow.CANCEL, EndSprintPolicy.flowFor(shield, elapsed))
            }
        }
    }

    @Test fun exactGraceBoundaryUsesTheSelectedShieldFlow() {
        for (elapsed in listOf(120_000L, 120_001L, Long.MAX_VALUE)) {
            assertEquals(EndFlow.IMMEDIATE, EndSprintPolicy.flowFor(Shield.SOFT, elapsed))
            assertEquals(EndFlow.CONFIRM, EndSprintPolicy.flowFor(Shield.FIRM, elapsed))
            assertEquals(EndFlow.SEALED, EndSprintPolicy.flowFor(Shield.SEALED, elapsed))
        }
    }

    @Test fun onlyConfirmationFlowsHaveAWait() {
        assertEquals(0L, EndSprintPolicy.delayMillis(EndFlow.CANCEL))
        assertEquals(0L, EndSprintPolicy.delayMillis(EndFlow.IMMEDIATE))
        assertEquals(5_000L, EndSprintPolicy.delayMillis(EndFlow.CONFIRM))
        assertEquals(30_000L, EndSprintPolicy.delayMillis(EndFlow.SEALED))
    }

    @Test fun phraseAcceptsCaseAndUnicodeWhitespaceBetweenTheExactWords() {
        for (typed in listOf("end my sprint", "END MY SPRINT", "  End\tmy\r\nsprint  ",
            "\u00a0end\u2003my\u0085sprint\u00a0", "end\u2028my\u202fsprint")) {
            assertTrue(typed, EndSprintPolicy.phraseMatches(typed))
        }
    }

    @Test fun phraseRejectsMissingExtraOrAlteredWords() {
        for (typed in listOf(null, "", " \t\n", "endmysprint", "end my", "end my sprint!",
            "please end my sprint", "end your sprint", "end my sprint now", "end-my-sprint",
            "end\u200bmy sprint", "end\u001cmy sprint", "end\ufeffmy sprint")) {
            assertFalse("input=$typed", EndSprintPolicy.phraseMatches(typed))
        }
    }

    @Test fun softAndFirmEarlyEndsLoseFifteenPercentAndTwoPoints() {
        for (shield in listOf(Shield.SOFT, Shield.FIRM)) {
            assertEquals(83.0, EndSprintPolicy.momentumAfterEndingEarly(100.0, shield), 0.0)
            assertEquals(6.5, EndSprintPolicy.momentumAfterEndingEarly(10.0, shield), 0.0)
            assertEquals(7.4, EndSprintPolicy.momentumAfterEndingEarly(11.0, shield), 0.0)
        }
    }

    @Test fun sealedEarlyEndsLoseThirtyPercentAndFivePoints() {
        assertEquals(65.0, EndSprintPolicy.momentumAfterEndingEarly(100.0, Shield.SEALED), 0.0)
        assertEquals(2.0, EndSprintPolicy.momentumAfterEndingEarly(10.0, Shield.SEALED), 0.0)
        assertEquals(11.8, EndSprintPolicy.momentumAfterEndingEarly(24.0, Shield.SEALED), 0.0)
    }

    @Test fun everyEarlyEndFloorsTheResultAtZero() {
        for (shield in Shield.values()) {
            for (score in listOf(-100.0, 0.0, 1.0, 2.0)) {
                assertEquals("$shield, score $score", 0.0,
                    EndSprintPolicy.momentumAfterEndingEarly(score, shield), 0.0)
            }
        }
        assertEquals(0.0, EndSprintPolicy.momentumAfterEndingEarly(7.0, Shield.SEALED), 0.0)
    }

    @Test fun earlyEndRoundingUsesEvenMidpointsRatherThanAlwaysRoundingUp() {
        for (shield in listOf(Shield.SOFT, Shield.FIRM)) {
            // 9 * .85 - 2 = 5.65; 11 * .85 - 2 = 7.35.
            assertEquals(5.6, EndSprintPolicy.momentumAfterEndingEarly(9.0, shield), 0.0)
            assertEquals(7.4, EndSprintPolicy.momentumAfterEndingEarly(11.0, shield), 0.0)
        }
        // 7.5 * .7 - 5 = .25; 12.5 * .7 - 5 = 3.75.
        assertEquals(0.2, EndSprintPolicy.momentumAfterEndingEarly(7.5, Shield.SEALED), 0.0)
        assertEquals(3.8, EndSprintPolicy.momentumAfterEndingEarly(12.5, Shield.SEALED), 0.0)
    }
}
