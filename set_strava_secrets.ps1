# Strava-koppeling ook online gebruiken. Zelf uitvoeren NA python strava_login.py:
#   powershell -ExecutionPolicy Bypass -File .\set_strava_secrets.ps1
$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "ankolmv/hardloopdashboard"
Set-Location $PSScriptRoot
$t = Get-Content ".strava_tokens\tokens.json" -Raw | ConvertFrom-Json
& $gh secret set STRAVA_CLIENT_ID -R $repo -b "$($t.client_id)"
& $gh secret set STRAVA_CLIENT_SECRET -R $repo -b "$($t.client_secret)"
& $gh secret set STRAVA_REFRESH_TOKEN -R $repo -b "$($t.refresh_token)"
Remove-Variable t
Write-Host "Strava-secrets ingesteld. Site wordt opnieuw gebouwd (1-2 min)..."
& $gh workflow run dashboard.yml -R $repo -f action=sync
