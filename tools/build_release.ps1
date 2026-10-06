<#
.SYNOPSIS
    Build a distributable Basalt release: installer, portable zip, update feed.

    Basalt was called FlowShield (#321). The package id, the exe and the
    artifact names keep the old name: a new package id would leave every
    installed copy on its old version, because the updater looks for its own id.

.DESCRIPTION
    Produces a self-contained build (no .NET runtime needed on the customer's
    machine) and packages it with Velopack, which generates the installer and
    the metadata the in-app updater reads from GitHub Releases.

    Two builds, one per processor, each on its own Velopack channel so an
    installed copy only ever updates to the build for its own processor.
    Everything lands in dist/releases/:

      win-x64 (most PCs; channel "win", file names unchanged since 1.0.0)
        FlowShield-win-Setup.exe              what customers download
        FlowShield-win-Portable.zip           no-install alternative
        FlowShield-<v>-full.nupkg             the payload the updater downloads
        RELEASES, releases.win.json           the update feed

      win-arm64 (Windows on ARM laptops, e.g. Snapdragon; channel "win-arm64")
        FlowShield-win-arm64-Setup.exe
        FlowShield-win-arm64-Portable.zip
        FlowShield-<v>-win-arm64-full.nupkg
        RELEASES-win-arm64, releases.win-arm64.json

.PARAMETER Version
    Semantic version for this build. Must increase for the updater to offer it.

.PARAMETER Publish
    Also create the GitHub Release and upload the artifacts.

.EXAMPLE
    pwsh tools/build_release.ps1 -Version 1.0.1 -Publish
#>

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [switch]$Publish
)

$ErrorActionPreference = 'Continue'
Set-Location (Join-Path $PSScriptRoot '..')

function Step($text) { Write-Host "`n  $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "  $text" -ForegroundColor Red; exit 1 }

if ($Version -notmatch '^\d+\.\d+\.\d+$') { Fail "Version must look like 1.2.3, got '$Version'" }

# vpk is a dotnet global tool and may not be on PATH in a fresh shell.
$env:Path = "$env:USERPROFILE\.dotnet\tools;$env:Path"
if (-not (Get-Command vpk -ErrorAction SilentlyContinue)) {
    Fail "vpk not found. Install it with: dotnet tool install -g vpk"
}

Step "Cleaning dist/"
Remove-Item 'dist' -Recurse -Force -ErrorAction SilentlyContinue

# The x64 build keeps Velopack's default channel ("win") so every copy
# installed before ARM64 existed keeps finding its updates under the same file
# names. ARM64 gets a channel of its own: the updater reads
# releases.<channel>.json, so an ARM install is never handed the x64 build.
# ARM laptops can run the x64 build under emulation, but a blocker that
# watches other processes is the last thing to leave to an emulator.
$targets = @(
    @{ Runtime = 'win-x64';   Channel = 'win' },
    @{ Runtime = 'win-arm64'; Channel = 'win-arm64' }
)

foreach ($t in $targets) {
    $publishDir = "dist\publish\$($t.Runtime)"

    Step "Publishing self-contained $($t.Runtime) build"
    # Self-contained on purpose: a stranger who downloads this will not have the
    # .NET Desktop Runtime, and "install this other thing first" loses most of them.
    & dotnet publish 'DesktopApp\FlowShield.csproj' `
        -c Release -r $t.Runtime --self-contained true `
        -p:Version=$Version -p:FileVersion=$Version -p:AssemblyVersion=$Version `
        -o $publishDir --nologo -v minimal
    if ($LASTEXITCODE -ne 0) { Fail "dotnet publish failed for $($t.Runtime)" }

    Step "Packaging $Version for $($t.Runtime)"
    & vpk pack `
        --packId FlowShield `
        --packVersion $Version `
        --packDir $publishDir `
        --mainExe 'FlowShield.exe' `
        --packTitle 'Basalt' `
        --packAuthors 'Basalt' `
        --icon 'DesktopApp\Assets\FlowShield.ico' `
        --runtime $t.Runtime `
        --channel $t.Channel `
        --outputDir 'dist\releases'
    if ($LASTEXITCODE -ne 0) { Fail "vpk pack failed for $($t.Runtime)" }
}

Write-Host ''
Get-ChildItem 'dist\releases' | ForEach-Object {
    '  {0,-40} {1,8:N1} MB' -f $_.Name, ($_.Length / 1MB)
}

Write-Host ''
Write-Host '  NOT CODE SIGNED.' -ForegroundColor Yellow
Write-Host '  Windows SmartScreen will warn every customer who runs this, which' -ForegroundColor Yellow
Write-Host '  matters more than usual for an app that closes other programs.' -ForegroundColor Yellow
Write-Host '  Fix: buy a code-signing certificate and pass --signParams to vpk.' -ForegroundColor Yellow

if ($Publish) {
    Step "Publishing GitHub Release v$Version"
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Fail 'gh CLI not found' }

    $notes = "Basalt $Version`n`nDownload **FlowShield-win-Setup.exe** below. " +
             "On a Windows on ARM laptop (Snapdragon, for example), download " +
             "**FlowShield-win-arm64-Setup.exe** instead.`n`n" +
             "Windows SmartScreen will warn that the publisher is unknown, because " +
             "this build is not code signed. Choose More info -> Run anyway."

    # Both channels' feeds go on the same release: the updater picks
    # releases.win.json or releases.win-arm64.json by the channel it was built with.
    & gh release create "v$Version" `
        'dist\releases\FlowShield-win-Setup.exe' `
        'dist\releases\FlowShield-win-Portable.zip' `
        "dist\releases\FlowShield-$Version-full.nupkg" `
        'dist\releases\RELEASES' `
        'dist\releases\releases.win.json' `
        'dist\releases\FlowShield-win-arm64-Setup.exe' `
        'dist\releases\FlowShield-win-arm64-Portable.zip' `
        "dist\releases\FlowShield-$Version-win-arm64-full.nupkg" `
        'dist\releases\RELEASES-win-arm64' `
        'dist\releases\releases.win-arm64.json' `
        --title "Basalt $Version" --notes $notes
    if ($LASTEXITCODE -ne 0) { Fail 'gh release create failed' }

    Write-Host "`n  Published: https://github.com/seventycookies6-design/flowshield/releases/tag/v$Version" -ForegroundColor Green
}

Write-Host ''
