# Accès distant à EchoHub par Tailscale — à lancer UNE fois, en administrateur.
#
# Pourquoi Tailscale et pas un tunnel public : EchoHub n'a AUCUNE authentification, et son bac à
# sable exécute du Python réel avec le réseau ouvert (`CAP_SYS_ADMIN` absent du conteneur, voir
# `backend/outils/bac_a_sable.py`). Une URL publique — ngrok ou autre — donnerait donc à quiconque
# la trouve les conversations, l'exécution de code sur cette machine, et le contrôle de la VRAM.
# Les URL de tunnel public sont scannées en continu.
#
# Tailscale n'expose RIEN sur Internet : il monte un réseau privé chiffré entre les machines
# inscrites sous le même compte. Le téléphone y accède comme s'il était sur le LAN.
#
# Le script est idempotent : le relancer ne casse rien et sert de diagnostic.

$ErrorActionPreference = 'Stop'
$PortWeb = 37820

function Etape($n, $texte) { Write-Host "`n[$n] $texte" -ForegroundColor Cyan }
function Bon($texte)       { Write-Host "    OK   $texte" -ForegroundColor Green }
function Souci($texte)     { Write-Host "    !!   $texte" -ForegroundColor Yellow }

$estAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
            ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $estAdmin) {
    Write-Host "Ce script doit tourner en ADMINISTRATEUR." -ForegroundColor Red
    Write-Host "Clic droit sur PowerShell -> « Exécuter en tant qu'administrateur », puis relance-le."
    exit 1
}

Etape 1 "Installation de Tailscale"
$tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
if ($tailscale) {
    Bon "déjà installé : $($tailscale.Source)"
} else {
    winget install --id Tailscale.Tailscale --exact --silent `
                   --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
    Bon "installé"
}

$exe = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $exe) { $exe = "$env:ProgramFiles\Tailscale\tailscale.exe" }
if (-not (Test-Path $exe)) { Write-Host "tailscale introuvable après installation." -ForegroundColor Red; exit 1 }

Etape 2 "Connexion au compte Tailscale"
# `tailscale up` ouvre le navigateur pour l'authentification. C'est TOI qui t'y connectes : aucun
# identifiant n'est saisi par un script, et aucun n'est stocké dans ce dépôt.
$etat = & $exe status --json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
if ($etat -and $etat.BackendState -eq 'Running') {
    Bon "déjà connecté sous $($etat.Self.HostName)"
} else {
    Souci "une page va s'ouvrir dans le navigateur : connecte-toi avec ton compte"
    & $exe up
}

Etape 3 "Adresse privée de cette machine"
$ip = (& $exe ip -4 2>$null | Select-Object -First 1)
if (-not $ip) { Write-Host "Pas d'adresse Tailscale : la connexion a échoué." -ForegroundColor Red; exit 1 }
Bon "adresse Tailscale : $ip"

Etape 4 "Ouverture du port $PortWeb sur l'interface Tailscale UNIQUEMENT"
# Portée restreinte à la plage 100.64.0.0/10 (CGNAT), celle que Tailscale utilise. Le port ne
# devient donc pas joignable depuis un réseau public ou un wifi partagé.
$regle = "EchoHub via Tailscale"
Get-NetFirewallRule -DisplayName $regle -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $regle -Direction Inbound -Action Allow `
                    -Protocol TCP -LocalPort $PortWeb -RemoteAddress 100.64.0.0/10 | Out-Null
Bon "port $PortWeb autorisé depuis 100.64.0.0/10 seulement"

Etape 5 "Vérification qu'EchoHub répond"
try {
    $code = (Invoke-WebRequest "http://localhost:$PortWeb/" -UseBasicParsing -TimeoutSec 10).StatusCode
    Bon "EchoHub répond localement (HTTP $code)"
} catch {
    Souci "EchoHub ne répond pas sur le port $PortWeb — le conteneur tourne-t-il ? (docker compose up -d)"
}

Write-Host "`n=== Depuis ton téléphone ===" -ForegroundColor Cyan
Write-Host "  1. installe l'application Tailscale"
Write-Host "  2. connecte-toi avec LE MÊME compte que celui utilisé ci-dessus"
Write-Host "  3. ouvre :  http://${ip}:$PortWeb"
Write-Host "`nRien n'est exposé sur Internet : cette adresse n'existe que dans ton réseau privé."
Write-Host "Tant qu'EchoHub n'a pas d'authentification, toute machine INSCRITE sur ton compte"
Write-Host "Tailscale y a un accès complet — n'y ajoute que tes propres appareils." -ForegroundColor Yellow
