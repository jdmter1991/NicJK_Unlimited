# Client benchmark: dev dedicated server (cheats on, N bots) + dev client connecting to it as a spectator.
# The client is teleported through fixed camera positions with setviewpos and logs com_speeds per frame.
#   run_client_bench.ps1 -DevDir <dir> -Renderer rd-vulkant -Bots 26 -Tag vk26 [-ClientExtra "+set r_distanceCull 20000"]
param(
    [Parameter(Mandatory = $true)][string]$DevDir,
    [string]$Renderer = "rd-vulkant",
    [int]$Bots = 26,
    [string]$Tag = "client",
    [string]$Map = "swtor_korriban",
    [string]$BasePath = "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData",
    [int]$Port = 29170,
    [int]$FramesPerPosition = 1200,
    [int]$Cycles = 3,
    [int]$TimeoutSec = 420,
    [string]$ClientExtra = "",
    [string[]]$Shots = @(),  # "x y z yaw" strings: take one screenshot at each instead of benchmarking
    [switch]$Lightning,     # play as a dark-side player holding force lightning instead of the camera tour
    [string]$ServerExtra = ""
)
$ErrorActionPreference = "Stop"
$modDir = Join-Path $DevDir "nicjk"
. (Join-Path $PSScriptRoot "bot_names.ps1")   # bot characters: the user's list
$lines = Get-BotLines -Bots $Bots
($lines -join "`r`n") + "`r`n" | Out-File -Encoding ascii (Join-Path $modDir "bench_bots.cfg")

