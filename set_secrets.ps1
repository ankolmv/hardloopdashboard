# Zet de geheime sleutels voor de GitHub-workflow. Zelf uitvoeren:
#   powershell -ExecutionPolicy Bypass -File .\set_secrets.ps1
# Leest je sleutels uit .env en .garmin_tokens\ en stuurt ze versleuteld naar GitHub (Settings > Secrets).
$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "pubquizmooiemannen/hardloopdashboard"
Set-Location $PSScriptRoot

Write-Host "1/4 intervals.icu-sleutels uit .env ..."
& $gh secret set -R $repo -f .env

Write-Host "2/4 Garmin-token ..."
Get-Content ".garmin_tokens\garmin_tokens.json" -Raw | & $gh secret set GARMIN_TOKENS -R $repo

Write-Host "3/4 Willekeurige sleutel voor de versleutelde cache ..."
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
& $gh secret set STATE_KEY -R $repo -b ([Convert]::ToBase64String($bytes))

Write-Host "4/4 Kies het wachtwoord voor je online dashboard (je typt het, het wordt niet getoond):"
& $gh secret set DASHBOARD_PASSWORD -R $repo

Write-Host "`nKlaar. Ingestelde secrets:"
& $gh secret list -R $repo
