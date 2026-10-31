import AppKit
import Observation
import ServiceManagement
import BasaltCore

@MainActor @Observable
final class AppModel {
  private(set) var settings = AppSettings()
  private(set) var isReady = false
  private(set) var isTransitioning = false
  private(set) var now = Date()
  var intention = ""
  var journalText = ""
  var endConfirmation = EndConfirmation()
  private(set) var summary: FocusSession?
  private(set) var journalVisible = false
  private(set) var breakOffered = false
  private(set) var pendingSchedule: ScheduleAction?
  private(set) var scheduleClosingText = ""
  private(set) var pendingStart: StartRequest?
  private(set) var runningAppsToClose: [String] = []
  private(set) var pickerEntries: [AppPickerEntry] = []
  private(set) var devices: [DeviceInfo] = []
  private(set) var licenseBusy = false
  private(set) var licenseMessage = ""
  private(set) var loginStatus: SMAppService.Status = .notRegistered
  var activationKey = ""
  var licensePromptVisible = false
  var errorMessage: String?
  var toast = ""
  var notificationDestination = MacNotifications.Destination.app
  var openWindowRequested: (() -> Void)?
  private(set) var cycle = CycleState()
  let options: LaunchOptions
  @ObservationIgnored private let store: SettingsStore
  @ObservationIgnored private let trialRecord: TrialRecord
  @ObservationIgnored private let licenseClient: LicenseClient
  @ObservationIgnored private let notifications: MacNotifications
  @ObservationIgnored private let login = LoginItemService()
  @ObservationIgnored private let hotkey = GlobalHotkey()
  @ObservationIgnored private let blocker: BlockerService
  @ObservationIgnored let log: BlockerLog
  @ObservationIgnored private var clockTask: Task<Void, Never>?
  @ObservationIgnored private var pendingSave: Task<Bool, Never>?
  @ObservationIgnored private var lastHeartbeat = Date()
  @ObservationIgnored private var lastScheduleTick = Date()
  @ObservationIgnored private var headsUpShown: Set<String> = []
  @ObservationIgnored private var scheduleNamedApps: Set<String> = []
  @ObservationIgnored private var scheduleNamesSeen = false
  @ObservationIgnored private var endingSoonNotified = false
  @ObservationIgnored private var blocks = 0
  @ObservationIgnored private var appsClosed = 0
  @ObservationIgnored private var nudges = 0
  @ObservationIgnored private var turnedBack = 0
  @ObservationIgnored private var templateBreak: Int?
  @ObservationIgnored private var quitAfterEnd = false
  @ObservationIgnored private var generation = UUID()

  struct StartRequest {
    var minutes: Int
    var shield: ShieldLevel
    var announcedName: String?
  }
  init(options: LaunchOptions = LaunchOptions(), licenseClient: LicenseClient? = nil) {
    self.options = options
    store = SettingsStore(url: options.dataDirectory.appendingPathComponent("settings.json"))
    trialRecord = TrialRecord(url: options.dataDirectory.appendingPathComponent("trial-start"))
    let identity = MacDeviceIdentity.values()
    self.licenseClient = licenseClient ?? LicenseClient(deviceId: identity.id, deviceName: identity.name)
    notifications = MacNotifications()
    let log = BlockerLog(directory: options.dataDirectory)
    self.log = log
    blocker = BlockerService(log: log, testTimings: options.testTimings)
    blocker.onEvent = { [weak self] event, index in self?.recordBlock(event, index: index) }
    blocker.onWarning = { [weak self] title, message in
      guard let self else { return }
      self.notifications.send(.appClosing, title: title, body: message, settings: self.settings)
      self.firmWarning = message
    }
    notifications.onOpen = { [weak self] destination in
      self?.notificationDestination = destination
      if destination == .license { self?.licensePromptVisible = true }
      self?.openWindowRequested?()
    }
    hotkey.onPress = { [weak self] in Task { await self?.start() } }
  }
  private(set) var firmWarning: String?
  func dismissFirmWarning() { firmWarning = nil }
  var activeSprint: RunningSprint? { settings.activeSprint }
  var isRunning: Bool { activeSprint != nil }
  var isOnBreak: Bool { settings.activeBreak != nil }
  var listIsLocked: Bool { settings.listIsLocked }
  var canEditBlocklist: Bool { isReady && !isTransitioning && !listIsLocked && !trialLocked }
  var remaining: TimeInterval {
    max(0, (activeSprint?.endsUtc ?? settings.activeBreak?.endsUtc ?? now).timeIntervalSince(now))
  }
  var remainingText: String {
    let n = Int(ceil(remaining))
    return n >= 3600 ? String(format: "%d:%02d:%02d", n / 3600, n / 60 % 60, n % 60) : String(format: "%02d:%02d", n / 60, n % 60)
  }
  var firstRunVisible: Bool {
    FirstRunPolicy.shouldShow(settings, hasAccess: hasAccess, sprintRunning: isRunning)
  }
  var termsRequired: Bool { !LegalTerms.accepted(settings) }
  var hasAccess: Bool { TrialPolicy.hasAccess(settings, now: now) }
  var trialDaysLeft: Int { TrialPolicy.daysLeft(start: settings.trialStartedUtc, now: now) }
  var trialLocked: Bool {
    TrialPolicy.shouldLock(settings, now: now, sprintRunning: isRunning, summaryVisible: summary != nil, journalVisible: journalVisible)
  }
  var goalProgress: String { DailyGoal.progressText(settings, day: LocalDay(now)) }
  var canStart: Bool { isReady && !isTransitioning && !isRunning && hasAccess && !termsRequired && !firstRunVisible }
  var canEndAnyway: Bool { endConfirmation.canEndAnyway(now: now) }
  var endButtonLabel: String {
    guard let sprint = activeSprint else { return "End sprint" }
    return EndSprintPolicy(testTimings: options.testTimings).buttonLabel(shield: sprint.shield, elapsed: now.timeIntervalSince(sprint.startedUtc))
  }
  var offeredBreakMinutes: Int {
    templateBreak ?? CycleState.breakMinutes(completedInARow: settings.completedSprintsInARow,
      short: settings.shortBreakMinutes, long: settings.longBreakMinutes)
  }

