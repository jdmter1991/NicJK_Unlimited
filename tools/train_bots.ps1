# Self-play league for the bots' tuning by play (bot_features 32768).
# Runs match after match on a dedicated server with no client.
#   Training round:   24 bots, all exploring; every finished episode moves the shared values a little.
#                     The values are kept in devgame_dev\nicjk\bottune.dat between rounds.
#   Evaluation round: 12 bots with the hand-set values against 12 bots with the tuned values, nobody
#                     exploring, nothing learned. This is the measurement of whether tuning helped.
# The first round and every (EvalEvery+1)th after it are evaluation rounds. One line per round is
# appended to reports\TUNING_LOG.csv.
#   train_bots.ps1 [-Rounds 16] [-Minutes 10] [-EvalEvery 4] [-Features 12577279]
# Stop early by creating the file tools\stop_training.flag (it is removed when the script ends).
# Uses port 29190, so it does not collide with watch_bots.ps1 (29170); the machine should otherwise be idle.
param(
    [int]$Rounds = 16,
    [int]$Minutes = 10,
    [int]$EvalEvery = 4,
    [int]$Features = 12577279,
    [int]$Episode = 150,
    [string]$Map = "swtor_korriban",
    [string]$Root = "E:\jedi academy modding archive\TaystJK_AI_Claude_Code_improvements"
)
$ErrorActionPreference = "Stop"
$dev = Join-Path $Root "devgame_dev"
$log = Join-Path $Root "reports\TUNING_LOG.csv"
$flag = Join-Path $Root "tools\stop_training.flag"
$handSet = $Features -band (-bnot 32768)
if (-not (Test-Path $log)) {
    "time,round,kind,minutes,handset_kills,handset_deaths,tuned_kills,tuned_deaths,all_kills,all_deaths,episodes,values" | Out-File -Encoding ascii $log
}
try {
    for ($r = 1; $r -le $Rounds; $r++) {
        if (Test-Path $flag) { "stop flag found, ending after $($r - 1) rounds"; break }
        $eval = (($r - 1) % ($EvalEvery + 1)) -eq 0
        if ($eval) {
            $extra = "+set bot_abTest 12 +set bot_abBase $handSet +set bot_features $Features +set bot_tuneExplore 0 +set bot_fixes 1 +set bot_profile 60"
        } else {
            $extra = "+set bot_abTest 0 +set bot_features $Features +set bot_tuneExplore 1 +set bot_tuneEpisode $Episode +set bot_fixes 1 +set bot_profile 60"
        }
        & (Join-Path $Root "tools\run_bench.ps1") -DevDir $dev -Bots 24 -Warmup 30 -Duration ($Minutes * 60) -Map $Map -Port 29190 -QuietConsole -Tag "train" -Extra $extra | Out-Null
        $q = Join-Path $dev "nicjk\qconsole.log"
        $ab = (Select-String -Path $q -Pattern "BOTEVAL baseline: bots \d+ kills (\d+) deaths (\d+) \| features \d+: bots \d+ kills (\d+) deaths (\d+)" | Select-Object -Last 1)
        $all = (Select-String -Path $q -Pattern "BOTEVAL all bots: features \d+ bots \d+ kills (\d+) deaths (\d+)" | Select-Object -Last 1)
        $ep = (Select-String -Path $q -Pattern "BOTEVAL tuning: episodes scored (\d+)" | Select-Object -Last 1)
        $vals = (Select-String -Path $q -Pattern "BOTEVAL tuned values, hand-set in brackets:(.*)" | Select-Object -Last 1)
        $e = if ($ep) { $ep.Matches[0].Groups[1].Value } else { "" }
        $v = if ($vals) { $vals.Matches[0].Groups[1].Value.Trim() } else { "" }
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
        if ($eval -and $ab) {
            $b = $ab.Matches[0].Groups
            "$stamp,$r,eval,$Minutes,$($b[1].Value),$($b[2].Value),$($b[3].Value),$($b[4].Value),,,$e,$v" | Out-File -Encoding ascii -Append $log
            "round $r eval : hand-set $($b[1].Value)/$($b[2].Value)  tuned $($b[3].Value)/$($b[4].Value)  episodes $e"
        } elseif ((-not $eval) -and $all) {
            $a = $all.Matches[0].Groups
            "$stamp,$r,train,$Minutes,,,,,$($a[1].Value),$($a[2].Value),$e,$v" | Out-File -Encoding ascii -Append $log
            "round $r train: all $($a[1].Value)/$($a[2].Value)  episodes $e"
        } else {
            "round $r : no result lines found in the server log"
        }
    }
}
finally {
    Remove-Item $flag -Force -ErrorAction SilentlyContinue
    # run_bench passes the test settings on the command line and the server archives them: put the defaults back
    $cfg = Join-Path $dev "nicjk\nicjk_server.cfg"
    if (Test-Path $cfg) {
        (Get-Content $cfg) -replace '^seta bot_features ".*"', 'seta bot_features "12577279"' -replace '^seta bot_fixes ".*"', 'seta bot_fixes "1"' | Set-Content -Encoding ascii $cfg
    }
}
