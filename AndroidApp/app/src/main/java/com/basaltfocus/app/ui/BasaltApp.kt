package com.basaltfocus.app.ui

import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.graphics.drawable.toBitmap
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.window.layout.FoldingFeature
import com.basaltfocus.app.MainViewModel
import com.basaltfocus.app.blocking.*
import com.basaltfocus.app.data.Settings
import com.basaltfocus.app.data.SprintRecord
import com.basaltfocus.core.*
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.withContext

private enum class Screen(val title: String) { TODAY("Today"), BLOCKLIST("Blocklist"), HISTORY("History"), LICENSE("License"), ABOUT("About") }
private fun Shield.label() = name.lowercase().replaceFirstChar { it.titlecase() }
private fun time(millis: Long) = Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("MMM d, h:mm a"))
private fun countdown(millis: Long): String {
    val seconds = (millis.coerceAtLeast(0) + 999) / 1000
    return "%d:%02d".format(seconds / 60, seconds % 60)
}

@Composable
fun BasaltApp(model: MainViewModel, hingeFlow: StateFlow<FoldingFeature?>) {
    val settings by model.settings.collectAsStateWithLifecycle()
    val records by model.history.collectAsStateWithLifecycle()
    val message by model.message.collectAsStateWithLifecycle()
    val revision by model.permissionRevision.collectAsStateWithLifecycle()
    val hinge by hingeFlow.collectAsStateWithLifecycle()
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { now = System.currentTimeMillis(); delay(250) } }
    var screen by rememberSaveable { mutableStateOf(Screen.TODAY) }
    var permission by rememberSaveable { mutableStateOf<PermissionStep?>(null) }
    val hasAccess = TrialPolicy.hasAccess(settings.licensed, settings.trialStartedAt, now)
    val summary = records.firstOrNull { it.id == settings.pendingSummaryId }
    val locked = !hasAccess && settings.active == null && settings.pendingSummaryId == null
    val onboarding = settings.initialized && !settings.onboardingDone && settings.active == null && !locked
    val density = LocalDensity.current
    // On dual-screen devices keep the complete interaction on one side of a separating hinge.
    val pane = hinge?.let { fold ->
        if (fold.orientation == FoldingFeature.Orientation.VERTICAL) with(density) { fold.bounds.left.toDp() }
        else null
    }
    val paneHeight = hinge?.let { fold ->
        if (fold.orientation == FoldingFeature.Orientation.HORIZONTAL) with(density) { fold.bounds.top.toDp() }
        else null
    }
    BackHandler(enabled = permission != null || screen != Screen.TODAY) {
        if (permission != null) permission = null else screen = Screen.TODAY
    }
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Box(Modifier.fillMaxSize().safeDrawingPadding().imePadding(), contentAlignment = if (pane != null) Alignment.TopStart else Alignment.TopCenter) {
            val size = Modifier.widthIn(max = 640.dp).then(if (pane != null && pane > 100.dp) Modifier.width(pane) else Modifier.fillMaxWidth())
                .then(if (paneHeight != null && paneHeight > 100.dp) Modifier.height(paneHeight) else Modifier.fillMaxHeight())
            Column(size) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Image(androidx.compose.ui.res.painterResource(com.basaltfocus.app.R.drawable.basalt_mark),
                        contentDescription = null, Modifier.size(32.dp))
                    Spacer(Modifier.width(12.dp))
                    Text("Basalt", style = MaterialTheme.typography.titleLarge)
                }
                if (!settings.initialized) {
                    Page("Getting ready") { Text(message.ifEmpty { "Reading your local sprint data…" }) }
                } else if (permission != null) {
                    PermissionScreen(permission!!, revision) {
                        permission = when (permission) {
                            PermissionStep.USAGE -> PermissionStep.OVERLAY
                            PermissionStep.OVERLAY -> PermissionStep.NOTIFICATIONS
                            else -> null
                        }
                        if (permission == null && onboarding) model.onboardingDone()
                    }
                } else if (onboarding) {
                    Page("Make room for one thing") {
                        Text("Choose the apps that distract you, then set a focus sprint. Your seven-day free trial starts on this device today.")
                        Text("Soft offers a notice you can dismiss. Firm returns you home after a short notice. Sealed also keeps the blocklist fixed until the sprint ends. Apps stay open, and essential apps always stay available.")
                        Text("Your blocklist, app activity, sprints and journal stay on this phone. Only a license check contacts the server.")
                        Action("Set up permissions", primary = true) { permission = PermissionStep.USAGE }
                        Action("Set up later") { model.onboardingDone() }
                    }
                } else if (settings.pendingSummaryId != null) {
                    if (summary == null) Page("Sprint summary") { Text("Reading the saved sprint…") }
                    else SummaryScreen(summary) { model.saveJournal(summary.id, it) }
                } else {
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp)) {
                        val options = if (locked) listOf(Screen.LICENSE, Screen.ABOUT) else Screen.entries
                        options.forEach { destination ->
                            TextButton({ screen = destination }, Modifier.heightIn(min = 48.dp).keyboardRing()) {
                                Text(destination.title, color = if (screen == destination) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface)
                            }
                        }
                    }
                    if (message.isNotEmpty()) {
                        Text(message, Modifier.padding(horizontal = 24.dp, vertical = 8.dp).semantics { liveRegion = LiveRegionMode.Polite },
                            color = MaterialTheme.colorScheme.error)
                    }
                    Box(Modifier.weight(1f)) {
                        when (if (locked && screen != Screen.ABOUT) Screen.LICENSE else screen) {
                            Screen.TODAY -> if (settings.active != null) RunningScreen(settings.active!!, now, model) { screen = Screen.BLOCKLIST }
                                else TodayScreen(settings, records, now, model, { screen = Screen.BLOCKLIST }, { permission = PermissionStep.USAGE })
                            Screen.BLOCKLIST -> BlocklistScreen(settings, model)
                            Screen.HISTORY -> HistoryScreen(records)
                            Screen.LICENSE -> LicenseScreen(settings, now, model, locked)
                            Screen.ABOUT -> AboutScreen { permission = PermissionStep.USAGE }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TodayScreen(s: Settings, records: List<SprintRecord>, now: Long, model: MainViewModel,
                        blocklist: () -> Unit, permissions: () -> Unit) {
    val context = LocalContext.current
    var minutes by rememberSaveable { mutableStateOf("25") }
    var shield by rememberSaveable { mutableStateOf(Shield.SOFT) }
    val today = Instant.ofEpochMilli(now).atZone(ZoneId.systemDefault()).toLocalDate()
    Page("Today") {
        Panel {
            Text("MOMENTUM", style = MaterialTheme.typography.labelSmall)
            Text("%.1f".format(records.firstOrNull()?.momentumAfter ?: 0.0), style = MaterialTheme.typography.displayMedium)
            Text("Finished sprints build momentum. A 25-minute sprint adds 10; shorter and longer sprints add 5 to 30. Nothing changes while you are away.")
        }
        Text("Sprint length", style = MaterialTheme.typography.titleMedium)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(15, 25, 45, 60).forEach { length ->
                FilterChip(minutes == "$length", { minutes = "$length" }, label = { Text("$length min") },
                    modifier = Modifier.heightIn(min = 48.dp).keyboardRing())
            }
        }
        OutlinedTextField(minutes, { minutes = it.filter(Char::isDigit).take(3) }, label = { Text("Custom minutes (1–180)") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.fillMaxWidth())
        Text("Shield", style = MaterialTheme.typography.titleMedium)
        Shield.entries.forEach { level ->
            Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surface) {
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(shield == level, onClick = { shield = level })
                    .keyboardRing().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(shield == level, onClick = null)
                    Spacer(Modifier.width(8.dp))
                    Column { Text(level.label(), style = MaterialTheme.typography.titleMedium); Text(ShieldCopy.promise(level)) }
                }
            }
        }
        Text("${s.blockedPackages.size} apps on your blocklist. Essential apps always stay available.")
        Action("Choose blocked apps", onClick = blocklist)
        if (!Permissions.canBlock(context)) {
            Text("Usage Access and display over other apps are needed for blocking.")
            Action("Review permissions", primary = true, onClick = permissions)
        }
        Action("Start sprint", enabled = minutes.toIntOrNull()?.let { it in 1..180 } == true && Permissions.canBlock(context), primary = true) {
            model.start(minutes.toInt(), shield)
        }
        Text(if (s.licensed) "License active" else "Free trial · ${TrialPolicy.daysLeft(s.trialStartedAt, now)} days left")
        Text("Today's sprints", style = MaterialTheme.typography.titleMedium)
        val todays = records.filter { Instant.ofEpochMilli(it.startedAt).atZone(ZoneId.systemDefault()).toLocalDate() == today }
        if (todays.isEmpty()) Text("No sprints yet. Pick a length and start when you are ready.")
        todays.forEach { RecordCard(it) }
    }
}