  func load() async {
    guard !isReady else { return }
    do {
      settings = try await store.load()
      settings.ensureProfiles(); settings.ensureTemplates()
      try trialRecord.ensureStarted(&settings, now: now)
      if options.skipOnboarding { LegalTerms.accept(&settings, now: now); settings.firstRunCompleted = true }
      let recovery = SprintLifecycle.recover(&settings, now: now)
      if let recovery { log.write("recovery=\(recovery); shield=\(settings.activeSprint.map { ShieldCopy.name($0.shield) } ?? "none")") }
      if let sprint = settings.activeSprint {
        cycle = CycleState(phase: .sprint, sprintsPlanned: sprint.cycleSprintsPlanned, sprintsDone: sprint.cycleSprintsDone)
        templateBreak = sprint.templateBreakMinutes
        intention = sprint.intention
        settings.defaultSprintMinutes = sprint.plannedMinutes
        settings.defaultShield = sprint.shield
      } else if let rest = settings.activeBreak {
        if rest.decide(now) == .resume { cycle = rest.cycle; templateBreak = rest.templateBreakMinutes; log.write("break resumed; enforcement stopped") }
        else { settings.activeBreak = nil }
      }
      DailyGoal.settle(&settings, today: LocalDay(now))
      Milestones.seed(&settings, now: now)
      lastHeartbeat = now
      lastScheduleTick = SchedulePlanner.seedLastTick(settings.scheduleLastCheckUtc, now: now)
      guard await persist() else { return }
      isReady = true
      loginStatus = login.status
      if settings.globalHotkeyEnabled && !hotkey.register() {
        settings.globalHotkeyEnabled = false; _ = await persist()
        toast = "The global shortcut couldn't be registered. It has been turned off."
      }
      blocker.startObserving(); blocker.update(settings)
      if let sprint = options.sprint, settings.activeSprint == nil {
        for id in sprint.bundles {
          var app = BlockedApp(); app.name = id; app.bundleIdentifier = id
          _ = await addBlockedApp(app)
        }
        _ = await start(minutes: sprint.minutes, shield: sprint.shield, confirmed: true)
      }
      clockTask = Task { [weak self] in
        while !Task.isCancelled {
          await self?.tick()
          do { try await Task.sleep(for: .seconds(1)) } catch { break }
        }
      }
      // Never contact production licensing from isolated automation data.
      if !options.isIsolated && (!settings.licenseKey.isEmpty || !settings.licenseEmail.isEmpty) {
        Task { [weak self] in await self?.refreshLicense() }
      }
    } catch { errorMessage = "Couldn't load Basalt's data: \(error.localizedDescription)" }
  }

