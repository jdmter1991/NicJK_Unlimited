# A/B quality test of a bot performance setting: 2 x Group bots (the same characters in both groups),
# group A = client slots 0..Group-1 with -ACvars, group B = slots Group..2*Group-1 with -BCvars, both
# with the default bot_features. Slots 12-23 do worse than 0-11 even with identical settings, so every
# match is played in both orientations (the setting under test in group B, then in group A).
#   bot_perf_ab.ps1 -DevDir <dir> -Map mp/ffa3 -Test "+set bot_ai_fps 20" -TestBase "+set bot_ai_fpsBase 20" -Off "+set bot_ai_fps 0" -OffBase "+set bot_ai_fpsBase 0"
# The group-B cvar (bot_ai_fps, bot_perf) and its baseline-group twin (bot_ai_fpsBase, bot_perfBase)
# are given separately: -Test/-Off set the B group, -TestBase/-OffBase the A group.
param(
    [Parameter(Mandatory = $true)][string]$DevDir,
    [string]$Map = "mp/ffa3",
    [string]$BasePath = "",
    [int]$Group = 12,
    [int]$Minutes = 7,
    [int]$Matches = 2,
    [Parameter(Mandatory = $true)][string]$Test,
    [Parameter(Mandatory = $true)][string]$TestBase,
    [Parameter(Mandatory = $true)][string]$Off,
    [Parameter(Mandatory = $true)][string]$OffBase,
    [string]$Label = "ab",
    [string]$Seed = "",
    [int]$Port = 29240
)
$bench = Join-Path $PSScriptRoot "bot_perf_bench.ps1"
if (-not $BasePath) {
    $BasePath = if ($Map -like "mp/*") { "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData" } else { "B:\SteamLibrary\steamapps\common\Jedi Academy\GameData" }
}
$results = Join-Path $DevDir "ab_$Label.jsonl"
$common = "+set bot_abTest $Group +set bot_abBase 46131711 +set bot_features 46131711"
for ($m = 1; $m -le $Matches; $m++) {
    foreach ($o in @("testInB", "testInA")) {
        $extra = if ($o -eq "testInB") { "$common $Test $OffBase" } else { "$common $Off $TestBase" }
        $tag = "{0}_{1}_m{2}" -f $Label, $o, $m
        & $bench -DevDir $DevDir -Bots (2 * $Group) -Map $Map -BasePath $BasePath -Warmup 0 -Duration (60 * $Minutes) -Window 30 `
            -Port $Port -Extra $extra -Tag $tag -Seed $Seed -Results $results -Eval
    }
}