@Composable
private fun RunningScreen(a: ActiveSprint, now: Long, model: MainViewModel, blocklist: () -> Unit) {
    var requestedAt by remember(a.id) { mutableStateOf<Long?>(null) }
    var phrase by remember(a.id) { mutableStateOf("") }
    var openedFlow by remember(a.id) { mutableStateOf<EndFlow?>(null) }
    val status by SprintService.status.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val remaining = a.endsAt - now
    val progress = (remaining.toFloat() / (a.plannedMinutes * 60_000)).coerceIn(0f, 1f)
    val primary = MaterialTheme.colorScheme.primary
    val track = MaterialTheme.colorScheme.outlineVariant
    Page("${a.shield.label()} sprint") {
        Box(Modifier.fillMaxWidth().heightIn(min = 260.dp).drawBehind {
            val radius = minOf(size.width, size.height) / 2 - 12.dp.toPx()
            val center = Offset(size.width / 2, size.height / 2)
            drawCircle(track, radius, center, style = Stroke(4.dp.toPx()))
            drawArc(primary, -90f, 360f * progress, false,
                topLeft = center - Offset(radius, radius), size = androidx.compose.ui.geometry.Size(radius * 2, radius * 2),
                style = Stroke(4.dp.toPx()))
        }.semantics { contentDescription = "Sprint time remaining ${countdown(remaining)}" }, contentAlignment = Alignment.Center) {
            Text(countdown(remaining), Modifier.padding(24.dp), style = if (androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f)
                MaterialTheme.typography.displayMedium else MaterialTheme.typography.displayLarge)
        }
        Text(ShieldCopy.promise(a.shield))
        Text(if (Permissions.canBlock(context)) status else "Blocking paused: check permissions. Your sprint timer continues.")
        Action(if (EndSprintPolicy.flowFor(a.shield, now - a.startedAt) == EndFlow.CANCEL) "Cancel sprint" else "End sprint") {
            val flow = EndSprintPolicy.flowFor(a.shield, System.currentTimeMillis() - a.startedAt)
            if (flow == EndFlow.CANCEL || flow == EndFlow.IMMEDIATE) model.end(a.id, null, null)
            else { openedFlow = flow; requestedAt = SystemClock.elapsedRealtime() }
        }
        if (now - a.startedAt < EndSprintPolicy.graceMillis) Text("Cancel within the first two minutes with no record or momentum change.")
        Action("View blocklist", onClick = blocklist)
    }
    if (requestedAt != null) {
        val flow = openedFlow!!
        val delayLeft = (EndSprintPolicy.delayMillis(flow) - (SystemClock.elapsedRealtime() - requestedAt!!)).coerceAtLeast(0)
        AlertDialog(onDismissRequest = { requestedAt = null; phrase = "" }, title = { Text("End this sprint early?") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(if (flow == EndFlow.SEALED) "Ending early reduces momentum by 30% and 5, floored at zero. Wait 30 seconds, then type \"end my sprint\"."
                        else "Ending early reduces momentum by 15% and 2, floored at zero. Wait 5 seconds to confirm.")
                    if (delayLeft > 0) Text("${(delayLeft + 999) / 1000} seconds remaining")
                    if (flow == EndFlow.SEALED) OutlinedTextField(phrase, { phrase = it },
                        label = { Text("Type end my sprint") }, modifier = Modifier.fillMaxWidth())
                }
            }, confirmButton = {
                TextButton({ model.end(a.id, requestedAt, phrase); requestedAt = null; phrase = "" },
                    Modifier.heightIn(min = 48.dp).keyboardRing(),
                    enabled = delayLeft == 0L && (flow != EndFlow.SEALED || EndSprintPolicy.phraseMatches(phrase))) { Text("End anyway") }
            }, dismissButton = { TextButton({ requestedAt = null; phrase = "" }, Modifier.heightIn(min = 48.dp).keyboardRing()) { Text("Keep focusing") } })
    }
}