  @discardableResult private func persist() async -> Bool {
    let snapshot = settings
    let previous = pendingSave
    let store = store
    let task = Task { @MainActor [weak self] in
      _ = await previous?.value
      do { try await store.save(snapshot); return true }
      catch {
        self?.errorMessage = "Couldn't save Basalt's data. Blocking has stopped: \(error.localizedDescription)"
        self?.isReady = false
        self?.blocker.shutdown()
        return false
      }
    }
    pendingSave = task
    return await task.value
  }
  private func changed() async {
    // A failed/newer-schema load must not be replaced by the default in-memory value.
    guard isReady else { return }
    if await persist() { blocker.update(settings) }
  }
  func acceptTerms() async { guard isReady else { return }; LegalTerms.accept(&settings, now: Date()); await changed() }
  func completeOnboarding() async {
    guard isReady else { return }
    settings.firstRunCompleted = true; await changed()
    if settings.notificationsEnabled { _ = await notifications.requestAuthorization() }
  }

  @discardableResult func start(minutes: Int? = nil, shield: ShieldLevel? = nil,
    confirmed: Bool = false, announcedName: String? = nil) async -> SprintStartResult {
    guard isReady, !isTransitioning else { return .alreadyRunning }
    let minutes = minutes ?? settings.defaultSprintMinutes
    let shield = shield ?? settings.defaultShield
    let running = (shield != .soft || settings.hardKillModeEnabled)
      ? blocker.runningBlockedApps(targets: settings.blockedApps) : []
    let result = SprintLifecycle.start(&settings, now: Date(), minutes: minutes, shield: shield,
      intention: intention, firstRunVisible: firstRunVisible, runningBlockedApps: !running.isEmpty,
      confirmed: confirmed, cycle: cycle, templateBreak: templateBreak)
    if result == .confirmRunningApps {
      pendingStart = StartRequest(minutes: minutes, shield: shield, announcedName: announcedName)
      runningAppsToClose = running.compactMap(\.localizedName).sorted()
      openWindowRequested?()
      return result
    }
    guard result == .started else { return result }
    isTransitioning = true
    defer { isTransitioning = false }
    settings.defaultSprintMinutes = minutes; settings.defaultShield = shield
    pendingStart = nil; runningAppsToClose = []; pendingSchedule = nil
    summary = nil; journalVisible = false; breakOffered = false
    endConfirmation.keepGoing()
    cycle = cycle.onSprintStarted(settings.cycleSprints)
    blocks = 0; appsClosed = 0; nudges = 0; turnedBack = 0; endingSoonNotified = false
    lastHeartbeat = Date(); now = Date()
    // This await is the F3 boundary. No enforcement is started until the active record is durable.
    guard await persist() else { settings.activeSprint = nil; return .persistenceFailed }
    log.write("sprint started; shield=\(ShieldCopy.name(shield)); minutes=\(minutes)")
    blocker.update(settings)
    let announced = announcedName.map {
      notifications.send(.scheduledSprint, title: "\($0) started", body: "\(minutes) minutes at \(ShieldCopy.name(shield)).", settings: settings)
    } ?? false
    if !announced { notifications.send(.sprintStarted, title: "Sprint started", body: "\(ShieldCopy.name(shield)) shield on for \(minutes) minutes.", settings: settings) }
    return .started
  }
  func confirmStart() async {
    guard let pendingStart else { return }
    _ = await start(minutes: pendingStart.minutes, shield: pendingStart.shield, confirmed: true, announcedName: pendingStart.announcedName)
  }
  func dismissStart() { pendingStart = nil; runningAppsToClose = [] }
  func requestEnd() async {
    guard let sprint = activeSprint, !isTransitioning else { return }
    now = Date()
    let flow = endConfirmation.request(shield: sprint.shield, elapsed: now.timeIntervalSince(sprint.startedUtc), now: now,
      policy: EndSprintPolicy(testTimings: options.testTimings))
    switch flow {
    case .cancel: await cancel()
    case .immediate: await finish(completed: false)
    case .confirm, .sealed: openWindowRequested?()
    }
  }
  func endAnyway() async {
    guard isRunning, !isTransitioning, endConfirmation.endAnyway(now: Date()) else { return }
    await finish(completed: false)
  }
  func keepGoing() { endConfirmation.keepGoing(); quitAfterEnd = false }
  func cancel() async {
    guard let sprint = activeSprint, !isTransitioning,
      EndSprintPolicy(testTimings: options.testTimings).flow(shield: sprint.shield, elapsed: Date().timeIntervalSince(sprint.startedUtc)) == .cancel else { return }
    isTransitioning = true
    SprintLifecycle.cancel(&settings); cycle = CycleState(); templateBreak = nil
    endConfirmation.keepGoing(); blocker.update(settings)
    log.write("sprint cancelled; enforcement stopped")
    _ = await persist(); isTransitioning = false
    finishQuitIfNeeded()
  }
  private func finish(completed: Bool, interrupted: Bool = false) async {
    guard let sprint = activeSprint, !isTransitioning else { return }
    isTransitioning = true
    now = Date()
    settings.activeSprint?.noteStillWatching(now)
    let session = SprintLifecycle.finish(&settings, now: now, completed: completed, interrupted: interrupted,
      appsClosed: appsClosed, nudges: nudges, blocks: blocks, turnedBack: turnedBack)
    blocker.update(settings)
    endConfirmation.keepGoing(); firmWarning = nil
    cycle = completed ? cycle.onSprintCompleted() : cycle.onSprintAbandoned()
    if cycle.cycleFinished { toast = "Cycle done — \(cycle.sprintsPlanned) sprints."; cycle = cycle.onCycleFinished() }
    if !interrupted { summary = session; journalVisible = true; journalText = "" }
    intention = ""
    breakOffered = completed
    _ = await persist(); isTransitioning = false
    log.write("sprint ended; completed=\(completed); interrupted=\(interrupted); enforcement stopped")
    if completed {
      notifications.send(.sprintComplete, title: "Sprint complete", body: "\(sprint.plannedMinutes) minutes done. Momentum \(String(format: "%.1f", settings.momentumScore)).", settings: settings, destination: .journal)
      if cycle.startsNextSprint { await startBreak() }
    } else if interrupted {
      notifications.send(.sprintInterrupted, title: "Sprint interrupted", body: "The Mac was asleep or Basalt was closed for most of it, so it doesn't count as finished.", settings: settings)
    }
    finishQuitIfNeeded()
  }
  func startBreak() async {
    guard !isRunning, !isOnBreak, breakOffered, !isTransitioning else { return }
    var rest = RunningBreak(); rest.startedUtc = Date(); rest.minutes = offeredBreakMinutes
    rest.endsUtc = rest.startedUtc.addingTimeInterval(CycleState.breakLength(rest.minutes, testTimings: options.testTimings))
    rest.sprintsPlanned = cycle.sprintsPlanned; rest.sprintsDone = cycle.sprintsDone; rest.templateBreakMinutes = templateBreak
    settings.activeBreak = rest; cycle = cycle.onBreakStarted(); breakOffered = false
    await changed(); log.write("break started; enforcement stopped")
  }
  func skipBreak() async {
    guard !isRunning, !isTransitioning else { return }
    settings.activeBreak = nil; breakOffered = false; cycle = cycle.onBreakEnded()
    log.write("break ended; enforcement stopped")
    await changed()
    if cycle.startsNextSprint { _ = await start() } else { cycle = cycle.onCycleFinished(); templateBreak = nil }
  }
  func saveJournal() async {
    SprintLifecycle.saveJournal(&settings, text: journalText)
    journalVisible = false; toast = "Logged."; await changed()
  }
  func dismissSummary() { summary = nil }
  func dismissJournal() { journalVisible = false }
  func requestQuit() async {
    if isRunning { quitAfterEnd = true; await requestEnd() } else { await shutdown(); NSApp.terminate(nil) }
  }
  private func finishQuitIfNeeded() {
    if quitAfterEnd { Task { await shutdown(); NSApp.terminate(nil) } }
  }
  func shutdown() async {
    clockTask?.cancel(); clockTask = nil
    blocker.shutdown(); hotkey.unregister()
    if isRunning { settings.activeSprint?.noteStillWatching(Date()); _ = await persist() }
    _ = await pendingSave?.value
  }

