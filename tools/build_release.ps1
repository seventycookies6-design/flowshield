<#
.SYNOPSIS
    Build a distributable FlowShield release: installer, portable zip, update feed.

.DESCRIPTION
    Produces a self-contained build (no .NET runtime needed on the customer's
    machine) and packages it with Velopack, which generates the installer and
    the metadata the in-app updater reads from GitHub Releases.

    Everything lands in dist/releases/:
      FlowShield-win-Setup.exe      what customers download
      FlowShield-win-Portable.zip   no-install alternative
      FlowShield-<v>-full.nupkg     the payload the updater downloads
      RELEASES, releases.win.json   the update feed

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

Step "Publishing self-contained win-x64 build"
# Self-contained on purpose: a stranger who downloads this will not have the
# .NET Desktop Runtime, and "install this other thing first" loses most of them.
& dotnet publish 'DesktopApp\FlowShield.csproj' `
    -c Release -r win-x64 --self-contained true `
    -p:Version=$Version -p:FileVersion=$Version -p:AssemblyVersion=$Version `
    -o 'dist\publish' --nologo -v minimal
if ($LASTEXITCODE -ne 0) { Fail 'dotnet publish failed' }

Step "Packaging $Version"
& vpk pack `
    --packId FlowShield `
    --packVersion $Version `
    --packDir 'dist\publish' `
    --mainExe 'FlowShield.exe' `
    --packTitle 'FlowShield' `
    --packAuthors 'FlowShield' `
    --icon 'DesktopApp\Assets\FlowShield.ico' `
    --outputDir 'dist\releases'
if ($LASTEXITCODE -ne 0) { Fail 'vpk pack failed' }

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

    $notes = "FlowShield $Version`n`nDownload **FlowShield-win-Setup.exe** below.`n`n" +
             "Windows SmartScreen will warn that the publisher is unknown, because " +
             "this build is not code signed. Choose More info -> Run anyway."

    & gh release create "v$Version" `
        'dist\releases\FlowShield-win-Setup.exe' `
        'dist\releases\FlowShield-win-Portable.zip' `
        "dist\releases\FlowShield-$Version-full.nupkg" `
        'dist\releases\RELEASES' `
        'dist\releases\releases.win.json' `
        --title "FlowShield $Version" --notes $notes
    if ($LASTEXITCODE -ne 0) { Fail 'gh release create failed' }

    Write-Host "`n  Published: https://github.com/seventycookies6-design/flowshield/releases/tag/v$Version" -ForegroundColor Green
}

Write-Host ''
