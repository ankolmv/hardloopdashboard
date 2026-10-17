# Wachtwoord van het online dashboard (opnieuw) instellen. Zelf uitvoeren:
#   powershell -ExecutionPolicy Bypass -File .\set_password.ps1
$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "ankolmv/hardloopdashboard"

function Read-Plain($prompt) {
    $s = Read-Host -Prompt $prompt -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

while ($true) {
    $p1 = Read-Plain "Nieuw wachtwoord voor het dashboard"
    $p2 = Read-Plain "Herhaal het wachtwoord"
    if ($p1 -ne $p2) { Write-Host "De wachtwoorden zijn niet gelijk, probeer opnieuw." -ForegroundColor Yellow; continue }
    if ($p1.Length -lt 8) { Write-Host "Gebruik minstens 8 tekens." -ForegroundColor Yellow; continue }
    break
}
& $gh secret set DASHBOARD_PASSWORD -R $repo -b $p1
Remove-Variable p1, p2
Write-Host "Wachtwoord ingesteld. Site wordt opnieuw gebouwd (1-2 min)..."
& $gh workflow run dashboard.yml -R $repo -f action=sync
Write-Host "Klaar. Open over 2 minuten https://ankolmv.github.io/hardloopdashboard/ en log in met je nieuwe wachtwoord."