  func tick(at date: Date = Date()) async {
    guard isReady, !isTransitioning else { return }
    now = date
    if let sprint = activeSprint {
      if now >= sprint.endsUtc {
        // Account for only the capped stretch actually observed after a sleep.
        settings.activeSprint?.noteStillWatching(now)
        let watched = settings.activeSprint?.watchedSoFar ?? 0
        await finish(completed: watched >= Double(sprint.plannedMinutes) * RunningSprint.completedIfWatchedFraction,
          interrupted: watched < Double(sprint.plannedMinutes) * RunningSprint.completedIfWatchedFraction)
      } else {
        if now.timeIntervalSince(lastHeartbeat) >= RunningSprint.heartbeatInterval {
          settings.activeSprint?.noteStillWatching(now); lastHeartbeat = now; _ = await persist()
        }
        if !endingSoonNotified, remaining <= NotificationPolicy.endingSoon,
          !NotificationPolicy.tooShortForEndingSoon(sprint.plannedMinutes) {
          endingSoonNotified = true
          notifications.send(.fiveMinutesLeft, title: "5 minutes left", body: BreakCopy.endingSoon(inSleepWindow: false, sleepEndsText: ""), settings: settings)
        }
      }
    } else if let rest = settings.activeBreak, now >= rest.endsUtc {
      notifications.send(.breakOver, title: "Break over", body: cycle.startsNextSprint ? "Back to it — \(cycle.cycleLabel.lowercased())." : "Back to it when you're ready.", settings: settings)
      await skipBreak()
    }
    let planner = SchedulePlanner(testTimings: options.testTimings)
    if now.timeIntervalSince(lastScheduleTick) >= planner.tickInterval {
      let actions = planner.decide(settings.schedules, lastTick: lastScheduleTick, now: now, zone: .current, headsUpShown: headsUpShown)
      lastScheduleTick = now; settings.scheduleLastCheckUtc = now
      for action in actions { await handleSchedule(action) }
      if let pendingSchedule, planner.cardHasExpired(start: pendingSchedule.startUtc, now: now) { self.pendingSchedule = nil }
      _ = await persist()
    }
    if DailyGoal.settle(&settings, today: LocalDay(now)) { _ = await persist() }
    if TrialPolicy.shouldWarnTomorrow(settings, now: now, today: LocalDay(now), sprintRunning: isRunning) {
      if notifications.send(.trialEnding, title: "Your free trial ends tomorrow", body: "Buy Basalt once for $4.99 to keep it — no subscription.", settings: settings, destination: .license) {
        settings.trialEndingNotifiedLocal = LocalDay(now); _ = await persist()
      }
    }
  }
  private func recordBlock(_ event: BlockerService.Event, index: Int) {
    guard isRunning else { return }
    if event == .turnedBack { turnedBack += 1; return }
    blocks += 1
    if event == .closing { appsClosed += 1 } else { nudges += 1 }
    settings.recordBlock(day: LocalDay(Date()))
    if let p = settings.profiles.firstIndex(where: { $0.id == settings.activeProfileId }), settings.profiles[p].apps.indices.contains(index) {
      settings.profiles[p].apps[index].blockCount += 1
    }
    Task { _ = await persist() }
  }

