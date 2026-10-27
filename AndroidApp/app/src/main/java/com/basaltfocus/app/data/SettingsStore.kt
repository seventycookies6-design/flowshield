package com.basaltfocus.app.data

import android.content.Context
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import com.basaltfocus.core.ActiveSprint
import com.basaltfocus.core.Shield
import kotlinx.coroutines.flow.map
import org.json.JSONObject

private val Context.basaltDataStore by preferencesDataStore("basalt")

class SettingsStore(context: Context) {
    private val store = context.applicationContext.basaltDataStore
    private val document = stringPreferencesKey("settings")
    val flow = store.data.map { decode(it[document]) }

    suspend fun update(change: (Settings) -> Settings) {
        store.edit { it[document] = encode(change(decode(it[document]))) }
    }

    companion object {
        internal fun encode(s: Settings): String = JSONObject().apply {
            put("initialized", s.initialized)
            put("onboardingDone", s.onboardingDone)
            put("trialStartedAt", s.trialStartedAt)
            put("blockedPackages", org.json.JSONArray(s.blockedPackages.toList()))
            s.active?.let { a -> put("active", JSONObject().apply {
                put("id", a.id); put("startedAt", a.startedAt)
                put("plannedMinutes", a.plannedMinutes); put("shield", a.shield.name)
                put("lastSeenAt", a.lastSeenAt); put("watchedMillis", a.watchedMillis)
            }) }
            put("pendingSummaryId", s.pendingSummaryId)
            put("licensed", s.licensed); put("licenseKey", s.licenseKey)
            put("licenseEmail", s.licenseEmail); put("licenseStatus", s.licenseStatus)
            put("licenseDeviceId", s.licenseDeviceId); put("licenseCheckedAt", s.licenseCheckedAt)
            put("deviceCount", s.deviceCount); put("deviceLimit", s.deviceLimit)
        }.toString()

        internal fun decode(raw: String?): Settings {
            if (raw == null) return Settings()
            val j = JSONObject(raw)
            val a = j.optJSONObject("active")?.let {
                ActiveSprint(it.getString("id"), it.getLong("startedAt"), it.getInt("plannedMinutes"),
                    Shield.valueOf(it.getString("shield")), it.optLong("lastSeenAt", it.getLong("startedAt")),
                    it.optLong("watchedMillis"))
            }
            val blocked = j.optJSONArray("blockedPackages")
            return Settings(
                initialized = j.optBoolean("initialized"),
                onboardingDone = j.optBoolean("onboardingDone"),
                trialStartedAt = if (j.has("trialStartedAt")) j.getLong("trialStartedAt") else null,
                blockedPackages = (0 until (blocked?.length() ?: 0)).map { blocked!!.getString(it) }.toSet(),
                active = a,
                pendingSummaryId = j.optString("pendingSummaryId").takeIf { it.isNotEmpty() },
                licensed = j.optBoolean("licensed"), licenseKey = j.optString("licenseKey"),
                licenseEmail = j.optString("licenseEmail"), licenseStatus = j.optString("licenseStatus"),
                licenseDeviceId = j.optString("licenseDeviceId"),
                licenseCheckedAt = if (j.has("licenseCheckedAt")) j.getLong("licenseCheckedAt") else null,
                deviceCount = j.optInt("deviceCount"), deviceLimit = j.optInt("deviceLimit"),
            )
        }
    }
}
