package com.basaltfocus.core

import org.junit.Assert.*
import org.junit.Test

class BlockPolicyTest {
    @Test fun anotherInstalledBasaltBuildAlsoStaysAvailable() {
        assertTrue(BlockPolicy.neverBlock("design.seventycookies6.basalt", "com.basaltfocus.app", emptySet()))
    }
    private val own = "com.basaltfocus.app"
    private val app = "com.example.distraction"
    private val protectedPackages = setOf("com.vendor.customhome", "com.vendor.accessible.dialer")

    private fun decide(
        soft: SoftOverlayPolicy,
        packageName: String? = app,
        shield: Shield = Shield.SOFT,
        active: Boolean = true,
        now: Long = 0,
        blocklist: Set<String> = setOf(app),
    ) = BlockPolicy.decision(active, shield, packageName, blocklist, own, protectedPackages, soft, now)

    @Test fun sealedAloneLocksBlocklistEdits() {
        assertTrue(BlockPolicy.blocklistEditable(null))
        assertTrue(BlockPolicy.blocklistEditable(Shield.SOFT))
        assertTrue(BlockPolicy.blocklistEditable(Shield.FIRM))
        assertFalse(BlockPolicy.blocklistEditable(Shield.SEALED))
    }

    @Test fun ownAppAndDynamicallyDiscoveredProtectedPackagesAreNeverBlocked() {
        for (packageName in protectedPackages + own + own.uppercase()) {
            assertTrue(packageName, BlockPolicy.neverBlock(packageName, own, protectedPackages))
        }
        assertFalse(BlockPolicy.neverBlock(app, own, protectedPackages))
    }

    @Test fun settingsSystemUiInstallersStoresDialersEmergencyAppsAndLaunchersAreProtected() {
        val critical = listOf("android", "com.android.settings", "com.android.systemui",
            "com.android.vending", "com.android.packageinstaller", "com.google.android.packageinstaller",
            "com.android.permissioncontroller", "com.google.android.permissioncontroller",
            "com.sec.android.app.samsungapps", "com.amazon.venezia", "org.fdroid.fdroid",
            "com.huawei.appmarket", "com.xiaomi.mipicks", "com.heytap.market",
            "com.android.phone", "com.android.dialer", "com.google.android.dialer",
            "com.samsung.android.dialer", "com.android.incallui", "com.samsung.android.incallui",
            "com.android.emergency", "com.google.android.apps.safetyhub",
            "com.samsung.android.app.telephonyui", "com.sec.android.app.safetyassurance",
            "com.android.launcher", "com.android.launcher3", "com.google.android.apps.nexuslauncher",
            "com.sec.android.app.launcher", "com.miui.home", "com.huawei.android.launcher",
            "com.microsoft.launcher", "com.teslacoilsw.launcher", "com.vendor.settings",
            "com.vendor.launcher3", "com.vendor.emergency.service", "com.android.stk",
            "com.google.android.apps.accessibility.voiceaccess", "com.google.android.marvin.talkback",
            "com.samsung.android.accessibility.talkback", "com.google.android.accessibility.switchaccess")
        for (packageName in critical) {
            assertTrue(packageName, BlockPolicy.neverBlock(packageName, own, emptySet()))
            for (shield in Shield.values()) {
                val soft = SoftOverlayPolicy()
                assertEquals("$shield $packageName", BlockDecision.NONE,
                    decide(soft, packageName, shield, blocklist = setOf(packageName)))
                assertEquals(0, soft.tries)
            }
        }
    }

    @Test fun inactiveUnknownEmptyUnlistedOrProtectedForegroundDoesNothing() {
        for (shield in Shield.values()) {
            val soft = SoftOverlayPolicy()
            assertEquals(BlockDecision.NONE, decide(soft, shield = shield, active = false))
            assertEquals(BlockDecision.NONE, decide(soft, null, shield))
            assertEquals(BlockDecision.NONE, decide(soft, "", shield, blocklist = setOf("")))
            assertEquals(BlockDecision.NONE, decide(soft, " ", shield, blocklist = setOf(" ")))
            assertEquals(BlockDecision.NONE, decide(soft, "com.example.work", shield))
            assertEquals(BlockDecision.NONE, decide(soft, own, shield, blocklist = setOf(own)))
            assertEquals(BlockDecision.NONE, decide(soft, protectedPackages.first(), shield,
                blocklist = protectedPackages))
            assertEquals(0, soft.tries)
        }
    }

    @Test fun softUsesOncePerSightingNoticesAndTheFiveMinuteAllowance() {
        val soft = SoftOverlayPolicy()
        assertEquals(BlockDecision.SOFT_NOTICE, decide(soft))
        assertEquals(BlockDecision.NONE, decide(soft, now = 650))
        assertEquals(1, soft.tries)
        assertEquals(BlockDecision.NONE, decide(soft, "com.example.work", now = 1_000))
        assertEquals(BlockDecision.SOFT_NOTICE, decide(soft, now = 2_000))
        soft.allowFiveMinutes(app, 2_000)
        assertEquals(BlockDecision.NONE, decide(soft, now = 2_001))
        decide(soft, "com.example.work", now = 301_999)
        assertEquals(BlockDecision.SOFT_NOTICE, decide(soft, now = 302_000))
    }

    @Test fun nonblockedForegroundAlwaysResetsTheSoftSighting() {
        for (packageName in listOf(null, "", own, protectedPackages.first(), "com.example.work")) {
            val soft = SoftOverlayPolicy()
            assertEquals(BlockDecision.SOFT_NOTICE, decide(soft))
            assertEquals(BlockDecision.NONE, decide(soft, packageName, now = 1))
            assertFalse(soft.leftForeground())
            assertEquals(BlockDecision.SOFT_NOTICE, decide(soft, now = 2))
        }
    }

    @Test fun inactiveEnforcementAlsoClearsAnySoftSighting() {
        val soft = SoftOverlayPolicy()
        decide(soft)
        assertEquals(BlockDecision.NONE, decide(soft, active = false))
        assertEquals(BlockDecision.SOFT_NOTICE, decide(soft))
    }

    @Test fun firmAndSealedReturnHomeOnEveryReopeningWithoutSoftAllowances() {
        for (shield in listOf(Shield.FIRM, Shield.SEALED)) {
            val soft = SoftOverlayPolicy()
            soft.allowFiveMinutes(app, 0)
            repeat(3) { reopening ->
                assertEquals(BlockDecision.RETURN_HOME_NOTICE,
                    decide(soft, shield = shield, now = reopening * 650L))
                decide(soft, "com.example.work", shield, now = reopening * 650L + 1)
            }
            assertEquals(BlockDecision.RETURN_HOME_NOTICE, decide(soft, shield = shield))
            assertEquals(BlockDecision.RETURN_HOME_NOTICE, decide(soft, shield = shield))
            assertEquals(0, soft.tries)
        }
    }

    @Test fun safetyMatchingDoesNotAccidentallyExemptUnrelatedAppNames() {
        for (packageName in listOf(app, "com.example.launcherclub", "com.example.settingsgame",
            "com.example.dialerfun", "com.example.android.vending.clone")) {
            assertFalse(packageName, BlockPolicy.neverBlock(packageName, own, emptySet()))
        }
    }
}
