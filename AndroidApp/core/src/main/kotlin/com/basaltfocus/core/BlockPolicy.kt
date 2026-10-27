package com.basaltfocus.core

import java.util.Locale

enum class BlockDecision { NONE, SOFT_NOTICE, RETURN_HOME_NOTICE }

object BlockPolicy {
    // Runtime-discovered HOME/dialer handlers supplement these known packages. Safety wins
    // over interception when an unfamiliar vendor uses one of these critical component names.
    private val criticalComponent = Regex("(?:^|\\.)(?:settings|systemui|launcher[0-9]*|dialer|incallui|emergency)(?:\\.|$)")
    private val criticalPackages = setOf(
        "android",
        "design.seventycookies6.basalt",
        "com.android.settings",
        "com.android.systemui",
        "com.android.vending",
        "com.android.packageinstaller",
        "com.google.android.packageinstaller",
        "com.android.permissioncontroller",
        "com.google.android.permissioncontroller",
        "com.sec.android.app.samsungapps",
        "com.amazon.venezia",
        "org.fdroid.fdroid",
        "org.fdroid.basic",
        "com.huawei.appmarket",
        "com.xiaomi.mipicks",
        "com.xiaomi.market",
        "com.oppo.market",
        "com.heytap.market",
        "com.bbk.appstore",
        "com.vivo.appstore",
        "com.android.phone",
        "com.android.server.telecom",
        "com.android.providers.telephony",
        "com.android.contacts",
        "com.google.android.contacts",
        "com.samsung.android.contacts",
        "com.android.dialer",
        "com.google.android.dialer",
        "com.samsung.android.dialer",
        "com.android.incallui",
        "com.samsung.android.incallui",
        "com.android.emergency",
        "com.google.android.apps.safetyhub",
        "com.samsung.android.app.telephonyui",
        "com.sec.android.app.safetyassurance",
        "com.samsung.android.emergency",
        "com.android.launcher",
        "com.android.launcher2",
        "com.android.launcher3",
        "com.google.android.launcher",
        "com.google.android.apps.nexuslauncher",
        "com.sec.android.app.launcher",
        "com.samsung.android.app.launcher",
        "com.miui.home",
        "com.huawei.android.launcher",
        "com.motorola.launcher3",
        "com.oppo.launcher",
        "com.bbk.launcher2",
        "com.vivo.launcher",
        "com.transsion.xoslauncher",
        "com.microsoft.launcher",
        "com.teslacoilsw.launcher",
    )

    fun neverBlock(packageName: String, ownPackage: String, protectedPackages: Set<String>): Boolean {
        val key = packageName.trim().lowercase(Locale.ROOT)
        return key.isEmpty()
            || key.equals(ownPackage.trim(), ignoreCase = true)
            || protectedPackages.any { key.equals(it.trim(), ignoreCase = true) }
            || key in criticalPackages
            || criticalComponent.containsMatchIn(key)
    }

    fun blocklistEditable(activeShield: Shield?): Boolean = activeShield != Shield.SEALED

    /** Firm/Sealed intentionally have no sighting gate: the platform owns notice/HOME lifetimes. */
    fun decision(
        active: Boolean,
        shield: Shield,
        packageName: String?,
        blocklist: Set<String>,
        ownPackage: String,
        protectedPackages: Set<String>,
        soft: SoftOverlayPolicy,
        nowMillis: Long,
    ): BlockDecision {
        if (!active || packageName == null
            || neverBlock(packageName, ownPackage, protectedPackages)
            || blocklist.none { it.equals(packageName, ignoreCase = true) }
        ) {
            soft.leftForeground()
            return BlockDecision.NONE
        }
        if (shield == Shield.SOFT) {
            return if (soft.shouldShow(packageName, nowMillis)) BlockDecision.SOFT_NOTICE else BlockDecision.NONE
        }
        soft.leftForeground()
        return BlockDecision.RETURN_HOME_NOTICE
    }
}
