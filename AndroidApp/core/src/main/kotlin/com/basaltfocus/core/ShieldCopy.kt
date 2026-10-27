package com.basaltfocus.core

/** Each shield's promise on Android. Windows' ShieldCopy says "Closes"; Android Basalt never closes an app. */
object ShieldCopy {
    fun promise(shield: Shield): String = when (shield) {
        Shield.SOFT -> "Shows a notice you can dismiss."
        Shield.FIRM -> "Shows a notice, then returns you to the home screen."
        Shield.SEALED -> "Shows a notice, then returns you to the home screen and locks the list until the sprint ends."
    }

    /** Same scenarios as Windows' ShieldCopy.BestFor. */
    fun bestFor(shield: Shield): String = when (shield) {
        Shield.SOFT -> "Best for classes or light work."
        Shield.FIRM -> "Best for homework."
        Shield.SEALED -> "Best for exams and deep work."
    }

    fun label(shield: Shield): String = when (shield) {
        Shield.SOFT -> "Soft"
        Shield.FIRM -> "Firm"
        Shield.SEALED -> "Sealed"
    }
}
