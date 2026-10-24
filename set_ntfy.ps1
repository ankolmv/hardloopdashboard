# Meldingen via ntfy (ochtendbericht, analyse na een run, terugblik, storingen). Zelf uitvoeren:
#   powershell -ExecutionPolicy Bypass -File .\set_ntfy.ps1
# Installeer eerst de gratis app 'ntfy' (App Store / Google Play). Dit script maakt een geheim, onraadbaar
# kanaal aan, zet het in .env (lokaal) en als secret NTFY_TOPIC in GitHub (online), en stuurt een testbericht.
$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "ankolmv/hardloopdashboard"
Set-Location $PSScriptRoot

# Bestaand kanaal hergebruiken, anders een nieuw willekeurig kanaal (wie de naam kent, kan meelezen)
$old = Get-Content .env | Where-Object { $_ -match '^NTFY_TOPIC=' } | Select-Object -First 1
if ($old) {
  $topic = $old.Substring(11).Trim()
} else {
  $bytes = New-Object byte[] 12
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $topic = "hardlopen-" + (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
  $lines = @(Get-Content .env) + "NTFY_TOPIC=$topic"
  Set-Content .env $lines -Encoding ASCII  # geen BOM: anders wordt de eerste regel niet gelezen
}

& $gh secret set NTFY_TOPIC -R $repo -b $topic
python notify.py test

Write-Host ""
Write-Host "Abonneer je in de ntfy-app op dit kanaal (plus-knop, server ntfy.sh):"
Write-Host ""
Write-Host "    $topic" -ForegroundColor Green
Write-Host ""
Write-Host "Deel deze naam met niemand. Het testbericht staat klaar zodra je geabonneerd bent."
