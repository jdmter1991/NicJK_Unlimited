# Create a GitHub release and upload assets through the REST API, using the credential Git
# already has for github.com (Git Credential Manager). The token is never printed or stored.
#   gh_release.ps1 -Repo owner/name -Check
#   gh_release.ps1 -Repo owner/name -Tag v1 -Target <branch or sha> -Name "..." -BodyFile notes.md -Assets a.zip[,b.zip] [-Latest]
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [switch]$Check,
    [string]$Tag,
    [string]$Target,
    [string]$Name,
    [string]$BodyFile,
    [string[]]$Assets = @(),
    [switch]$Latest
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$credIn = Join-Path $env:TEMP "gitcred_query.txt"
[IO.File]::WriteAllText($credIn, "protocol=https`nhost=github.com`n`n", (New-Object System.Text.ASCIIEncoding))
$cred = cmd /c "git credential fill < `"$credIn`""
$token = ($cred | Where-Object { $_ -like "password=*" }) -replace "^password=", ""
if (-not $token) { throw "Git has no stored credential for github.com" }
$headers = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28"; "User-Agent" = "release-script" }

if ($Check) {
    $me = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/$Repo"
    "repo: $($me.full_name)  can push: $($me.permissions.push)  private: $($me.private)"
    $rels = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/$Repo/releases?per_page=5"
    foreach ($r in $rels) { "release: tag=$($r.tag_name) name=$($r.name) prerelease=$($r.prerelease) published=$($r.published_at) assets=$($r.assets.Count)" }
    try { $l = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/$Repo/releases/latest"; "current latest: $($l.tag_name)" } catch { "current latest: none" }
    return
}

$body = if ($BodyFile) { [string][IO.File]::ReadAllText($BodyFile, [Text.Encoding]::UTF8) } else { "" }
$payload = @{ tag_name = $Tag; target_commitish = $Target; name = $Name; body = $body; draft = $false; prerelease = $false; make_latest = $(if ($Latest) { "true" } else { "false" }) } | ConvertTo-Json
$rel = Invoke-RestMethod -Method Post -Headers $headers -Uri "https://api.github.com/repos/$Repo/releases" -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType "application/json"
"created release $($rel.tag_name): $($rel.html_url)"
$uploadBase = $rel.upload_url -replace "\{.*$", ""
foreach ($a in $Assets) {
    $fn = [IO.Path]::GetFileName($a)
    $up = Invoke-RestMethod -Method Post -Headers $headers -Uri "$uploadBase`?name=$([uri]::EscapeDataString($fn))" -InFile $a -ContentType "application/zip" -TimeoutSec 1800
    "uploaded $($up.name) ($([math]::Round($up.size / 1MB, 1)) MB): $($up.browser_download_url)"
}



