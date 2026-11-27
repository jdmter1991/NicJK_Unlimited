# Records what bots do, as seen in the client: dev server with bots + dev client as a spectator that
# follows one bot after another and takes a screenshot every 0.2 s. The pictures land in
# devgame_dev\clienthome_bench\nicjk\screenshots and are moved to reports\footage\<Tag>.
#   record_bots.ps1 [-Bots 24] [-Follow 2,5,9,14,18,22] [-Seconds 8] [-Tag jumps]
param(
    [int]$Bots = 24,
    [int[]]$Follow = @(2, 5, 9, 14, 18, 22),
    [int]$Seconds = 8,
    [string]$Tag = "footage",
    [int]$BotFeatures = 12577279,
    [string]$Map = "swtor_korriban",
    [string]$Root = "E:\jedi academy modding archive\TaystJK_AI_Claude_Code_improvements",
    [string]$BasePath = "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData",
    [int]$Port = 29170,
    [string]$Extra = ""   # more server settings, e.g. "+set g_mb2manualblock 1"
)
$ErrorActionPreference = "Stop"
$DevDir = Join-Path $Root "devgame_dev"
$modDir = Join-Path $DevDir "nicjk"
. (Join-Path $PSScriptRoot "bot_names.ps1")   # bot characters: the user's list
$lines = Get-BotLines -Bots $Bots
($lines -join "`r`n") + "`r`n" | Out-File -Encoding ascii (Join-Path $modDir "bench_bots.cfg")

$cfg = @()
# one picture a second (the game names screenshots by the second, so faster ones would overwrite)
$chain = @()
for ($i = 0; $i -lt $Follow.Count; $i++) {
    $shots = (1..$Seconds | ForEach-Object { "screenshot; wait 125" }) -join "; "
    $chain += , @("f$i", "follow $($Follow[$i]); wait 150; echo FOLLOW $i $($Follow[$i]); $shots")
}
for ($k = 0; $k -lt $chain.Count; $k++) {
    $next = if ($k + 1 -lt $chain.Count) { "vstr $($chain[$k + 1][0])" } else { "echo BENCH_END; wait 20; quit" }
    $cfg += 'set {0} "{1}; {2}"' -f $chain[$k][0], $chain[$k][1], $next
}
$cfg += 'set benchgo "wait 2500; team s; wait 250; togglemenu; wait 60; vstr f0"'
$cfg += "vstr benchgo"
$clientHome = Join-Path $DevDir "clienthome_bench"
New-Item -ItemType Directory -Force (Join-Path $clientHome "nicjk") | Out-Null
($cfg -join "`r`n") + "`r`n" | Out-File -Encoding ascii (Join-Path $clientHome "nicjk\recordbots.cfg")
Copy-Item (Join-Path $modDir "cgamex86_64.dll"), (Join-Path $modDir "uix86_64.dll") (Join-Path $clientHome "nicjk") -Force
$shots = Join-Path $clientHome "nicjk\screenshots"
if (Test-Path $shots) { Get-ChildItem $shots -File | Remove-Item -Force }
$clog = Join-Path $clientHome "nicjk\qconsole.log"
Remove-Item $clog -Force -ErrorAction SilentlyContinue

$sArgs = "+set fs_basepath `"$BasePath`" +set fs_homepath `"$DevDir`" +set fs_game nicjk +set dedicated 1 +set net_port $Port " +
    "+exec bench.cfg +set logfile 1 +set bot_profile 30 +set bot_fixes 1 +set bot_features $BotFeatures +set bot_abTest 0 $Extra +devmap $Map +exec bench_bots.cfg"
$cArgs = "+set fs_basepath `"$BasePath`" +set fs_homepath `"$clientHome`" +set fs_game nicjk +set net_port $($Port + 1) " +
    "+set cl_renderer rd-vulkant +set r_fullscreen 0 +set r_mode -1 +set r_customwidth 960 +set r_customheight 540 +set r_swapInterval 0 " +
    "+set com_maxfps 125 +set s_volume 0 +set s_musicvolume 0 +set logfile 1 +set cg_thirdPerson 1 +set cg_drawFPS 0 +set cg_draw2D 1 +set forcepowers 0-1-000000000000000000 " +
    "+connect 127.0.0.1:$Port +exec recordbots.cfg"
$srv = Start-Process -FilePath (Join-Path $DevDir "nicjkded.x86_64.exe") -ArgumentList $sArgs -WorkingDirectory $DevDir -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $env:TEMP "tjk_srv_out.tmp") -RedirectStandardError (Join-Path $env:TEMP "tjk_srv_err.tmp")
try { $srv.PriorityClass = "High" } catch {}
$cl = $null
try {
    Start-Sleep -Seconds 30
    $srv.Refresh(); if ($srv.HasExited) { "SERVER EXITED before client start"; return }
    $cl = Start-Process -FilePath (Join-Path $DevDir "nicjk.x86_64.exe") -ArgumentList $cArgs -WorkingDirectory $DevDir -PassThru
    $t0 = Get-Date
    $limit = 240 + $Follow.Count * ($Seconds * 2 + 5)
    while (-not $cl.HasExited -and ((Get-Date) - $t0).TotalSeconds -lt $limit) { Start-Sleep -Seconds 2; $cl.Refresh() }
    "client ran {0:n0} s, exited={1}" -f ((Get-Date) - $t0).TotalSeconds, $cl.HasExited
}
finally {
    if ($cl -and -not $cl.HasExited) { Stop-Process -Id $cl.Id -Force; $null = $cl.WaitForExit(15000) }
    if (-not $srv.HasExited) { Stop-Process -Id $srv.Id -Force; $null = $srv.WaitForExit(15000) }
    Start-Sleep -Seconds 2
    $out = Join-Path $Root "reports\footage\$Tag"
    New-Item -ItemType Directory -Force $out | Out-Null
    if (Test-Path $shots) { Get-ChildItem $shots -File | Move-Item -Destination $out -Force }
    if (Test-Path $clog) { Copy-Item $clog (Join-Path $out "client.log") -Force }
    Copy-Item (Join-Path $modDir "qconsole.log") (Join-Path $out "server.log") -Force -ErrorAction SilentlyContinue
    "{0} pictures in {1}" -f (Get-ChildItem $out -Filter *.jpg).Count, $out
    $cfgf = Join-Path $modDir "nicjk_server.cfg"
    if (Test-Path $cfgf) {
        (Get-Content $cfgf) -replace '^seta bot_features ".*"', 'seta bot_features "12577279"' -replace '^seta bot_fixes ".*"', 'seta bot_fixes "1"' | Set-Content -Encoding ascii $cfgf
    }
}
