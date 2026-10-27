package com.basaltfocus.app.ui

import com.basaltfocus.core.ActiveSprint
import com.basaltfocus.core.EndFlow
import com.basaltfocus.core.Shield
import org.junit.Assert.*
import org.junit.Test

class EndFlowStateTest {
    private val start = 1_000_000_000L
    private fun sprint(shield: Shield, minutes: Int = 25) = ActiveSprint("s1", start, minutes, shield)
    private val twoMinutes = 120_000L

    @Test fun insideTheGracePeriodEveryShieldCancelsAtOnce() {
        for (shield in Shield.entries) {
            val s = sprint(shield)
            assertEquals("Cancel sprint", EndFlowState.buttonLabel(s, start + twoMinutes - 1))
            assertEquals(EndRequest.Now(EndFlow.CANCEL), EndFlowState.request(s, 50.0, start + twoMinutes - 1, 0))
            assertNotNull(EndFlowState.graceNote(s, start + twoMinutes - 1))
            assertNull(EndFlowState.graceNote(s, start + twoMinutes))
        }
    }

    @Test fun softEndsImmediatelyAfterGrace() {
        val s = sprint(Shield.SOFT)
        assertEquals("End sprint", EndFlowState.buttonLabel(s, start + twoMinutes))
        assertEquals(EndRequest.Now(EndFlow.IMMEDIATE), EndFlowState.request(s, 50.0, start + twoMinutes, 0))
    }

    @Test fun firmOpensAConfirmationThatUnlocksAfterFiveSeconds() {
        val s = sprint(Shield.FIRM)
        assertEquals("End sprint…", EndFlowState.buttonLabel(s, start + twoMinutes))
        val panel = (EndFlowState.request(s, 100.0, start + twoMinutes, 10_000) as EndRequest.Panel).panel
        assertEquals(EndFlow.CONFIRM, panel.flow)
        assertEquals("End this sprint early?", panel.title)
        assertEquals("23 minutes left. Ending now counts as ended early: momentum 100 → 83.", panel.text)
        assertFalse(panel.phraseRequired)
        assertFalse(panel.canEnd(14_999, ""))
        assertEquals("You can end it in 1 s.", panel.countdownText(14_001, ""))
        assertEquals("You can end it in 5 s.", panel.countdownText(10_000, ""))
        assertTrue(panel.canEnd(15_000, ""))
        assertEquals("", panel.countdownText(15_000, ""))
    }

    @Test fun sealedNeedsThirtySecondsAndThePhrase() {
        val s = sprint(Shield.SEALED)
        assertEquals("I need to stop", EndFlowState.buttonLabel(s, start + twoMinutes))
        val panel = (EndFlowState.request(s, 100.0, start + twoMinutes, 0) as EndRequest.Panel).panel
        assertEquals(EndFlow.SEALED, panel.flow)
        assertEquals("This sprint is sealed", panel.title)
        assertTrue(panel.text, panel.text.contains("momentum 100 → 65."))
        assertTrue(panel.text, panel.text.endsWith("then type \"end my sprint\"."))
        assertTrue(panel.phraseRequired)
        assertFalse(panel.canEnd(29_999, "end my sprint"))
        assertEquals("You can end it in 30 s.", panel.countdownText(0, ""))
        assertFalse(panel.canEnd(30_000, "end my"))
        assertEquals("Type the phrase to confirm.", panel.countdownText(30_000, "end my"))
        assertTrue(panel.canEnd(30_000, "  End   MY sprint "))
        assertEquals("", panel.countdownText(30_000, "end my sprint"))
    }

    @Test fun panelSaysOneMinuteInTheSingular() {
        val s = sprint(Shield.FIRM, minutes = 3)
        val panel = (EndFlowState.request(s, 0.0, start + 150_000, 0) as EndRequest.Panel).panel
        assertTrue(panel.text, panel.text.startsWith("1 minute left."))
        assertTrue(panel.text, panel.text.contains("momentum 0 → 0."))
    }
}
