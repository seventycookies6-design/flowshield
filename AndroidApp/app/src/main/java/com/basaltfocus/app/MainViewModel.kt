package com.basaltfocus.app

import android.app.Application
import android.content.Intent
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.basaltfocus.app.blocking.*
import com.basaltfocus.core.Shield
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job

class MainViewModel(application: Application) : AndroidViewModel(application) {
    val repository = (application as BasaltApplication).repository
    val settings = repository.settings
    val history = repository.history
    val message = MutableStateFlow("")
    val licenseMessage = MutableStateFlow("")
    val activating = MutableStateFlow(false)
    val permissionRevision = MutableStateFlow(0)
    private var refreshJob: Job? = null

    init {
        viewModelScope.launch {
            val initialized = runCatching { repository.initialize(); repository.recover() }
                .onFailure { message.value = "Basalt couldn't read its local data. Close and reopen the app. Your trial has not been reset." }
            if (initialized.isFailure) return@launch
            resumeService()
            refreshJob = viewModelScope.launch { runCatching { repository.refreshLicense() } }
        }
    }

    fun onResume() {
        permissionRevision.value++
        viewModelScope.launch { if (settings.value.initialized) { repository.settleIfElapsed(System.currentTimeMillis()); resumeService() } }
    }

    private suspend fun resumeService() {
        if (repository.current().active == null) return
        try { getApplication<Application>().startForegroundService(Intent(getApplication(), SprintService::class.java)) }
        catch (_: RuntimeException) { message.value = "Your sprint is saved. Open Basalt again to resume blocking." }
    }

    fun start(minutes: Int, shield: Shield) = viewModelScope.launch {
        val error = repository.start(minutes, shield)
        message.value = error.orEmpty()
        if (error == null) resumeService()
    }
    fun end(sprintId: String, requestedAt: Long?, phrase: String?) = viewModelScope.launch {
        message.value = repository.end(sprintId, requestedAt, phrase).orEmpty()
        if (repository.current().active == null) getApplication<Application>().stopService(Intent(getApplication(), SprintService::class.java))
    }
    fun block(packageName: String, checked: Boolean) = viewModelScope.launch {
        message.value = repository.setBlocked(packageName, checked).orEmpty()
    }
    fun onboardingDone() = viewModelScope.launch { repository.finishOnboarding() }
    fun letStarredContactsThrough(enabled: Boolean) = viewModelScope.launch {
        repository.setLetStarredContactsThrough(enabled)
    }
    fun saveJournal(id: String, line: String) = viewModelScope.launch { repository.saveJournal(id, line) }
    fun activate(input: String) {
        if (activating.value) return
        refreshJob?.cancel()
        activating.value = true
        viewModelScope.launch {
            try { licenseMessage.value = repository.activate(input) { licenseMessage.value = it } }
            finally { activating.value = false }
        }
    }
}
