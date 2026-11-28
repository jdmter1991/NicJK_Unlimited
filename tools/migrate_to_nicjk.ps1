# Switches a Jedi Academy GameData folder from the TaystJK names to the NicJK names and installs
# a NicJK build into it. Nothing is deleted: the old programs and every file that gets edited are
# first put in a backup folder, and the mod folder is renamed, not copied.
#   migrate_to_nicjk.ps1 -GameData <...\GameData> -Stage <...\JediAcademy from cmake --install> -Backup <folder> [-WhatIf]
param(
    [Parameter(Mandatory = $true)][string]$GameData,
    [Parameter(Mandatory = $true)][string]$Stage,
    [Parameter(Mandatory = $true)][string]$Backup,
    [switch]$WhatIf
)
$ErrorActionPreference = "Stop"
function Say($m) { if ($WhatIf) { "WOULD: $m" } else { $m } }
$old = Join-Path $GameData "taystjk"
$new = Join-Path $GameData "nicjk"
if (-not (Test-Path -LiteralPath $old)) { throw "no taystjk folder in $GameData" }
if (Test-Path -LiteralPath $new) { throw "a nicjk folder already exists in $GameData" }
if (Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($GameData, [StringComparison]::OrdinalIgnoreCase) }) { throw "a program from $GameData is running" }
if (-not $WhatIf) { New-Item -ItemType Directory -Force (Join-Path $Backup "base"), (Join-Path $Backup "taystjk") | Out-Null }

# 1. old programs out of the way (kept in the backup)
foreach ($f in Get-ChildItem -LiteralPath $GameData -File | Where-Object { $_.Name -match '^(taystjk|taystjkded)\.x86(_64)?\.(exe|pdb)$|^rd-taystjk_.*\.(dll|pdb)$' }) {
    Say "move old program $($f.Name) to the backup"
    if (-not $WhatIf) { Move-Item -LiteralPath $f.FullName -Destination (Join-Path $Backup $f.Name) -Force }
}
# 2. launch files: new name, new program, new mod folder
foreach ($f in Get-ChildItem -LiteralPath $GameData -File -Filter "*.bat" | Where-Object { $_.Name -match 'taystjk' -or (Get-Content -LiteralPath $_.FullName -Raw) -match 'taystjk' }) {
    $nn = $f.Name -replace 'taystjkded', 'nicjkded' -replace 'taystjk', 'nicjk'
    Say "launch file $($f.Name) -> $nn"
    if (-not $WhatIf) {
        Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $Backup $f.Name) -Force
        $t = (Get-Content -LiteralPath $f.FullName -Raw) -replace 'taystjkded', 'nicjkded' -replace 'taystjk', 'nicjk'
        [IO.File]::WriteAllText((Join-Path $GameData $nn), $t, (New-Object System.Text.ASCIIEncoding))
        if ($nn -ne $f.Name) { Remove-Item -LiteralPath $f.FullName -Force }
    }
}
# 3. server configs in base that carry the old name (server names)
foreach ($f in Get-ChildItem -LiteralPath (Join-Path $GameData "base") -File -Filter "*.cfg") {
    $raw = [IO.File]::ReadAllText($f.FullName, [Text.Encoding]::GetEncoding(1252))
    if (($raw -match 'TaystJK') -and $f.IsReadOnly) {
        "LEFT ALONE (read-only): base\$($f.Name) still says TaystJK"
    } elseif ($raw -match 'TaystJK') {
        Say "server config base\$($f.Name): name changed to NicJK Unlimited"
        if (-not $WhatIf) {
            Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $Backup "base\$($f.Name)") -Force
            $raw = $raw -creplace 'TaystJK', 'NicJK Unlimited' -creplace 'taystjkded', 'nicjkded' -creplace 'taystjk', 'nicjk'
            [IO.File]::WriteAllText($f.FullName, $raw, [Text.Encoding]::GetEncoding(1252))
        }
    }
}
# 4. the mod folder and the settings files in it
foreach ($n in "taystjk.cfg", "taystjk_server.cfg") {
    $p = Join-Path $old $n
    if (Test-Path -LiteralPath $p) { if (-not $WhatIf) { Copy-Item -LiteralPath $p -Destination (Join-Path $Backup "taystjk\$n") -Force } }
}
foreach ($n in "cgamex86_64.dll", "jampgamex86_64.dll", "uix86_64.dll") {
    $p = Join-Path $old $n
    if (Test-Path -LiteralPath $p) { Say "keep old game module taystjk\$n in the backup"; if (-not $WhatIf) { Copy-Item -LiteralPath $p -Destination (Join-Path $Backup "taystjk\$n") -Force } }
}
Say "rename folder taystjk -> nicjk"
if (-not $WhatIf) { Rename-Item -LiteralPath $old -NewName "nicjk" }
foreach ($pair in @(@("taystjk.cfg", "nicjk.cfg"), @("taystjk_server.cfg", "nicjk_server.cfg"))) {
    $p = Join-Path $(if ($WhatIf) { $old } else { $new }) $pair[0]
    if (Test-Path -LiteralPath $p) {
        Say "settings $($pair[0]) -> $($pair[1])"
        if (-not $WhatIf) {
            $raw = [IO.File]::ReadAllText($p, [Text.Encoding]::GetEncoding(1252))
            # the saved renderer name of the old OpenGL renderer, and the server name
            $raw = $raw -creplace '"rd-taystjk"', '"rd-nicjk"' -creplace '(seta sv_hostname ".*)TaystJK', '$1NicJK Unlimited'
            [IO.File]::WriteAllText((Join-Path $new $pair[1]), $raw, [Text.Encoding]::GetEncoding(1252))
            Remove-Item -LiteralPath $p -Force
        }
    }
}
# 5. the new build
foreach ($f in Get-ChildItem -LiteralPath $Stage -File) {
    Say "install $($f.Name)"
    if (-not $WhatIf) {
        $dst = Join-Path $GameData $f.Name
        if ((Test-Path -LiteralPath $dst) -and -not (Test-Path -LiteralPath (Join-Path $Backup $f.Name))) { Copy-Item -LiteralPath $dst -Destination (Join-Path $Backup $f.Name) -Force }
        Copy-Item -LiteralPath $f.FullName -Destination $dst -Force
    }
}
foreach ($f in Get-ChildItem -LiteralPath (Join-Path $Stage "nicjk") -File) {
    Say "install nicjk\$($f.Name)"
    if (-not $WhatIf) {
        $dst = Join-Path $new $f.Name
        if ((Test-Path -LiteralPath $dst) -and -not (Test-Path -LiteralPath (Join-Path $Backup "taystjk\$($f.Name)"))) { Copy-Item -LiteralPath $dst -Destination (Join-Path $Backup "taystjk\$($f.Name)") -Force }
        Copy-Item -LiteralPath $f.FullName -Destination $dst -Force
    }
}
Say "done: $GameData"