# camera positions: x y z yaw (spawn areas and places where bots were seen fighting)
$pos = @(
    @("p1", "685 180 700 -180"),
    @("p2", "-3625 -1535 472 -160"),
    @("p3", "-1185 -2323 448 -90"),
    @("p4", "1980 -16050 1655 90"),
    @("p5", "6311 9527 -4465 0")
)
$cfg = @()
$chain = @()
for ($c = 1; $c -le $Cycles; $c++) { foreach ($p in $pos) { $chain += , @("c${c}_$($p[0])", $p[0], $p[1], $c) } }
for ($i = 0; $i -lt $chain.Count; $i++) {
    $next = if ($i + 1 -lt $chain.Count) { "vstr $($chain[$i + 1][0])" } else { "echo BENCH_END; wait 20; quit" }
    $cfg += 'set {0} "team s; setviewpos {1}; wait 150; echo BENCH_BEGIN cycle {2} {3}; wait {4}; echo BENCH_STOP; {5}"' -f `
        $chain[$i][0], $chain[$i][2], $chain[$i][3], $chain[$i][1], $FramesPerPosition, $next
}
$cfg += 'set benchgo "wait 2500; team s; wait 250; set com_maxfps 0; vstr {0}"' -f $chain[0][0]
$cfg += "vstr benchgo"
if ($Lightning) {
    # baseline segment, then lightning held down, three times, standing at camera position p2
    $cfg = @()
    $steps = @()
    for ($c = 1; $c -le $Cycles; $c++) { $steps += "l${c}a"; $steps += "l${c}b" }
    for ($i = 0; $i -lt $steps.Count; $i++) {
        $next = if ($i + 1 -lt $steps.Count) { "vstr $($steps[$i + 1])" } else { "echo BENCH_END; wait 20; quit" }
        $c = [math]::Floor($i / 2) + 1
        if ($i % 2 -eq 0) {
            $cfg += 'set {0} "-force_lightning; setviewpos {1}; wait 300; echo BENCH_BEGIN cycle {2} idle; wait {3}; echo BENCH_STOP; {4}"' -f $steps[$i], $pos[1][1], $c, $FramesPerPosition, $next
        } else {
            $cfg += 'set {0} "+force_lightning; wait 100; echo BENCH_BEGIN cycle {1} zap; wait {2}; echo BENCH_STOP; screenshot; wait 4; -force_lightning; {3}"' -f $steps[$i], $c, $FramesPerPosition, $next
        }
    }
    $cfg += 'set benchgo "wait 2500; set forcepowers 7-2-030330030000000330; forcechanged; team f; wait 300; kill; wait 500; +attack; wait 20; -attack; wait 700; god; set com_maxfps 0; vstr {0}"' -f $steps[0]
    $cfg += "vstr benchgo"
    $ClientExtra = $ClientExtra + ' +set forcepowers "7-2-030330030000000330"'
    $ServerExtra = $ServerExtra + ' +set g_forceRegenTime 0'
}
if ($Shots.Count -gt 0) {
    $cfg = @()
    for ($i = 0; $i -lt $Shots.Count; $i++) {
        $next = if ($i + 1 -lt $Shots.Count) { "vstr s$($i + 1)" } else { "echo BENCH_END; wait 20; quit" }
        $cfg += 'set s{0} "setviewpos {1}; wait 60; echo SHOT {0} {1}; screenshot; wait 190; {2}"' -f $i, $Shots[$i], $next
    }
    $cfg += 'set benchgo "wait 2500; team s; wait 250; set cg_draw2D 0; vstr s0"'
    $cfg += "vstr benchgo"
}
($cfg -join "`r`n") + "`r`n" | Out-File -Encoding ascii (Join-Path $modDir "clientbench.cfg")

# the client and the server share fs_homepath, so give the client its own to keep the logs apart
$clientHome = Join-Path $DevDir "clienthome_bench"   # separate from the home watch_bots.ps1 uses, so benchmark settings never leak into it
New-Item -ItemType Directory -Force (Join-Path $clientHome "nicjk") | Out-Null
Copy-Item (Join-Path $modDir "clientbench.cfg") (Join-Path $clientHome "nicjk") -Force
Copy-Item (Join-Path $modDir "cgamex86_64.dll"), (Join-Path $modDir "uix86_64.dll") (Join-Path $clientHome "nicjk") -Force
$clog = Join-Path $clientHome "nicjk\qconsole.log"
$slog = Join-Path $modDir "qconsole.log"
Remove-Item $clog, $slog -Force -ErrorAction SilentlyContinue

$sArgs = "+set fs_basepath `"$BasePath`" +set fs_homepath `"$DevDir`" +set fs_game nicjk +set dedicated 1 +set net_port $Port " +
    "+exec bench.cfg +set logfile 1 +set sv_profile 30 +set sv_crashStacks 1 $ServerExtra +devmap $Map +exec bench_bots.cfg"
$cArgs = "+set fs_basepath `"$BasePath`" +set fs_homepath `"$clientHome`" +set fs_game nicjk +set net_port $($Port + 1) " +
    "+set cl_renderer $Renderer +set r_fullscreen 0 +set r_mode -1 +set r_customwidth 1920 +set r_customheight 1080 +set r_swapInterval 0 " +
    "+set com_maxfps 125 +set s_volume 0 +set s_musicvolume 0 +set logfile 1 +set com_speeds 1 +set cg_drawFPS 1 $ClientExtra " +
    "+connect 127.0.0.1:$Port +exec clientbench.cfg"

$srv = Start-Process -FilePath (Join-Path $DevDir "nicjkded.x86_64.exe") -ArgumentList $sArgs -WorkingDirectory $DevDir -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $env:TEMP "tjk_srv_out.tmp") -RedirectStandardError (Join-Path $env:TEMP "tjk_srv_err.tmp")
try { $srv.PriorityClass = "High" } catch {}
$cl = $null
try {
    Start-Sleep -Seconds 30
    $srv.Refresh(); if ($srv.HasExited) { "SERVER EXITED before client start"; return }
    $cl = Start-Process -FilePath (Join-Path $DevDir "nicjk.x86_64.exe") -ArgumentList $cArgs -WorkingDirectory $DevDir -PassThru
    $t0 = Get-Date
    $peak = 0
    while (-not $cl.HasExited -and ((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec) {
        Start-Sleep -Seconds 2
        $cl.Refresh(); if (-not $cl.HasExited -and $cl.PeakWorkingSet64 -gt $peak) { $peak = $cl.PeakWorkingSet64 }
        $srv.Refresh(); if ($srv.HasExited) { "SERVER EXITED during client run"; break }
    }
    "client ran {0:n0} s, exited={1}, client peak working set {2:n0} MB" -f ((Get-Date) - $t0).TotalSeconds, $cl.HasExited, ($peak / 1MB)
}
finally {
    if ($cl -and -not $cl.HasExited) { Stop-Process -Id $cl.Id -Force; $null = $cl.WaitForExit(15000) }
    if (-not $srv.HasExited) { Stop-Process -Id $srv.Id -Force; $null = $srv.WaitForExit(15000) }
    Start-Sleep -Seconds 2
    if (Test-Path $clog) { Copy-Item $clog (Join-Path $DevDir "cbench_$Tag.client.log") -Force }
    if (Test-Path $slog) { Copy-Item $slog (Join-Path $DevDir "cbench_$Tag.server.log") -Force }
}






