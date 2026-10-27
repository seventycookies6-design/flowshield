package com.basaltfocus.app.ui

import com.basaltfocus.core.ActiveSprint
import com.basaltfocus.core.EndFlow
import com.basaltfocus.core.EndSprintPolicy
import com.basaltfocus.core.Momentum

/** The open "End this sprint early?" panel. Times are SystemClock.elapsedRealtime, so a clock change can't skip the wait. */
data class EndPanel(
    val sprintId: String,
    val flow: EndFlow,
    val requestedAt: Long,
    val title: String,
    val text: String,
) {
    val phraseRequired: Boolean get() = flow == EndFlow.SEALED
    private val unlocksAt: Long get() = requestedAt + EndSprintPolicy.delayMillis(flow)

    fun waitLeftMillis(nowMonotonic: Long): Long = (unlocksAt - nowMonotonic).coerceAtLeast(0)

    /** Ported from Windows' UpdateEndPanel: the button stays disabled until the wait and the phrase are both done. */
    fun canEnd(nowMonotonic: Long, phrase: String): Boolean =
        waitLeftMillis(nowMonotonic) == 0L && (!phraseRequired || EndSprintPolicy.phraseMatches(phrase))

    fun countdownText(nowMonotonic: Long, phrase: String): String {
        val left = waitLeftMillis(nowMonotonic)
        return when {
            left > 0 -> "You can end it in ${(left + 999) / 1000} s."
            phraseRequired && !EndSprintPolicy.phraseMatches(phrase) -> "Type the phrase to confirm."
            else -> ""
        }
    }
}

/** What pressing End does right now: end at once (grace cancel or Soft), or open a panel with a wait. */
sealed interface EndRequest {
    data class Now(val flow: EndFlow) : EndRequest
    data class Panel(val panel: EndPanel) : EndRequest
}

/** The end flow's view state, kept free of Compose so every rule is unit-tested. */
object EndFlowState {
    fun buttonLabel(sprint: ActiveSprint, nowMillis: Long): String =
        when (EndSprintPolicy.flowFor(sprint.shield, nowMillis - sprint.startedAt)) {
            EndFlow.CANCEL -> "Cancel sprint"
            EndFlow.IMMEDIATE -> "End sprint"
            EndFlow.CONFIRM -> "End sprint…"
            EndFlow.SEALED -> "I need to stop"
        }

    /** Under the button, while the grace period runs. */
    fun graceNote(sprint: ActiveSprint, nowMillis: Long): String? =
        if (nowMillis - sprint.startedAt < EndSprintPolicy.graceMillis)
            "In the first two minutes, cancelling leaves no record and doesn't change momentum."
        else null

    fun request(sprint: ActiveSprint, momentum: Double, nowMillis: Long, nowMonotonic: Long): EndRequest {
        val flow = EndSprintPolicy.flowFor(sprint.shield, nowMillis - sprint.startedAt)
        if (flow == EndFlow.CANCEL || flow == EndFlow.IMMEDIATE) return EndRequest.Now(flow)
        val left = ((sprint.endsAt - nowMillis).coerceAtLeast(0) + 59_999) / 60_000
        val after = EndSprintPolicy.momentumAfterEndingEarly(momentum, sprint.shield)
        val sealed = flow == EndFlow.SEALED
        val text = "$left minute${if (left == 1L) "" else "s"} left. Ending now counts as ended early: " +
            "momentum ${Momentum.display(momentum)} → ${Momentum.display(after)}." +
            if (sealed) " If you really need to stop, wait for the countdown, then type \"${EndSprintPolicy.phrase}\"." else ""
        return EndRequest.Panel(EndPanel(sprint.id, flow, nowMonotonic,
            if (sealed) "This sprint is sealed" else "End this sprint early?", text))
    }
}
