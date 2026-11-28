# The bot characters used by every test script, in order.
# They come from the user's own list (the active addbot lines of bots_mixed.cfg); when a test needs
# more bots than the list has, the extra names below are appended. If the file cannot be read the
# extras alone are used.
#   . tools\bot_names.ps1 ;  $names = Get-BotNames
function Get-BotNames {
    param([string]$Cfg = "B:\SteamLibrary\steamapps\common\Jedi Academy\GameData\base\bots_mixed.cfg")
    $extra = @("Cultist", "Jedi Temple Guard", "Grand Master Luke Skywalker", "Reborn", "Jedi Zora",
        "Kyle", "Vaylin", "Arcann", "Valkorion")
    $names = @()
    if (Test-Path -LiteralPath $Cfg) {
        foreach ($line in Get-Content -LiteralPath $Cfg) {
            if ($line -match '^\s*addbot\s+"([^"]+)"') { $names += $Matches[1] }
        }
    }
    foreach ($e in $extra) { if ($names -notcontains $e) { $names += $e } }
    return , $names
}

# addbot lines for $Bots bots. With -Cycle N the first N characters are repeated, so the two groups
# of an A/B test (bot_abTest N) hold the same characters in the same order.
function Get-BotLines {
    param([int]$Bots, [int]$Cycle = 0, [int]$Skill = 5)
    $names = Get-BotNames
    $n = if ($Cycle -gt 0) { [Math]::Min($Cycle, $names.Count) } else { $names.Count }
    for ($i = 0; $i -lt $Bots; $i++) { 'addbot "{0}" {1}' -f $names[$i % $n], $Skill }
}