  func selectShield(_ shield: ShieldLevel) async {
    guard !isRunning else { return }; settings.defaultShield = shield; await changed()
  }
  func setSprintMinutes(_ minutes: Int) async {
    guard !isRunning, SprintLength.isValid(minutes) else { return }
    settings.defaultSprintMinutes = minutes
    if !SprintLength.presets.contains(minutes) { settings.lastCustomSprintMinutes = minutes }
    await changed()
  }
  @discardableResult func applyTemplate(_ id: String) async -> Bool {
    guard !isRunning, let template = settings.templates.first(where: { $0.id == id }) else { return false }
    settings.defaultSprintMinutes = template.sprintMinutes; settings.defaultShield = template.shield
    settings.cycleSprints = template.cycleSprints
    if settings.findProfile(template.profileId) != nil { settings.activeProfileId = template.profileId }
    templateBreak = template.breakMinutes; cycle = CycleState()
    await changed(); return true
  }
  func saveTemplate(_ value: StudyTemplate) async {
    var value = value; value.normalize()
    value.name = settings.uniqueTemplateName(value.name, except: value.id)
    if let i = settings.templates.firstIndex(where: { $0.id == value.id }) { settings.templates[i] = value }
    else { settings.templates.append(value) }
    await changed()
  }
  func deleteTemplate(_ id: String) async { settings.deleteTemplate(id); await changed() }
  func restoreTemplates() async { settings.restoreBuiltInTemplates(); await changed() }
  @discardableResult func addProfile(name: String, copying id: String? = nil) async -> String? {
    guard canEditBlocklist else { return nil }
    let profile = settings.addProfile(name: name, copying: id.flatMap { settings.findProfile($0) } ?? settings.activeProfile)
    if let profile { settings.activeProfileId = profile.id; await changed() }; return profile?.id
  }
  func renameProfile(_ id: String, name: String) async { guard canEditBlocklist else { return }; if settings.renameProfile(id, name: name) { await changed() } }
  func deleteProfile(_ id: String) async { guard canEditBlocklist else { return }; if settings.deleteProfile(id) { await changed() } }
  func selectProfile(_ id: String) async { guard canEditBlocklist else { return }; if settings.setActiveProfile(id) { await changed() } }
  @discardableResult func addBlockedApp(_ app: BlockedApp) async -> Bool {
    guard canEditBlocklist, let i = settings.profiles.firstIndex(where: { $0.id == settings.activeProfileId }),
      !settings.blockedApps.contains(where: { (!$0.bundleIdentifier.isEmpty && $0.bundleIdentifier.lowercased() == app.bundleIdentifier.lowercased()) || (!app.processName.isEmpty && $0.processName.lowercased() == app.processName.lowercased()) }) else { return false }
    settings.profiles[i].apps.append(app); await changed(); return true
  }
  func removeBlockedApp(at index: Int) async {
    guard canEditBlocklist, let i = settings.profiles.firstIndex(where: { $0.id == settings.activeProfileId }), settings.profiles[i].apps.indices.contains(index) else { return }
    settings.profiles[i].apps.remove(at: index); await changed()
  }
  func toggleBlockedApp(at index: Int, enabled: Bool) async {
    guard canEditBlocklist, let i = settings.profiles.firstIndex(where: { $0.id == settings.activeProfileId }), settings.profiles[i].apps.indices.contains(index) else { return }
    settings.profiles[i].apps[index].isEnabled = enabled; await changed()
  }
  func refreshAppPicker() { pickerEntries = AppCatalog.discover() }
  func saveSchedule(_ value: SprintSchedule) async {
    guard settings.templates.contains(where: { $0.id == value.templateId }) else { return }
    var value = value; value.normalize()
    if let i = settings.schedules.firstIndex(where: { $0.id == value.id }) { settings.schedules[i] = value }
    else { settings.schedules.append(value) }
    await changed()
  }
  func deleteSchedule(_ id: String) async {
    settings.schedules.removeAll { $0.id == id }; if pendingSchedule?.schedule.id == id { pendingSchedule = nil }; await changed()
  }
  func skipScheduledSprint() async {
    guard let action = pendingSchedule else { return }
    if let i = settings.schedules.firstIndex(where: { $0.id == action.schedule.id }) { settings.schedules[i].skip(LocalDay(action.startUtc)) }
    pendingSchedule = nil; await changed()
  }
  func startScheduledSprint() async {
    guard let action = pendingSchedule, let template = settings.templates.first(where: { $0.id == action.schedule.templateId }) else { return }
    let confirmed = scheduleNamesCoverCurrentApps(template)
    guard await applyTemplate(template.id) else { return }
    _ = await start(confirmed: confirmed, announcedName: action.schedule.askFirst ? nil : template.name)
  }
  func markScheduleHeadsUpSeen() { if pendingSchedule != nil { scheduleNamesSeen = true } }
  private func scheduleApps(_ template: StudyTemplate) -> [NSRunningApplication] {
    guard template.shield != .soft || settings.hardKillModeEnabled else { return [] }
    return blocker.runningBlockedApps(targets: settings.profile(for: template).apps)
  }
  private func appKey(_ app: NSRunningApplication) -> String {
    (app.bundleIdentifier ?? app.executableURL?.lastPathComponent ?? "\(app.processIdentifier)").lowercased()
  }
  private func scheduleNamesCoverCurrentApps(_ template: StudyTemplate) -> Bool {
    scheduleNamesSeen && Set(scheduleApps(template).map(appKey)).isSubset(of: scheduleNamedApps)
  }
  private func handleSchedule(_ action: ScheduleAction) async {
    if action.kind == .headsUp { headsUpShown.insert(SchedulePlanner.headsUpKey(action.schedule, start: action.startUtc)) }
    guard !isRunning, !isOnBreak, pendingStart == nil, let template = settings.templates.first(where: { $0.id == action.schedule.templateId }), hasAccess, !termsRequired, !firstRunVisible else {
      if action.kind == .start, pendingSchedule?.schedule.id == action.schedule.id { pendingSchedule = nil }
      return
    }
    let matching = pendingSchedule.map { $0.schedule.id == action.schedule.id && $0.startUtc == action.startUtc } ?? false
    if !ScheduleStartPolicy.mustOffer(kind: action.kind, askFirst: action.schedule.askFirst, matchingHeadsUp: matching) {
      let confirmed = matching && scheduleNamesCoverCurrentApps(template)
      if await applyTemplate(template.id) { _ = await start(confirmed: confirmed, announcedName: action.schedule.askFirst ? nil : template.name) }
    } else {
      pendingSchedule = action
      let apps = scheduleApps(template)
      scheduleNamedApps = Set(apps.map(appKey)); scheduleNamesSeen = false
      let names = Set(apps.compactMap(\.localizedName)).sorted().joined(separator: ", ")
      scheduleClosingText = names.isEmpty ? "" : "\(names) will be closed."
      let time = action.startUtc.formatted(date: .omitted, time: .shortened)
      let title = action.kind == .offerMissed ? "You missed \(template.name)" : action.kind == .headsUp ? "\(template.name) starts at \(time)" : "\(template.name) is due now"
      let ask = action.kind == .offerMissed ? "It was due at \(time). Start it now or skip it on Today." : action.kind == .headsUp ? "Start now or skip it on Today." : "Start it now or skip it on Today."
      let body = scheduleClosingText.isEmpty ? ask : "\(scheduleClosingText) \(ask)"
      if notifications.send(.scheduledSprint, title: title, body: body, settings: settings, destination: .today) && !scheduleClosingText.isEmpty { scheduleNamesSeen = true }
    }
  }