@Composable
private fun SummaryScreen(record: SprintRecord, save: (String) -> Unit) {
    var journal by rememberSaveable(record.id) { mutableStateOf(record.journal) }
    Page(record.outcome) {
        Text("${record.plannedMinutes} planned ${if (record.plannedMinutes == 1) "minute" else "minutes"} · ${record.shield.lowercase().replaceFirstChar { it.titlecase() }} shield")
        Text("Momentum %.1f → %.1f (%+.1f)".format(record.momentumBefore, record.momentumAfter, record.momentumAfter - record.momentumBefore))
        Text("What moved?", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(journal, { journal = it.replace('\n', ' ').take(280) }, label = { Text("One line, just for you") },
            modifier = Modifier.fillMaxWidth(), singleLine = true)
        Text("Saved on your phone. A blank line is fine.")
        Action("Save and finish", primary = true) { save(journal) }
    }
}

@Composable
private fun HistoryScreen(records: List<SprintRecord>) {
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(vertical = 24.dp)) {
        item { Text("History", style = MaterialTheme.typography.headlineLarge) }
        if (records.isEmpty()) item { Text("Your finished and interrupted sprints will appear here. Start a sprint from Today.") }
        items(records, key = { it.id }) { RecordCard(it) }
    }
}

@Composable
private fun RecordCard(record: SprintRecord) {
    Panel {
        Text("${record.outcome} · ${record.plannedMinutes} min", style = MaterialTheme.typography.titleMedium)
        Text("${time(record.startedAt)} · ${record.shield.lowercase().replaceFirstChar { it.titlecase() }}")
        Text("Momentum %+.1f → %.1f".format(record.momentumAfter - record.momentumBefore, record.momentumAfter))
        if (record.journal.isNotBlank()) Text(record.journal)
    }
}

