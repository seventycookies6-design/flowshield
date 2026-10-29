package com.basaltfocus.app.data

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.basaltfocus.core.ActiveSprint

data class Settings(
    val initialized: Boolean = false,
    val onboardingDone: Boolean = false,
    val trialStartedAt: Long? = null,
    val blockedPackages: Set<String> = emptySet(),
    val active: ActiveSprint? = null,
    val pendingSummaryId: String? = null,
    // Entitlement seam for #413: a future verified Play purchase can grant access here.
    // This build accepts only the existing /validate protocol; it has no billing code.
    val licensed: Boolean = false,
    val licenseKey: String = "",
    val licenseEmail: String = "",
    val licenseStatus: String = "",
    val licenseDeviceId: String = "",
    val licenseCheckedAt: Long? = null,
    val deviceCount: Int = 0,
    val deviceLimit: Int = 0,
    val letStarredContactsThrough: Boolean = false,
)

@Entity(tableName = "sprints")
data class SprintRecord(
    @PrimaryKey val id: String,
    val startedAt: Long,
    val endedAt: Long,
    val plannedMinutes: Int,
    val shield: String,
    val outcome: String,
    val momentumBefore: Double,
    val momentumAfter: Double,
    val journal: String = "",
)
