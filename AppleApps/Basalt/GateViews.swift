import SwiftUI
import BasaltCore

struct TermsView: View {
  let model: AppModel
  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      Text("BEFORE YOU START").font(.caption).foregroundStyle(.secondary)
      Text("Basalt closes programs").font(.title)
      Text(LegalTerms.dataLossWarning).accessibilityIdentifier("TermsDataLossText")
      Text(LegalTerms.agreementLine).accessibilityIdentifier("TermsAgreementText")
      HStack {
        Link("Read the terms", destination: URL(string: LegalTerms.termsURL(model.settings))!).accessibilityIdentifier("OpenTermsButton")
        Link("Read the privacy policy", destination: URL(string: LegalTerms.privacyURL(model.settings))!).accessibilityIdentifier("OpenPrivacyButton")
      }
      Text("Terms version \(LegalTerms.version)").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("TermsVersionText")
      Button("I understand and agree") { Task { await model.acceptTerms() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("AcceptTermsButton")
      Text("If you don't agree, close Basalt and uninstall it; if you have bought it, ask for a refund.").font(.caption).foregroundStyle(.secondary)
    }.padding(30).frame(width: 520).interactiveDismissDisabled()
  }
}

struct FirstRunView: View {
  let model: AppModel
  @Binding var step: Int
  @State private var query = ""
  @State private var selected: Set<String> = []
  @State private var initialized = false
  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      HStack {
        Text("Step \(step) of 3").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("FirstRunStepText")
        Spacer()
        Button("Skip setup") { Task { await model.completeOnboarding() } }.accessibilityIdentifier("FirstRunSkipButton")
      }
      Group {
        switch step {
        case 1: apps
        case 2: shields
        default: firstSprint
        }
      }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
      HStack {
        if step > 1 { Button("Back") { step -= 1 }.accessibilityIdentifier("FirstRunBackButton") }
        Spacer()
        if step < 3 { Button("Next") { step += 1 }.buttonStyle(.borderedProminent).accessibilityIdentifier("FirstRunNextButton") }
        else {
          Button("Finish without starting") { finish(start: false) }.accessibilityIdentifier("FirstRunFinishButton")
          Button("Start my first sprint") { finish(start: true) }.buttonStyle(.borderedProminent).accessibilityIdentifier("FirstRunStartButton")
        }
      }
    }.padding(28).frame(width: 590, height: 520).interactiveDismissDisabled()
      .onAppear {
        if model.pickerEntries.isEmpty { model.refreshAppPicker() }
        if !initialized { selected = Set(model.pickerEntries.filter { FirstRunPolicy.preTicked(isSuggested: $0.isAutomaticSuggestion, installedPath: $0.url?.path, group: $0.group) }.map(\.id)); initialized = true }
      }
  }
  private var apps: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("What pulls you away?").font(.title)
      Text("Tick the apps Basalt should block during a sprint. The ones on this Mac are ticked for you to confirm.").foregroundStyle(.secondary)
      TextField("Search your apps", text: $query).textFieldStyle(.roundedBorder).accessibilityIdentifier("FirstRunSearchInput")
      ScrollView {
        LazyVStack(alignment: .leading, spacing: 12) {
          ForEach(model.pickerEntries.filter { query.isEmpty || $0.name.localizedCaseInsensitiveContains(query) }) { entry in
            Toggle(isOn: Binding(get: { selected.contains(entry.id) }, set: { yes in if yes { selected.insert(entry.id) } else { selected.remove(entry.id) } })) {
              HStack { AppIcon(path: entry.url?.path); Text(entry.name); if entry.isAutomaticSuggestion { Text("Suggested").font(.caption).foregroundStyle(.secondary) } }
            }.accessibilityIdentifier("FirstRunApp_\(entry.id)")
          }
        }
      }.accessibilityIdentifier("FirstRunAppList")
    }
  }
  private var shields: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("How strict should the shield be?").font(.title)
      Text("You can change this before any sprint.").foregroundStyle(.secondary)
      ForEach(ShieldLevel.allCases, id: \.self) { shield in
        Button { Task { await model.selectShield(shield) } } label: {
          HStack(alignment: .top, spacing: 12) {
            Image(systemName: shield.symbol).font(.title2).foregroundStyle(Color("Primary"))
            VStack(alignment: .leading, spacing: 5) {
              Text(ShieldCopy.name(shield) + (shield == .firm ? " · recommended" : "")).font(.headline)
              Text(ShieldCopy.promise(shield)); Text(ShieldCopy.bestFor(shield)).font(.caption).foregroundStyle(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading)
            if model.settings.defaultShield == shield { Image(systemName: "checkmark.circle.fill").foregroundStyle(Color("Primary")) }
          }.padding(8)
        }.buttonStyle(.bordered).accessibilityIdentifier("FirstRunShield_\(ShieldCopy.name(shield))")
      }
    }
  }
  private var firstSprint: some View {
    VStack(alignment: .leading, spacing: 20) {
      Text("Your first sprint").font(.title)
      Text("Pick a length. The shield runs until the time is up.").foregroundStyle(.secondary)
      HStack {
        ForEach(FirstRunPolicy.sprintLengths, id: \.self) { minutes in
          Button("\(minutes) min") { Task { await model.setSprintMinutes(minutes) } }.accessibilityIdentifier("FirstRunLength_\(minutes)")
            .accessibilityAddTraits(model.settings.defaultSprintMinutes == minutes ? .isSelected : [])
        }
      }
      Toggle("Open Basalt at login", isOn: Binding(get: { model.settings.openAtLogin }, set: { value in Task { await model.setOpenAtLogin(value) } })).accessibilityIdentifier("FirstRunStartWithWindows")
      Text("Opens quietly in the menu bar when you sign in, so a sprint survives a restart.").font(.caption).foregroundStyle(.secondary)
      if !model.settings.isPro { Text("\(model.trialDaysLeft) days left on your free trial.").font(.caption).accessibilityIdentifier("FirstRunTrialText") }
    }
  }
  private func finish(start: Bool) {
    Task {
      // Saving the choices is the last step: adding apps earlier would hide the wizard.
      for entry in model.pickerEntries where selected.contains(entry.id) { _ = await model.addBlockedApp(entry.blockedApp) }
      await model.completeOnboarding()
      if start { _ = await model.start() }
    }
  }
}

