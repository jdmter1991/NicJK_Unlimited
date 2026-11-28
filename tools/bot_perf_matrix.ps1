# Runs bot_perf_bench.ps1 over a matrix of maps, bot counts, server rates and cvar sets.
#   bot_perf_matrix.ps1 -DevDir <dir> -Label base -Maps "mp/ffa3","naboo_theed" -Bots 8,16,24,32 -SvFps 40
#   -Configs takes name=cvars pairs, e.g. -Configs "orig=+set bot_ai_fps 0","ai20=+set bot_ai_fps 20"
# Maps other than the stock ones are read from -SteamBase (fs_basepath only; nothing is written there).
param(
    [Parameter(Mandatory = $true)][string]$DevDir,
    [string]$Label = "run",
    [string[]]$Maps = @("mp/ffa3", "naboo_theed"),
    [int[]]$Bots = @(8, 16, 24, 32),
    [int[]]$SvFps = @(40),
    [string[]]$Configs = @("default="),
    [int]$Warmup = 20,
    [int]$Duration = 60,
    [int]$Repeat = 1,
    [int]$Port = 29240,
    [string]$Seed = "",
    [string]$Results = "",
    [string]$TestBase = "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData",
    [string]$SteamBase = "B:\SteamLibrary\steamapps\common\Jedi Academy\GameData"
)
$bench = Join-Path $PSScriptRoot "bot_perf_bench.ps1"
if (-not $Results) { $Results = Join-Path $DevDir "perf_$Label.jsonl" }
for ($rep = 1; $rep -le $Repeat; $rep++) {
    foreach ($map in $Maps) {
        $base = if ($map -like "mp/*") { $TestBase } else { $SteamBase }
        foreach ($fps in $SvFps) {
            foreach ($n in $Bots) {
                # configurations back to back for each point, so a change in machine load hits all of them alike
                foreach ($c in $Configs) {
                    $name, $extra = $c -split "=", 2
                    $tag = "{0}_{1}_{2}_b{3}_fps{4}_r{5}" -f $Label, $name, ($map -replace '[/\\]', '_'), $n, $fps, $rep
                    try {
                        & $bench -DevDir $DevDir -Bots $n -Map $map -BasePath $base -SvFps $fps -Warmup $Warmup -Duration $Duration `
                            -Port $Port -Extra $extra -Tag $tag -Seed $Seed -Results $Results
                    } catch { "$tag FAILED: $_" }
                }
            }
        }
    }
}
