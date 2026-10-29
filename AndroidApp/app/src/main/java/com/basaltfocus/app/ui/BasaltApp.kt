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
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import com.basaltfocus.app.BuildConfig
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
private fun shieldLabel(stored: String) = Shield.entries.firstOrNull { it.name == stored }?.let(ShieldCopy::label) ?: stored
private fun summaryTitle(outcome: String) = when (outcome) {
    "Completed" -> "Sprint complete"
    "Ended early" -> "Sprint ended early"
    "Interrupted" -> "Sprint interrupted"
    else -> outcome
}
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
                            PermissionStep.OVERLAY -> if (android.os.Build.VERSION.SDK_INT >= 33) PermissionStep.NOTIFICATIONS else null
                            else -> null
                        }
                        // First run continues to the blocklist, the next thing a new user needs.
                        if (permission == null && onboarding) { model.onboardingDone(); screen = Screen.BLOCKLIST }
                    }
                } else if (onboarding) {
                    Page("Make room for one thing") {
                        Text("Choose the apps that distract you, then start a focus sprint. When one of them opens during a sprint, Basalt shows a notice over it.")
                        Shield.entries.forEach { Text("${ShieldCopy.label(it)}: ${ShieldCopy.promise(it)}") }
                        Text("Basalt never closes your apps, and Settings, your phone app, emergency calls and the Play Store always stay available.")
                        Text("Your blocklist, app activity, sprints and journal stay on this phone. Only a license check contacts a server.")
                        Text("Everything is unlocked for 7 days on this device.", style = MaterialTheme.typography.bodySmall)
                        Text("Next, Basalt explains each permission it needs before Android asks you.", style = MaterialTheme.typography.bodySmall)
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
                            Screen.TODAY -> if (settings.active != null)
                                RunningScreen(settings.active!!, now, records.firstOrNull()?.momentumAfter ?: 0.0, model) { screen = Screen.BLOCKLIST }
                                else TodayScreen(settings, records, now, model, { screen = Screen.BLOCKLIST },
                                    { permission = PermissionStep.USAGE }, { screen = Screen.HISTORY },
                                    { permission = PermissionStep.DND })
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
                        blocklist: () -> Unit, permissions: () -> Unit, history: () -> Unit, dndPermission: () -> Unit) {
    val context = LocalContext.current
    val revision by model.permissionRevision.collectAsStateWithLifecycle()
    val canBlock = remember(revision) { Permissions.canBlock(context) }
    val dndGranted = remember(revision) { Permissions.dnd(context) }
    var preset by rememberSaveable { mutableIntStateOf(25) }
    var custom by rememberSaveable { mutableStateOf("") }
    var customSelected by rememberSaveable { mutableStateOf(false) }
    var shield by rememberSaveable { mutableStateOf(Shield.SOFT) }
    val minutes = if (customSelected) custom.toIntOrNull() else preset
    val lengthError = if (customSelected) SprintLength.error(minutes, BuildConfig.DEBUG) else null
    val today = Instant.ofEpochMilli(now).atZone(ZoneId.systemDefault()).toLocalDate()
    val momentum = records.firstOrNull()?.momentumAfter ?: 0.0
    Page("Today") {
        Panel {
            Text("MOMENTUM", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(Momentum.display(momentum), style = MaterialTheme.typography.displayMedium,
                modifier = Modifier.semantics { contentDescription = "Momentum ${Momentum.display(momentum)}" })
            Text(Momentum.explanation.first(), color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(history, Modifier.heightIn(min = 48.dp).keyboardRing()) { Text("How momentum works") }
        }
        Text("Sprint length", style = MaterialTheme.typography.titleMedium)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SprintLength.presets.forEach { length ->
                FilterChip(!customSelected && preset == length, { preset = length; customSelected = false },
                    label = { Text("$length min") }, colors = chipColors(), modifier = Modifier.heightIn(min = 48.dp).keyboardRing())
            }
            FilterChip(customSelected, { customSelected = true }, label = { Text("Custom") }, colors = chipColors(),
                modifier = Modifier.heightIn(min = 48.dp).keyboardRing())
        }
        if (customSelected) {
            OutlinedTextField(custom, { custom = it.filter(Char::isDigit).take(3) },
                label = { Text("Minutes (${SprintLength.minimum(BuildConfig.DEBUG)} to ${SprintLength.customMax})") },
                isError = lengthError != null && custom.isNotEmpty(),
                supportingText = { if (lengthError != null && custom.isNotEmpty()) Text(lengthError) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true,
                modifier = Modifier.fillMaxWidth())
        }
        Text("Shield", style = MaterialTheme.typography.titleMedium)
        Column(Modifier.selectableGroup(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Shield.entries.forEach { level ->
                val selected = shield == level
                Surface(shape = MaterialTheme.shapes.medium,
                    color = if (selected) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.surface,
                    border = BorderStroke(if (selected) 2.dp else 1.dp,
                        if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant)) {
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                        .selectable(selected, onClick = { shield = level }, role = Role.RadioButton)
                        .keyboardRing().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected, onClick = null)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(ShieldCopy.label(level), style = MaterialTheme.typography.titleMedium)
                            Text(ShieldCopy.promise(level))
                            Text(ShieldCopy.bestFor(level), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
        val count = s.blockedPackages.size
        Text(if (count == 0) "No apps on your blocklist yet." else "$count app${if (count == 1) "" else "s"} on your blocklist.")
        Action("Choose blocked apps", onClick = blocklist)
        Panel {
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .toggleable(s.letStarredContactsThrough, role = Role.Switch, onValueChange = { enabled ->
                    model.letStarredContactsThrough(enabled)
                    if (enabled && !dndGranted) dndPermission()
                }).keyboardRing(), verticalAlignment = Alignment.CenterVertically) {
                Text("Let starred contacts through", Modifier.weight(1f))
                Switch(s.letStarredContactsThrough, onCheckedChange = null)
            }
            Text("During a sprint, Do Not Disturb allows calls and messages from starred contacts and silences everyone else. Choose people by starring them in Contacts. Basalt reads no contacts. Android's system exceptions still apply.")
            if (s.letStarredContactsThrough && !dndGranted) Text("Do Not Disturb access is off. This setting will change nothing until you allow it.")
            Action("About Do Not Disturb access", onClick = dndPermission)
        }
        if (!canBlock) {
            Text("Basalt needs Usage Access and display over other apps before a sprint can block anything.")
            Action("Review permissions", primary = true, onClick = permissions)
        }
        Action("Start sprint", enabled = lengthError == null && minutes != null && canBlock, primary = true) {
            model.start(minutes!!, shield)
        }
        Text(trialLine(s, now), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Today's sprints", style = MaterialTheme.typography.titleMedium)
        val todays = records.filter { Instant.ofEpochMilli(it.startedAt).atZone(ZoneId.systemDefault()).toLocalDate() == today }
        if (todays.isEmpty()) Text("No sprints yet today. Pick a length and a shield, then start when you're ready.")
        todays.forEach { RecordCard(it) }
    }
}

@Composable
private fun chipColors() = FilterChipDefaults.filterChipColors(
    selectedContainerColor = MaterialTheme.colorScheme.primary,
    selectedLabelColor = MaterialTheme.colorScheme.onPrimary)

private fun trialLine(s: Settings, now: Long): String {
    if (s.licensed) return "License active on this device."
    val days = TrialPolicy.daysLeft(s.trialStartedAt, now)
    return if (days == 0) "Your free trial has ended." else "Free trial: $days day${if (days == 1) "" else "s"} left on this device."
}

@Composable
private fun RunningScreen(a: ActiveSprint, now: Long, momentum: Double, model: MainViewModel, blocklist: () -> Unit) {
    var panel by remember(a.id) { mutableStateOf<EndPanel?>(null) }
    var phrase by remember(a.id) { mutableStateOf("") }
    val status by SprintService.status.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val remaining = a.endsAt - now
    val progress = (remaining.toFloat() / (a.plannedMinutes * 60_000)).coerceIn(0f, 1f)
    val primary = MaterialTheme.colorScheme.primary
    val track = MaterialTheme.colorScheme.outlineVariant
    val until = remember(a.endsAt) { java.text.DateFormat.getTimeInstance(java.text.DateFormat.SHORT).format(java.util.Date(a.endsAt)) }
    Page("${ShieldCopy.label(a.shield)} sprint") {
        Box(Modifier.fillMaxWidth().heightIn(min = 260.dp).drawBehind {
            val radius = minOf(size.width, size.height) / 2 - 12.dp.toPx()
            val center = Offset(size.width / 2, size.height / 2)
            drawCircle(track, radius, center, style = Stroke(6.dp.toPx()))
            drawArc(primary, -90f, 360f * progress, false,
                topLeft = center - Offset(radius, radius), size = androidx.compose.ui.geometry.Size(radius * 2, radius * 2),
                style = Stroke(6.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round))
        }.clearAndSetSemantics { contentDescription = "${SoftNoticeCopy.timeLeft(remaining)}, ends at $until" },
            contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(countdown(remaining), Modifier.padding(horizontal = 24.dp),
                    style = if (LocalDensity.current.fontScale >= 1.5f) MaterialTheme.typography.displayMedium else MaterialTheme.typography.displayLarge)
                Text("until $until", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Text(ShieldCopy.promise(a.shield))
        Text(if (Permissions.canBlock(context)) status else "Blocking is paused: a permission was turned off. Your sprint timer continues.",
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Action(EndFlowState.buttonLabel(a, now)) {
            when (val request = EndFlowState.request(a, momentum, System.currentTimeMillis(), SystemClock.elapsedRealtime())) {
                is EndRequest.Now -> model.end(a.id, null, null)
                is EndRequest.Panel -> { phrase = ""; panel = request.panel }
            }
        }
        EndFlowState.graceNote(a, now)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        Action(if (BlockPolicy.blocklistEditable(a.shield)) "Edit blocklist" else "View blocklist", onClick = blocklist)
    }
    panel?.let { open ->
        // `now` ticks every 250 ms, so reading the monotonic clock here keeps the countdown moving.
        val monotonic = remember(now) { SystemClock.elapsedRealtime() }
        val close = { panel = null; phrase = "" }
        AlertDialog(onDismissRequest = close, title = { Text(open.title) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(open.text)
                    if (open.phraseRequired) OutlinedTextField(phrase, { phrase = it },
                        label = { Text("Type: ${EndSprintPolicy.phrase}") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    val line = open.countdownText(monotonic, phrase)
                    if (line.isNotEmpty()) Text(line, Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }, confirmButton = {
                TextButton({ model.end(a.id, open.requestedAt, phrase); close() },
                    Modifier.heightIn(min = 48.dp).keyboardRing(), enabled = open.canEnd(monotonic, phrase)) { Text("End anyway") }
            }, dismissButton = {
                Button(close, Modifier.heightIn(min = 48.dp).keyboardRing()) { Text("Keep going") }
            })
    }
}

@Composable
private fun SummaryScreen(record: SprintRecord, save: (String) -> Unit) {
    var journal by rememberSaveable(record.id) { mutableStateOf(record.journal) }
    Page(summaryTitle(record.outcome)) {
        Text("${record.plannedMinutes} planned ${if (record.plannedMinutes == 1) "minute" else "minutes"} · ${shieldLabel(record.shield)} shield")
        Text("Momentum ${Momentum.change(record.momentumBefore, record.momentumAfter)}", style = MaterialTheme.typography.titleMedium)
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
        item {
            Panel {
                Text("How momentum works", style = MaterialTheme.typography.titleMedium)
                Momentum.explanation.forEach { Text(it) }
            }
        }
        if (records.isEmpty()) item { Text("Your finished and interrupted sprints will appear here. Start a sprint from Today.") }
        items(records, key = { it.id }) { RecordCard(it) }
    }
}

@Composable
private fun RecordCard(record: SprintRecord) {
    Panel {
        Text("${record.outcome} · ${record.plannedMinutes} min", style = MaterialTheme.typography.titleMedium)
        Text("${time(record.startedAt)} · ${shieldLabel(record.shield)} shield", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Momentum ${Momentum.change(record.momentumBefore, record.momentumAfter)}")
        if (record.journal.isNotBlank()) Text("\u201C${record.journal}\u201D")
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
                    val checked = app.packageName in s.blockedPackages
                    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp)
                        .toggleable(checked, enabled = editable, role = Role.Checkbox) { model.block(app.packageName, it) }
                        .keyboardRing().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        val icon = remember(app.packageName) { app.icon.toBitmap(48, 48).asImageBitmap() }
                        Image(icon, contentDescription = null, modifier = Modifier.size(40.dp))
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) { Text(app.label); Text(app.packageName, style = MaterialTheme.typography.bodySmall) }
                        Checkbox(checked, onCheckedChange = null, enabled = editable,
                            modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp))
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
        Text(if (locked) "Your 7-day free trial on this device has ended. Enter your license key to keep using Basalt." else trialLine(s, now))
        // Google Play Billing seam (#413): a Play purchase option goes here once it exists.
        // Play's payments policy: no link to the website purchase, no price, no "buy elsewhere".
        Text("Already bought Basalt? Enter your license key or purchase email.")
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
        Text("Basalt reads foreground-app package names only while a sprint runs. Your blocklist, sprint history and one-line journal stay in app storage. No analytics, ads or accounts. The only app network request is the license check described on the License screen.")
        Text("Android Auto Backup can back up your local trial, settings and history according to your phone's backup settings. Restoring on a different device requires another license check. Clearing app data may restart the trial and removes local history.")
        Text("Blocking is best effort. Android or your phone's battery saver can stop the service. Reopen Basalt to resume a saved sprint. Permissions can be changed at any time in Android Settings.")
        Action("Review permissions", onClick = permissions)
        Action("System battery settings") { runCatching { context.startActivity(android.content.Intent(android.provider.Settings.ACTION_BATTERY_SAVER_SETTINGS)) } }
        Action("Open-source notices") { notices = !notices }
        if (notices) Text(remember { context.assets.open("Inter-OFL.txt").bufferedReader().use { it.readText() } }, style = MaterialTheme.typography.bodySmall)
    }
}
