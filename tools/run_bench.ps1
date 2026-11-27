# Runs a dedicated server from an isolated dev directory against the original GameData (read-only)
# and measures process CPU time over a fixed window. Usage:
#   run_bench.ps1 -DevDir <dir> -Bots 10 -Warmup 45 -Duration 60 [-Map swtor_korriban] [-Extra "+set foo 1"]
param(
    [Parameter(Mandatory = $true)][string]$DevDir,
    [int]$Bots = 0,
    [int]$Warmup = 45,
    [int]$Duration = 60,
    [string]$Map = "swtor_korriban",
    [string]$BasePath = "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData",
    [int]$Port = 29170,
    [string]$Extra = "",
    [string]$Tag = "",
    [switch]$QuietConsole   # discard stdout/stderr (console writes can block the server); read nicjk\qconsole.log instead
)
$ErrorActionPreference = "Stop"
$exe = Join-Path $DevDir "nicjkded.x86_64.exe"
$modDir = Join-Path $DevDir "nicjk"
# bot characters: the user's list (tools/bot_names.ps1). In an A/B test (bot_abTest N in -Extra)
# the first N are repeated so both groups hold the same characters.
. (Join-Path $PSScriptRoot "bot_names.ps1")
$cycle = if ($Extra -match 'bot_abTest\s+(\d+)') { [int]$Matches[1] } else { 0 }
$lines = Get-BotLines -Bots $Bots -Cycle $cycle
$botCfg = "bench_bots.cfg"
($lines -join "`r`n") + "`r`n" | Out-File -Encoding ascii (Join-Path $modDir $botCfg)

$stamp = if ($Tag) { $Tag } else { "b$Bots" }
$outLog = Join-Path $DevDir "bench_$stamp.stdout.log"
$errLog = Join-Path $DevDir "bench_$stamp.stderr.log"
$qlog = Join-Path $modDir "qconsole.log"
if (Test-Path $qlog) { Remove-Item $qlog -Force -ErrorAction SilentlyContinue }

$argList = "+set fs_basepath `"$BasePath`" +set fs_homepath `"$DevDir`" +set fs_game nicjk +set dedicated 1 " +
    "+set net_port $Port +set com_hunkmegs 2048 +exec bench.cfg $Extra +map $Map +exec $botCfg"
if ($QuietConsole) {
    $argList = $argList + " +set logfile 1"
    $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $DevDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $env:TEMP "tjk_bench_out.tmp") -RedirectStandardError (Join-Path $env:TEMP "tjk_bench_err.tmp")
} else {
    $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $DevDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog
}
try { $p.PriorityClass = "High" } catch {}
try {
    $t0 = Get-Date
    Start-Sleep -Seconds $Warmup
    $p.Refresh()
    if ($p.HasExited) { "SERVER EXITED during warmup, code $($p.ExitCode)"; return }
    $cpu0 = $p.TotalProcessorTime.TotalSeconds; $w0 = Get-Date
    $samples = @()
    $last = $cpu0; $lastT = $w0
    while (((Get-Date) - $w0).TotalSeconds -lt $Duration) {
        Start-Sleep -Milliseconds 1000
        $p.Refresh()
        if ($p.HasExited) { "SERVER EXITED during measurement, code $($p.ExitCode)"; break }
        $now = Get-Date; $c = $p.TotalProcessorTime.TotalSeconds
        $samples += ($c - $last) / ($now - $lastT).TotalSeconds
        $last = $c; $lastT = $now
    }
    $p.Refresh()
    $wall = ((Get-Date) - $w0).TotalSeconds
    $cpu = $p.TotalProcessorTime.TotalSeconds - $cpu0
    $sorted = $samples | Sort-Object
    $res = [pscustomobject]@{
        tag           = $stamp
        bots          = $Bots
        warmup_s      = $Warmup
        window_s      = [math]::Round($wall, 1)
        cpu_s         = [math]::Round($cpu, 2)
        cpu_core_pct  = [math]::Round(100 * $cpu / $wall, 1)
        ms_per_frame40 = [math]::Round(1000 * $cpu / $wall / 40, 2)
        worst_1s_pct  = if ($sorted) { [math]::Round(100 * $sorted[-1], 1) } else { 0 }
        ws_mb         = [math]::Round($p.WorkingSet64 / 1MB, 0)
        peak_ws_mb    = [math]::Round($p.PeakWorkingSet64 / 1MB, 0)
        private_mb    = [math]::Round($p.PrivateMemorySize64 / 1MB, 0)
    }
    $res | Format-List
    $res | ConvertTo-Json -Compress | Add-Content (Join-Path $DevDir "bench_results.jsonl")
}
finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; $null = $p.WaitForExit(15000) }
    Start-Sleep -Seconds 2
    if (Test-Path $qlog) { Copy-Item $qlog (Join-Path $DevDir "bench_$stamp.qconsole.log") -Force -ErrorAction SilentlyContinue }
}