  // Typed setters keep persistence and enforcement out of SwiftUI bindings.
  func setTheme(_ value: AppTheme) async { settings.theme = value; await changed() }
  func setHardKill(_ value: Bool) async { guard !listIsLocked else { return }; settings.hardKillModeEnabled = value; await changed() }
  func setSoftNotice(_ value: Bool) async { settings.showSoftOverlayEnabled = value; await changed() }
  func setCycleSprints(_ value: Int) async { guard !isRunning, CycleState.choices.contains(value) else { return }; settings.cycleSprints = value; cycle = CycleState(); await changed() }
  func setBreakMinutes(short: Int, long: Int) async {
    guard CycleState.isValidBreakMinutes(short), CycleState.isValidBreakMinutes(long) else { return }
    settings.shortBreakMinutes = short; settings.longBreakMinutes = long; await changed()
  }
  func setSleepBlock(enabled: Bool, startMinute: Int, endMinute: Int) async {
    guard (0...1439).contains(startMinute), (0...1439).contains(endMinute) else { return }
    settings.isSleepBlockEnabled = enabled; settings.sleepBlockStartMinute = startMinute; settings.sleepBlockEndMinute = endMinute; await changed()
  }
  func setDailyGoal(kind: DailyGoalKind, target: Int) async {
    settings.dailyGoalKind = kind; settings.dailyGoalTarget = DailyGoal.clampTarget(kind, target)
    DailyGoal.noteProgress(&settings, today: LocalDay(now)); await changed()
  }
  func setDayOff(_ day: LocalDay, skipped: Bool) async {
    if skipped { DailyGoal.skip(&settings, day: day) } else { DailyGoal.unskip(&settings, day: day) }; await changed()
  }
  func markMilestoneShown(_ id: String) async {
    if let i = settings.earnedMilestones.firstIndex(where: { $0.id == id }) { settings.earnedMilestones[i].shown = true; await changed() }
  }
  func setNotifications(_ value: Bool, kind: NotificationKind? = nil) async {
    guard isReady else { return }
    if let kind { settings.notificationKinds[kind.rawValue] = value } else { settings.notificationsEnabled = value }
    if value { _ = await notifications.requestAuthorization() }; await changed()
  }
  func setOpenAtLogin(_ enabled: Bool) async {
    guard isReady else { return }
    do { try login.setEnabled(enabled); settings.openAtLogin = enabled; loginStatus = login.status; await changed() }
    catch { errorMessage = "Couldn't change Open at login: \(error.localizedDescription)"; loginStatus = login.status }
  }
  func openLoginApprovalSettings() { login.openApprovalSettings() }
  func setGlobalHotkey(_ enabled: Bool) async {
    guard isReady else { return }
    if enabled { settings.globalHotkeyEnabled = hotkey.register(); if !settings.globalHotkeyEnabled { toast = "The global shortcut couldn't be registered. It has been turned off." } }
    else { hotkey.unregister(); settings.globalHotkeyEnabled = false }
    await changed()
  }
  func handleURL(_ url: URL) {
    guard let key = ActivationLink.key(from: url.absoluteString) else { return }
    activationKey = key; licensePromptVisible = true; openWindowRequested?()
  }
  func setLicenseServer(_ url: String) async {
    guard let parsed = URL(string: url), ["https", "http"].contains(parsed.scheme?.lowercased() ?? ""), parsed.host != nil, parsed.user == nil, parsed.password == nil else { return }
    settings.licenseServerUrl = url; await changed()
  }
  func activateLicense(key: String, email: String) async {
    guard isReady, !licenseBusy else { return }; licenseBusy = true; defer { licenseBusy = false }
    let token = generation
    let result = await licenseClient.validate(key: key, email: email, server: settings.licenseServerUrl) { [weak self] message in
      Task { @MainActor in self?.licenseMessage = message }
    }
    guard token == generation else { return }
    licenseMessage = result.message; result.applyActivation(to: &settings, now: Date()); await changed()
  }
  func refreshLicense() async {
    guard isReady, !licenseBusy else { return }; licenseBusy = true; defer { licenseBusy = false }
    let token = generation
    if let result = await licenseClient.refresh(settings), token == generation {
      result.applyRefresh(to: &settings, now: Date()); licenseMessage = result.message; await changed()
    }
  }
  func deactivateLicense() async {
    guard isReady, !licenseBusy else { return }; licenseBusy = true; defer { licenseBusy = false }
    await licenseClient.deactivate(key: settings.licenseKey, server: settings.licenseServerUrl)
    LicenseClient.clearLocalLicense(&settings); devices = []; await changed()
  }
  func listDevices() async {
    guard isReady, !licenseBusy else { return }; licenseBusy = true; defer { licenseBusy = false }
    let token = generation
    let result = await licenseClient.listDevices(key: settings.licenseKey, server: settings.licenseServerUrl)
    guard token == generation else { return }
    devices = result.devices; licenseMessage = result.message ?? ""
    if result.ok { settings.deviceCount = result.deviceCount; settings.deviceLimit = result.deviceLimit; await changed() }
  }
  func releaseDevice(_ token: String) async {
    guard isReady, !licenseBusy else { return }; licenseBusy = true
    let released = await licenseClient.releaseDevice(key: settings.licenseKey, token: token, server: settings.licenseServerUrl)
    if released, devices.contains(where: { $0.deviceToken == token && $0.isCurrent }) { LicenseClient.clearLocalLicense(&settings); await changed() }
    licenseBusy = false
    if released { await listDevices() } else { licenseMessage = "Couldn't release this device." }
  }
  func exportAllData(to url: URL) throws { try DataPrivacy.export(settings, now: Date()).write(to: url, options: .atomic) }
  func exportJournal(to url: URL, from: LocalDay, through: LocalDay, format: ExportFormat) throws {
    try JournalExport.write(to: url, sessions: settings.sessions, from: from, to: through, format: format)
  }
  func deleteEverything() async {
    guard isReady, !isRunning, !isOnBreak, !licenseBusy, !isTransitioning else { return }
    isTransitioning = true
    defer { isTransitioning = false }
    if !settings.licenseKey.isEmpty { await licenseClient.deactivate(key: settings.licenseKey, server: settings.licenseServerUrl) }
    generation = UUID(); _ = await pendingSave?.value
    do {
      try await store.reset()
      settings = AppSettings(); settings.ensureProfiles(); settings.ensureTemplates()
      try trialRecord.ensureStarted(&settings, now: Date())
      summary = nil; journalVisible = false; pendingSchedule = nil; pendingStart = nil
      intention = ""; journalText = ""; endConfirmation.keepGoing(); breakOffered = false
      activationKey = ""; licenseMessage = ""; licensePromptVisible = false
      headsUpShown.removeAll(); runningAppsToClose = []; firmWarning = nil
      devices = []; cycle = CycleState(); templateBreak = nil
      hotkey.unregister(); blocker.update(settings)
      if login.status == .enabled || login.status == .requiresApproval {
        do { try login.setEnabled(false) } catch { errorMessage = "Open at login couldn't be removed: \(error.localizedDescription)" }
      }
      loginStatus = login.status
      try? FileManager.default.removeItem(at: log.url)
      let fm = FileManager.default
      for file in (try? fm.contentsOfDirectory(at: options.dataDirectory, includingPropertiesForKeys: nil)) ?? [] {
        if file.lastPathComponent.hasPrefix("settings.corrupt-") && file.pathExtension == "json" { try fm.removeItem(at: file) }
      }
      await changed()
    } catch { errorMessage = "Couldn't delete all data: \(error.localizedDescription)" }
  }
}
