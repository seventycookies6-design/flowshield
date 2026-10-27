package com.basaltfocus.app.license

/** Pure Windows waiting copy and retry schedule; no clock, network or UI dependencies. */
object LicenseWaitCopy {
    const val ContactingMessage = "Contacting the license server…"
    const val WakingUpMessage = "The server is waking up. This can take up to a minute."
    const val WakingUpAfterSeconds = 8.0
    val RetryDelaysSeconds: List<Double> = listOf(2.0, 5.0)
    const val FirstAttemptTimeoutSeconds = 35.0
    const val RetryAttemptTimeoutSeconds = 15.0
    val TotalAttempts: Int get() = RetryDelaysSeconds.size + 1
    const val TotalBudgetSeconds = 72.0

    fun timeoutForAttempt(attempt: Int): Double =
        if (attempt <= 1) FirstAttemptTimeoutSeconds else RetryAttemptTimeoutSeconds

    fun messageFor(elapsedSeconds: Double): String =
        if (elapsedSeconds < WakingUpAfterSeconds) ContactingMessage else WakingUpMessage
}
