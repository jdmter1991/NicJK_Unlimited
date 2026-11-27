# Repository administration through the GitHub REST API, using the credential Git already has for
# github.com (Git Credential Manager). The token is never printed or stored.
#   gh_admin.ps1 -Repo owner/name -Info
#   gh_admin.ps1 -Repo owner/name -RenameBranch old -To new
#   gh_admin.ps1 -Repo owner/name -DefaultBranch name
#   gh_admin.ps1 -Repo owner/name -RenameRepo newname
#   gh_admin.ps1 -Repo owner/name -EnableActions
#   gh_admin.ps1 -Repo owner/name -Runs            (latest workflow runs)
#   gh_admin.ps1 -Repo owner/name -Branches        (every branch with its last commit date)
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [switch]$Info,
    [string]$RenameBranch,
    [string]$To,
    [string]$DefaultBranch,
    [string]$RenameRepo,
    [switch]$EnableActions,
    [switch]$Runs,
    [switch]$Branches,
    [string]$Jobs
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$credIn = Join-Path $env:TEMP "gitcred_query.txt"
[IO.File]::WriteAllText($credIn, "protocol=https`nhost=github.com`n`n", (New-Object System.Text.ASCIIEncoding))
$cred = cmd /c "git credential fill < `"$credIn`""
$token = ($cred | Where-Object { $_ -like "password=*" }) -replace "^password=", ""
if (-not $token) { throw "Git has no stored credential for github.com" }
$headers = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28"; "User-Agent" = "admin-script" }
$api = "https://api.github.com/repos/$Repo"
function Send($method, $uri, $obj) {
    $json = $obj | ConvertTo-Json
    Invoke-RestMethod -Method $method -Headers $headers -Uri $uri -Body ([Text.Encoding]::UTF8.GetBytes($json)) -ContentType "application/json"
}
if ($Info) {
    $r = Invoke-RestMethod -Headers $headers -Uri $api
    "repo: $($r.full_name)  default branch: $($r.default_branch)  private: $($r.private)  fork: $($r.fork)  parent: $($r.parent.full_name)  admin: $($r.permissions.admin)"
    try { $a = Invoke-RestMethod -Headers $headers -Uri "$api/actions/permissions"; "actions enabled: $($a.enabled)  allowed: $($a.allowed_actions)" } catch { "actions permissions: $($_.Exception.Message)" }
    try { $w = Invoke-RestMethod -Headers $headers -Uri "$api/actions/workflows"; foreach ($x in $w.workflows) { "workflow: $($x.name) [$($x.path)] state=$($x.state)" } } catch { "workflows: $($_.Exception.Message)" }
}
if ($RenameBranch) { $b = Send Post "$api/branches/$RenameBranch/rename" @{ new_name = $To }; "branch renamed: $($b.name)" }
if ($DefaultBranch) { $r = Send Patch $api @{ default_branch = $DefaultBranch }; "default branch: $($r.default_branch)" }
if ($RenameRepo) { $r = Send Patch $api @{ name = $RenameRepo }; "repo renamed: $($r.full_name)  $($r.html_url)" }
if ($EnableActions) {
    Send Put "$api/actions/permissions" @{ enabled = $true; allowed_actions = "all" } | Out-Null
    $w = Invoke-RestMethod -Headers $headers -Uri "$api/actions/workflows"
    foreach ($x in $w.workflows) { if ($x.state -ne "active") { try { Invoke-RestMethod -Method Put -Headers $headers -Uri "$api/actions/workflows/$($x.id)/enable" | Out-Null; "enabled workflow $($x.name)" } catch { "could not enable $($x.name): $($_.Exception.Message)" } } }
    "actions enabled"
}
if ($Runs) {
    $r = Invoke-RestMethod -Headers $headers -Uri "$api/actions/runs?per_page=8"
    foreach ($x in $r.workflow_runs) { "run $($x.id): $($x.name) [$($x.event)] branch=$($x.head_branch) status=$($x.status) conclusion=$($x.conclusion) $($x.created_at)" }
}
if ($Jobs) {
    $r = Invoke-RestMethod -Headers $headers -Uri "$api/actions/runs/$Jobs/jobs?per_page=60"
    foreach ($x in $r.jobs) { "job $($x.id): $($x.name) status=$($x.status) conclusion=$($x.conclusion)"; foreach ($s in $x.steps) { if ($s.conclusion -eq "failure") { "    failed step: $($s.name)" } } }
}
if ($Branches) {
    $page = 1
    do {
        $bs = Invoke-RestMethod -Headers $headers -Uri "$api/branches?per_page=100&page=$page"
        foreach ($b in $bs) {
            $c = Invoke-RestMethod -Headers $headers -Uri "$api/commits/$($b.commit.sha)"
            "{0}`t{1}`t{2}`t{3}" -f $b.name, $c.commit.committer.date.Substring(0, 10), $b.commit.sha.Substring(0, 9), ($c.commit.message -split "`n")[0]
        }
        $page++
    } while ($bs.Count -eq 100)
}
if ($env:GH_JOBLOG) {
    $out = Join-Path $env:TEMP "gh_joblog_$($env:GH_JOBLOG).txt"
    Invoke-WebRequest -Headers $headers -Uri "$api/actions/jobs/$($env:GH_JOBLOG)/logs" -OutFile $out -UseBasicParsing
    "log saved: $out"
}