@Composable
private fun BlocklistScreen(s: Settings, model: MainViewModel) {
    val context = LocalContext.current
    var search by rememberSaveable { mutableStateOf("") }
    var apps by remember { mutableStateOf<List<LaunchableApp>?>(null) }
    LaunchedEffect(Unit) { apps = withContext(Dispatchers.IO) { AppCatalog.launchable(context) } }
    val editable = BlockPolicy.blocklistEditable(s.active?.shield)
    val visible = apps.orEmpty().filter { it.label.contains(search, true) || it.packageName.contains(search, true) }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(vertical = 24.dp)) {
        item { Text("Blocklist", style = MaterialTheme.typography.headlineLarge) }
        item { Text(if (editable) "Choose launchable apps. Your choices stay on this phone." else "Sealed keeps the list locked until this sprint ends.") }
        item { Text("Settings, phone, emergency apps, launchers and Play Store always stay available.", style = MaterialTheme.typography.bodySmall) }
        item(key = "search") { OutlinedTextField(search, { search = it }, label = { Text("Search apps") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
        if (apps == null) item { Text("Reading launchable apps…") }
        else if (visible.isEmpty()) item { Text("No matching apps. Try another search.") }
        items(visible, key = { it.packageName }) { app ->
                    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        val icon = remember(app.packageName) { app.icon.toBitmap(48, 48).asImageBitmap() }
                        Image(icon, contentDescription = null, modifier = Modifier.size(40.dp))
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) { Text(app.label); Text(app.packageName, style = MaterialTheme.typography.bodySmall) }
                        Checkbox(app.packageName in s.blockedPackages, { model.block(app.packageName, it) }, enabled = editable,
                            modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp).keyboardRing().semantics { contentDescription = "Block ${app.label}" })
                    }
        }
    }
}

