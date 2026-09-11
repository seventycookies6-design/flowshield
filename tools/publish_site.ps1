<#
.SYNOPSIS
    Publish Website/ to the gh-pages branch, which GitHub Pages serves.

.DESCRIPTION
    GitHub Pages can only serve a branch root or a /docs folder, and the site
    lives in Website/. Rather than duplicating it into /docs, this splits
    Website/ into its own commit history and force-pushes that to gh-pages.

    A GitHub Actions workflow would be the more modern option, but pushing one
    requires the 'workflow' OAuth scope that the local gh token does not carry.
    This needs no extra permissions. To switch later:
        gh auth refresh -s workflow

.EXAMPLE
    pwsh tools/publish_site.ps1
#>

# Native commands write progress to stderr, which Windows PowerShell turns into
# a terminating NativeCommandError under 'Stop'. Check $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
Set-Location (Join-Path $PSScriptRoot '..')

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & git @Arguments 2>&1
    return [pscustomobject]@{ Output = $output; ExitCode = $LASTEXITCODE }
}

Write-Host ''
Write-Host '  Publishing Website/ to gh-pages' -ForegroundColor Cyan
Write-Host ''

# --- refuse to publish secrets ------------------------------------------------

$secretPattern = 'sk_test_[A-Za-z0-9]{16,}|sk_live_|whsec_[A-Za-z0-9]{16,}|pk_live_'
$leaks = Get-ChildItem -Path 'Website' -Recurse -File |
    Select-String -Pattern $secretPattern -ErrorAction SilentlyContinue

if ($leaks) {
    Write-Host '  A Stripe secret appears in Website/ - refusing to publish:' -ForegroundColor Red
    $leaks | ForEach-Object { Write-Host "    $($_.Filename):$($_.LineNumber)" -ForegroundColor Red }
    exit 1
}

# `git ls-files <path>` prints the path when tracked and nothing when not,
# exiting 0 either way — no stderr to trip over.
if ((Invoke-Git ls-files '.stripe_keys.json').Output) {
    Write-Host '  .stripe_keys.json is tracked in git - refusing to publish.' -ForegroundColor Red
    exit 1
}
Write-Host '  No secrets found in Website/.' -ForegroundColor DarkGray

# --- uncommitted changes would be silently left behind ------------------------

if ((Invoke-Git status --porcelain -- Website).Output) {
    Write-Host '  Website/ has uncommitted changes. Commit them first:' -ForegroundColor Yellow
    (Invoke-Git status --short -- Website).Output | ForEach-Object { Write-Host "    $_" }
    exit 1
}

# --- split and push -----------------------------------------------------------

$branch = (Invoke-Git rev-parse --abbrev-ref HEAD).Output | Select-Object -First 1
Write-Host "  Splitting Website/ out of $branch ..." -ForegroundColor DarkGray

$split = Invoke-Git subtree split --prefix Website $branch
# subtree prints progress lines; the commit sha is the last 40-hex line.
$sha = $split.Output | ForEach-Object { "$_".Trim() } |
    Where-Object { $_ -match '^[0-9a-f]{40}$' } | Select-Object -Last 1

if (-not $sha) {
    Write-Host '  git subtree split produced no commit:' -ForegroundColor Red
    $split.Output | ForEach-Object { Write-Host "    $_" }
    exit 1
}

Write-Host "  Pushing $($sha.Substring(0,8)) to gh-pages ..." -ForegroundColor DarkGray
$push = Invoke-Git push origin "$($sha):refs/heads/gh-pages" --force
if ($push.ExitCode -ne 0) {
    Write-Host '  Push failed:' -ForegroundColor Red
    $push.Output | ForEach-Object { Write-Host "    $_" }
    exit 1
}

$remote = ((Invoke-Git remote get-url origin).Output | Select-Object -First 1) `
    -replace '\.git$', '' -replace '^https://github\.com/', ''
Write-Host ''
Write-Host '  Published.' -ForegroundColor Green
Write-Host "  Pages usually refreshes within a minute: https://$($remote.Split('/')[0]).github.io/$($remote.Split('/')[1])/"
Write-Host ''
