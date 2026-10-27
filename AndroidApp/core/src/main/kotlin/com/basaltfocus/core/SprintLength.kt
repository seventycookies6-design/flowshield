package com.basaltfocus.core

/** Sprint lengths, as on Windows' Today page (TodayViewModel.SprintLengths and its custom range). */
object SprintLength {
    val presets = listOf(15, 25, 45, 60, 90)
    const val customMin = 5
    const val customMax = 240

    /** Debug builds may run one-minute sprints to prove blocking quickly; release builds never do. */
    fun minimum(allowShort: Boolean): Int = if (allowShort) 1 else customMin

    fun isValid(minutes: Int?, allowShort: Boolean = false): Boolean =
        minutes != null && minutes in minimum(allowShort)..customMax

    fun error(minutes: Int?, allowShort: Boolean = false): String? =
        if (isValid(minutes, allowShort)) null
        else "Choose between ${minimum(allowShort)} and $customMax minutes."
}
