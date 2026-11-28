# Start the dev dedicated server on Korriban with bots and connect the dev client to it.
# The server stops when you quit the game. Your original installation is only read.
#   watch_bots.ps1 [-Bots 26] [-Renderer rd-vulkant] [-Cheats]
param(
    [int]$Bots = 26,
    [string]$Renderer = "rd-vulkant",
    [int]$BotFixes = 1,      # server cvar bot_fixes; always set, so a value left behind by a test run cannot leak in
    [int]$BotFeatures = 12577279, # server cvar bot_features; 12577279 = default (all switches except 512, 1024, 4096 and 4194304)
    [switch]$Cheats,        # devmap: allows noclip / setviewpos / god for looking around
    [string]$Map = "swtor_korriban",
    [string]$DevDir = "E:\jedi academy modding archive\TaystJK_AI_Claude_Code_improvements\devgame_dev",
    [string]$BasePath = "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData",
    [int]$Port = 29170
)
$ErrorActionPreference = "Stop"
$modDir = Join-Path $DevDir "nicjk"
. (Join-Path $PSScriptRoot "bot_names.ps1")   # bot characters: the user's list
$lines = Get-BotLines -Bots $Bots
($lines -join "`r`n") + "`r`n" | Out-File -Encoding ascii (Join-Path $modDir "bench_bots.cfg")

$clientHome = Join-Path $DevDir "clienthome"
New-Item -ItemType Directory -Force (Join-Path $clientHome "nicjk") | Out-Null
Copy-Item (Join-Path $modDir "cgamex86_64.dll"), (Join-Path $modDir "uix86_64.dll") (Join-Path $clientHome "nicjk") -Force

$mapCmd = if ($Cheats) { "+devmap $Map" } else { "+map $Map" }
$fixArg = "+set bot_fixes $BotFixes +set bot_features $BotFeatures +set bot_abTest 0"
$sArgs = "+set fs_basepath `"$BasePath`" +set fs_homepath `"$DevDir`" +set fs_game nicjk +set dedicated 1 +set net_port $Port " +
    "+exec bench.cfg +set logfile 1 +set sv_profile 30 +set bot_profile 30 +set sv_crashStacks 1 $fixArg $mapCmd +exec bench_bots.cfg"
$cArgs = "+set fs_basepath `"$BasePath`" +set fs_homepath `"$clientHome`" +set fs_game nicjk +set net_port $($Port + 1) " +
    "+set cl_renderer $Renderer +set cg_drawFPS 1 +connect 127.0.0.1:$Port"

$srv = Start-Process -FilePath (Join-Path $DevDir "nicjkded.x86_64.exe") -ArgumentList $sArgs -WorkingDirectory $DevDir -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $env:TEMP "tjk_srv_out.tmp") -RedirectStandardError (Join-Path $env:TEMP "tjk_srv_err.tmp")
# Other heavy jobs on the PC must not starve the game: the server is single-threaded and falls
# hopelessly behind if it does not get a core, which shows up as "Awaiting challenge" on the client.
try { $srv.PriorityClass = "High" } catch {}
try {
    "Server starting (map load takes about 30 seconds)..."
    Start-Sleep -Seconds 30
    $srv.Refresh(); if ($srv.HasExited) { "Server exited during startup."; return }
    $cl = Start-Process -FilePath (Join-Path $DevDir "nicjk.x86_64.exe") -ArgumentList $cArgs -WorkingDirectory $DevDir -PassThru
    try { $cl.PriorityClass = "AboveNormal" } catch {}
    $cl.WaitForExit()
}
finally {
    if (-not $srv.HasExited) { Stop-Process -Id $srv.Id -Force; $null = $srv.WaitForExit(15000) }
    Start-Sleep -Seconds 2
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $slog = Join-Path $modDir "qconsole.log"
    if (Test-Path $slog) { Copy-Item $slog (Join-Path $DevDir "watch_$stamp.server.log") -Force; "Server log: watch_$stamp.server.log" }
}
