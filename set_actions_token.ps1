# Gedeelde GitHub-token voor de knoppen op het online dashboard. Zelf uitvoeren:
#   powershell -ExecutionPolicy Bypass -File .\set_actions_token.ps1
# Maak eerst een fine-grained token: https://github.com/settings/personal-access-tokens/new
#   Repository access: Only select repositories -> ankolmv/hardloopdashboard
#   Permissions -> Actions: Read and write
$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "ankolmv/hardloopdashboard"

$s = Read-Host -Prompt "Plak je token (github_pat_...)" -AsSecureString
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
try { $tok = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b).Trim() } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
if (-not $tok.StartsWith("github_pat_")) { throw "Dit lijkt geen fine-grained token (moet beginnen met github_pat_)." }

& $gh secret set ACTIONS_TOKEN -R $repo -b $tok
Remove-Variable tok
Write-Host "Token ingesteld. Site wordt opnieuw gebouwd (1-2 min)..."
& $gh workflow run dashboard.yml -R $repo -f action=sync
Write-Host "Klaar. Na ~2 minuten werken de knoppen op al je apparaten na het inloggen."
