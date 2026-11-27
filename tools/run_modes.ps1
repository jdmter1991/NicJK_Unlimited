# Runs bots in several game modes one after another on a dedicated dev server and prints what
# happened in each: team scores, flags taken / captured / returned, siege objectives, kills by
# weapon type, kills of teammates. One block per mode is appended to reports\MODES_LOG.txt.
#   run_modes.ps1 [-Minutes 5] [-Bots 16] [-Only tffa,ctf,cty,siege,guns,ctf_korriban]
# Game types: 0 FFA, 6 Team FFA, 7 Siege, 8 CTF, 9 CTY. g_weaponDisable 0 = all weapons allowed.
param(
    [int]$Minutes = 5,
    [int]$Bots = 16,
    [string[]]$Only = @(),
    [int]$Features = 12577279,
    [string]$Tag = "",
    [string]$Root = "E:\jedi academy modding archive\TaystJK_AI_Claude_Code_improvements"
)
$ErrorActionPreference = "Stop"
$dev = Join-Path $Root "devgame_dev"
$log = Join-Path $Root "reports\MODES_LOG.txt"
$modes = @(
    @{ name = "tffa";         gt = 6; map = "mp/ffa3";         wd = 524279 },   # Team FFA, sabers only, stock map with waypoints
    @{ name = "tffa_korriban"; gt = 6; map = "swtor_korriban"; wd = 524279 },   # Team FFA, no waypoints
    @{ name = "ctf";          gt = 8; map = "mp/ctf3";         wd = 524279 },   # CTF, sabers only
    @{ name = "cty";          gt = 9; map = "mp/ctf3";         wd = 524279 },   # Capture the Ysalamiri
    @{ name = "ctf_guns";     gt = 8; map = "mp/ctf4";         wd = 0 },        # CTF with all weapons
    @{ name = "guns";         gt = 0; map = "mp/ffa3";         wd = 0 },        # FFA with all weapons
    @{ name = "siege";        gt = 7; map = "mp/siege_hoth";   wd = 0 },
    @{ name = "siege_desert"; gt = 7; map = "mp/siege_desert"; wd = 0 }
)
try {
    foreach ($m in $modes) {
        if ($Only.Count -gt 0 -and ($Only -notcontains $m.name)) { continue }
        $extra = "+set g_gametype $($m.gt) +set g_weaponDisable $($m.wd) +set bot_abTest 0 +set bot_features $Features +set bot_tuneExplore 0 +set bot_fixes 1 +set bot_profile 60"
        $res = & (Join-Path $Root "tools\run_bench.ps1") -DevDir $dev -Bots $Bots -Warmup 30 -Duration ($Minutes * 60) -Map $m.map -Port 29190 -QuietConsole -Tag "mode" -Extra $extra
        $q = Join-Path $dev "nicjk\qconsole.log"
        $head = "== {0} {1} | {2} gametype {3} map {4} bots {5} minutes {6} features {7}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $Tag, $m.name, $m.gt, $m.map, $Bots, $Minutes, $Features
        $lines = @($head)
        if ($res -match "SERVER EXITED") { $lines += ($res | Where-Object { $_ -match "SERVER EXITED" }) }
        foreach ($pat in "BOTEVAL match", "BOTEVAL kills by", "BOTEVAL all bots", "stuck suicides", "BOTEVAL force economy") {
            $hit = Select-String -Path $q -Pattern $pat | Select-Object -Last 1
            if ($hit) { $lines += $hit.Line.Substring(20) }
        }
        $err = Select-String -Path $q -Pattern "^.{20}(ERROR|Error:|Couldn't|couldn't find map|recursive error)" | Select-Object -First 3
        foreach ($e in $err) { $lines += "LOG: " + $e.Line.Substring(20) }
        $lines | Out-File -Encoding ascii -Append $log
        $lines
        Copy-Item $q (Join-Path $dev "mode_$($m.name).qconsole.log") -Force
    }
}
finally {
    $cfg = Join-Path $dev "nicjk\nicjk_server.cfg"
    if (Test-Path $cfg) {
        (Get-Content $cfg) -replace '^seta bot_features ".*"', 'seta bot_features "12577279"' -replace '^seta bot_fixes ".*"', 'seta bot_fixes "1"' `
            -replace '^seta g_gametype ".*"', 'seta g_gametype "0"' -replace '^seta g_weaponDisable ".*"', 'seta g_weaponDisable "524279"' | Set-Content -Encoding ascii $cfg
    }
}
