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

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

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

if (git ls-files --error-unmatch '.stripe_keys.json' 2>$null) {
    Write-Host '  .stripe_keys.json is tracked in git - refusing to publish.' -ForegroundColor Red
    exit 1
}
Write-Host '  No secrets found in Website/.' -ForegroundColor DarkGray

# --- uncommitted changes would be silently left behind ------------------------

if (git status --porcelain -- Website) {
    Write-Host '  Website/ has uncommitted changes. Commit them first:' -ForegroundColor Yellow
    git status --short -- Website
    exit 1
}

# --- split and push -----------------------------------------------------------

$branch = git rev-parse --abbrev-ref HEAD
Write-Host "  Splitting Website/ out of $branch ..." -ForegroundColor DarkGray
$sha = (git subtree split --prefix Website $branch).Trim()

if (-not $sha) {
    Write-Host '  git subtree split produced no commit.' -ForegroundColor Red
    exit 1
}

Write-Host "  Pushing $($sha.Substring(0,8)) to gh-pages ..." -ForegroundColor DarkGray
git push origin "$($sha):refs/heads/gh-pages" --force | Out-Null

$remote = (git remote get-url origin) -replace '\.git$', '' -replace '^https://github\.com/', ''
Write-Host ''
Write-Host '  Published.' -ForegroundColor Green
Write-Host "  Pages usually refreshes within a minute: https://$($remote.Split('/')[0]).github.io/$($remote.Split('/')[1])/"
Write-Host ''