@Composable
private fun LicenseScreen(s: Settings, now: Long, model: MainViewModel, locked: Boolean) {
    var input by rememberSaveable { mutableStateOf("") }
    val busy by model.activating.collectAsStateWithLifecycle()
    val message by model.licenseMessage.collectAsStateWithLifecycle()
    Page(if (locked) "Your free trial has ended" else "License") {
        Text(when { s.licensed -> "License active on this device."; locked -> "Enter your license key to unlock Basalt."; else -> "Free trial · ${TrialPolicy.daysLeft(s.trialStartedAt, now)} days left on this device." })
        Text("Already bought Basalt? Enter your key or purchase email.")
        OutlinedTextField(input, { input = it }, enabled = !busy, label = { Text("License key or purchase email") },
            singleLine = true, modifier = Modifier.fillMaxWidth(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii))
        Action(if (busy) "Checking license…" else "Activate license", enabled = input.isNotBlank() && !busy, primary = true) { model.activate(input) }
        if (message.isNotEmpty()) Text(message, Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        if (s.deviceLimit > 0) Text("${s.deviceCount} of ${s.deviceLimit} device seats in use.")
        Text("This check sends your key or purchase email, a salted device hash, and your phone's manufacturer and model to the license server. Your app activity and journal are never sent.")
        Text("An active license keeps working offline. A confirmed server rejection removes access. A first check can take about a minute while the server wakes.")
    }
}

@Composable
private fun AboutScreen(permissions: () -> Unit) {
    val context = LocalContext.current
    var notices by remember { mutableStateOf(false) }
    Page("About Basalt") {
        Text("Version 0.1.0 · Android closed test")
        Text("A focus timer with three shields. Your phone remains yours: you can always open Settings, use your phone, or uninstall Basalt. Apps stay open when you return to focus.")
        Text("Privacy", style = MaterialTheme.typography.titleMedium)
        Text("Basalt reads foreground-app package names only while a sprint runs. Your blocklist, sprint history and one-line journal stay in app storage. No analytics, ads, accounts or sync. The only app network request is the license check described on the License screen.")
        Text("Android Auto Backup can back up your local trial, settings and history according to your phone's backup settings. Restoring on a different device requires another license check. Clearing app data may restart the trial and removes local history.")
        Text("Blocking is best effort. Android or your phone's battery saver can stop the service. Reopen Basalt to resume a saved sprint. Permissions can be changed at any time in Android Settings.")
        Action("Review permissions", onClick = permissions)
        Action("System battery settings") { runCatching { context.startActivity(android.content.Intent(android.provider.Settings.ACTION_BATTERY_SAVER_SETTINGS)) } }
        Action("Open-source notices") { notices = !notices }
        if (notices) Text(remember { context.assets.open("Inter-OFL.txt").bufferedReader().use { it.readText() } }, style = MaterialTheme.typography.bodySmall)
    }
}
