# Android app — native Kotlin and Compose

Read [the root CLAUDE.md](../CLAUDE.md) first. Basalt is the product name;
FlowShield remains the repository and license protocol name. Customer copy
uses American **license**. The Android app makes no purchase links or claims
about features that are not implemented.

## Build and test

Use JDK 21 and an Android SDK containing platform 36 and build-tools 36.
On this Windows machine set `JAVA_HOME` to
`C:\Program Files\Microsoft\jdk-21.0.2.13-hotspot` (the default JRE is not suitable).
Set `ANDROID_HOME` or put `sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk`
in an untracked `local.properties`. From `AndroidApp/`:

```bash
./gradlew :core:test :app:testDebugUnitTest :app:lintDebug :app:assembleDebug --stacktrace
```

Windows uses `gradlew.bat`. The APK is at
`app/build/outputs/apk/debug/app-debug.apk`; never commit APKs, signing keys,
`local.properties`, captures, or build output. No release signing is configured.
There is no app-owned native code or NDK build. Compose Graphics Path and
DataStore bring prebuilt AndroidX native libraries; every packaged ELF load
segment and APK library offset was checked for 16 KB alignment. Keep checking
this when dependencies change. minSdk is 26 and compileSdk/targetSdk are 36.
AGP 9.4.1, Kotlin 2.4.21 and Gradle 9.6.0 are pinned. Compose BOM
2026.06.01 is the newest stable compatible with SDK 36: 2026.08.00 and
2026.09.00 require compileSdk 37. Lifecycle 2.10.0 and OkHttp 5.4.0 likewise
keep SDK 36 compatibility; their newer releases require SDK 37.
`basaltApplicationId` in `gradle.properties` is the single identity declaration
used for namespace and applicationId. `com.basaltfocus.app` is a placeholder
that can change until the first Play upload.

## Boundaries and safety

`:core` is pure Kotlin/JVM: no Android imports. Port numerical rules from
Windows, with JVM tests for boundaries, delays, rounding, trial expiry, key
checksums, critical apps and Soft suppression. App unit tests cover response
parsing, transport failures, offline caching and persisted transitions. Run
one test invocation per machine; never run Windows UI tiers for this work.

Sprint lengths match Windows: presets 15/25/45/60/90 and a custom 5 to 240
minutes (`SprintLength`). Debug builds alone also allow 1 to 4 minutes, so
blocking can be proven on an emulator without waiting; release builds never do.
Notice wording lives in `SoftNoticeCopy` (Windows' `SoftOverlayCopy` without
"Close"), momentum wording in `Momentum.explanation` (Windows' text), and the
end-flow panel state in `app/.../ui/EndFlowState.kt`, all unit-tested. Copy
must never say an app is closed: Basalt shows a notice and, at Firm and
Sealed, goes to the home screen; the app stays open in the background.

Blocking reads Usage Access events every 650 ms while a sprint runs, and uses
`TYPE_APPLICATION_OVERLAY` in a `specialUse` foreground service with an ongoing
time-left notification. Soft shows a notice and offers HOME or a five-minute
allowance after the Windows escalating wait. Firm shows a three-second notice
then HOME on each reopening. Sealed also locks blocklist edits. Apps stay open.
All shields have the Windows two-minute grace period and end-flow policies.

Never add AccessibilityService, Device Admin/owner, VpnService,
QUERY_ALL_PACKAGES, REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, root, uninstall
protection, or a way to block Settings. These are forbidden by the deliberately
timid blocker rules and the agreed Play policy approach. The picker uses
MAIN/LAUNCHER queries. Protect Basalt, all launchers, System UI, settings,
dialers/emergency apps, SIM toolkit, accessibility tools (TalkBack, Voice
Access, Switch Access) and app stores both in the picker and at enforcement.
Permissions require separate explanation pages before opening system UI;
denial and revocation must remain usable.

## Persistence and privacy

DataStore holds trial, settings, blocklist, license cache and active sprint.
Room holds history; deterministic sprint IDs make recovery idempotent.
Android Auto Backup includes the trial and settings. Reinstall usually restores
the trial; clearing data can restart it, an accepted limitation. A cached
license survives transport failure without an arbitrary expiry, matching
Windows; a definitive rejection removes access. The license cache is bound
to the salted device ID so a backup restored to another phone claims its own
seat. Only POST `/validate` leaves the phone: key or purchase email, SHA-256
of `FlowShield.device.v1|android|` plus ANDROID_ID, and manufacturer/model.
Never log those values or read the user-set device name.

Default license origin is the existing Render service. For a local test use
`-PbasaltLicenseBaseUrl=http://10.0.2.2:3000`; cleartext is allowed only in debug
and only to emulator/loopback hosts. Cold-start retries follow Windows and
have a 75-second total cap. Google Play Billing belongs to #413; the access
policy is its seam and there is no billing implementation or purchase UI.

## Recovery and verification

START_STICKY resumes a persisted sprint while time remains. BOOT_COMPLETED
may start specialUse on API 35/36 (Android's prohibited boot types do not
include it); if the platform refuses, post a notification opening Basalt.
Force-stop and manufacturer battery savers can stop enforcement. Link only
to the system battery settings; never request an exemption automatically.
Expired persisted sprints are settled once into history on recovery.

Use emulator `medium_phone` headless for interception proof. Save screenshots
outside the repository, e.g. `%TEMP%\basalt-android-shots`, and shut it down
after verification. Verify Soft allowance, Firm HOME, Sealed editing and end
flows, recovery, permission denial and large text. Physical OEM battery
behavior and Surface Duo hinges still require device verification.

Lint warnings allowed in this build: SDK/dependency update notices reflect the
required SDK 36 and tested pins; HardwareIds is the explicitly agreed salted
ANDROID_ID seat protocol (the raw ID never leaves the phone); UseKtx is a style
suggestion.
Test-only org.json and Robolectric are pinned to the versions used by the JVM
suite rather than automatically following each new release. No lint errors or
baseline suppressions are allowed.

Theme colors are generated into the APK from `../design/tokens.json` at build
time. Inter and its OFL notice are embedded; type and spacing map the design
system. No animated transitions are needed; timer progress updates discretely.

## Implementation order

1. Establish wrapper, two modules, manifest, CI and generated theme resources.
2. Port core policy and license behavior with JVM boundary tests.
3. Add transactional sprint persistence, permission flow, service and screens.
4. Run JVM tests, lint, APK build and emulator interception/recovery checks.
5. Review the complete diff and commit locally; parent handles PR work.