struct TrialEndedView: View {
  let model: AppModel
  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      Text("FREE TRIAL ENDED").font(.caption).foregroundStyle(.secondary)
      Text("Keep Basalt for $4.99").font(.title)
      Text("Your 7-day free trial has ended. Buy Basalt once for $4.99 to keep using it — no subscription. Already bought it? Enter your license key below.").accessibilityIdentifier("TrialEndedText")
      Link("Buy Basalt — $4.99", destination: model.buyURL).accessibilityIdentifier("LockBuyButton")
      Divider()
      Text("ALREADY BOUGHT IT?").font(.caption).foregroundStyle(.secondary)
      LicenseSettings(model: model, trialGate: true)
    }.padding(28).frame(width: 500).interactiveDismissDisabled()
  }
}

struct ActivationView: View {
  @Bindable var model: AppModel
  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      Text("FROM YOUR PURCHASE").font(.caption).foregroundStyle(.secondary)
      Text("Activate this license?").font(.title2)
      Text(model.activationKey).monospaced().textSelection(.enabled).accessibilityIdentifier("ActivationLinkKey")
      Text("Basalt will check this key with the license server and unlock this device.")
      if model.licenseBusy { ProgressView("Checking…") }
      Text(model.licenseMessage).foregroundStyle(.secondary)
      HStack {
        Button("Activate") { Task { await model.activateLicense(key: model.activationKey, email: ""); if model.settings.isPro { model.licensePromptVisible = false } } }.buttonStyle(.borderedProminent).disabled(model.licenseBusy).accessibilityIdentifier("ConfirmActivationButton")
        Button("Cancel") { model.licensePromptVisible = false }.keyboardShortcut(.cancelAction).accessibilityIdentifier("DismissActivationButton")
      }
    }.padding(28).frame(width: 480)
  }
}
