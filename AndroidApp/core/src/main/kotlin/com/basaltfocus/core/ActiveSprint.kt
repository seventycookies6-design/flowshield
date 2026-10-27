package com.basaltfocus.core

enum class ResumeDecision { RESUME, COMPLETED, INTERRUPTED, DISCARD }

data class ActiveSprint(
    val id: String,
    val startedAt: Long,
    val plannedMinutes: Int,
    val shield: Shield,
    val lastSeenAt: Long = startedAt,
    val watchedMillis: Long = 0,
) {
    private val durationMillis: Long get() = plannedMinutes.toLong() * 60_000L
    private val valid: Boolean
        get() = plannedMinutes > 0 && startedAt <= Long.MAX_VALUE - durationMillis

    /** Saturate a corrupt overflowing end date; resumeDecision still discards that record. */
    val endsAt: Long
        get() = when {
            plannedMinutes <= 0 -> startedAt
            !valid -> Long.MAX_VALUE
            else -> startedAt + durationMillis
        }

    /**
     * Credit observed time only. Sleep/restart gaps are capped and time after the end earns
     * nothing. A repeated timestamp or backwards clock cannot count the same stretch twice.
     */
    fun heartbeat(nowMillis: Long, capMillis: Long = 5_000): ActiveSprint {
        if (!valid) return this
        val previous = lastSeenAt.coerceIn(startedAt, endsAt)
        val observedUntil = nowMillis.coerceIn(startedAt, endsAt).coerceAtLeast(previous)
        val stretch = (observedUntil - previous).coerceAtMost(capMillis.coerceAtLeast(0))
        return copy(
            lastSeenAt = observedUntil,
            watchedMillis = (watchedMillis.coerceIn(0, durationMillis) + stretch).coerceAtMost(durationMillis),
        )
    }

    /** Pure judgement: persistence must atomically clear this ID and record its result once. */
    fun resumeDecision(nowMillis: Long): ResumeDecision = when {
        !valid -> ResumeDecision.DISCARD
        nowMillis < endsAt -> ResumeDecision.RESUME
        watchedMillis.coerceIn(0, durationMillis) >= durationMillis / 2 -> ResumeDecision.COMPLETED
        else -> ResumeDecision.INTERRUPTED
    }
}

object SprintPolicy {
    /** Even expired records must be settled before another sprint replaces them. */
    fun canStart(hasAccess: Boolean, active: ActiveSprint?): Boolean = hasAccess && active == null

    /**
     * Recheck in the transition handler, rather than trusting a disabled UI control.
     * Expired sprints settle through recovery, so an end click cannot charge an early penalty.
     * The caller owns the monotonic request timestamp for the currently displayed end flow.
     */
    fun canEnd(
        active: ActiveSprint,
        nowMillis: Long,
        requestedAtMonotonic: Long?,
        nowMonotonic: Long,
        phrase: String?,
    ): Boolean {
        if (active.resumeDecision(nowMillis) != ResumeDecision.RESUME) return false
        val elapsed = try {
            Math.subtractExact(nowMillis, active.startedAt)
        } catch (_: ArithmeticException) {
            return false
        }
        val flow = EndSprintPolicy.flowFor(active.shield, elapsed)
        if (flow == EndFlow.CANCEL || flow == EndFlow.IMMEDIATE) return true
        val requestedAt = requestedAtMonotonic ?: return false
        val waited = try {
            Math.subtractExact(nowMonotonic, requestedAt)
        } catch (_: ArithmeticException) {
            return false
        }
        if (waited < EndSprintPolicy.delayMillis(flow)) return false
        return flow != EndFlow.SEALED || EndSprintPolicy.phraseMatches(phrase)
    }
}
