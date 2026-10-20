# OpenRouteService-sleutel voor automatische looproutes. Zelf uitvoeren:
#   powershell -ExecutionPolicy Bypass -File .\set_ors_key.ps1
# Maak eerst een gratis sleutel: https://openrouteservice.org/dev/#/signup  (Dashboard -> Tokens -> Create token)
# De sleutel komt in .env (lokaal dashboard) en als secret ORS_KEY in GitHub (online dashboard).
$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "ankolmv/hardloopdashboard"
Set-Location $PSScriptRoot

$s = Read-Host -Prompt "Plak je OpenRouteService-sleutel" -AsSecureString
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b).Trim() } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
if ($key.Length -lt 20) { throw "Dit lijkt geen geldige sleutel." }

# Lokaal: .env bijwerken (bestaande ORS-regel vervangen)
$lines = @(Get-Content .env | Where-Object { $_ -notmatch '^ORS_API_KEY=' })
$lines += "ORS_API_KEY=$key"
Set-Content .env $lines -Encoding ASCII  # geen BOM: anders wordt de eerste regel niet gelezen

# Online
& $gh secret set ORS_KEY -R $repo -b $key
Remove-Variable key
Write-Host "Sleutel ingesteld. Site wordt opnieuw gebouwd (1-2 min)..."
& $gh workflow run dashboard.yml -R $repo -f action=sync
Write-Host "Klaar."
