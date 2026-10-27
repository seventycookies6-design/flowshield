package com.basaltfocus.core

object ShieldCopy {
    fun promise(shield: Shield): String = when (shield) {
        Shield.SOFT -> "Shows a notice you can dismiss."
        Shield.FIRM -> "Shows a notice, then returns you to the home screen."
        Shield.SEALED -> "Shows a notice, then returns you to the home screen and locks the list until the sprint ends."
    }
}
