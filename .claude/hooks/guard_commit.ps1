# PreToolUse hook (PowerShell | Bash).
# Before any `git add` or `git commit`, refuses if a secret-bearing file would be
# staged or committed. The list is CLAUDE.md Rule 2 "Never commit".
#
# It deliberately does NOT block every file whose name contains "key" or
# "token": this repo tracks real source files such as auth/token_crypto.py,
# routes/keywords_routes.py and _tokens.css. Those words block only NON-source
# files (a .json, .txt, a file with no extension, ...), where a key would live.
#
# Output: nothing (allow) or a PreToolUse "deny" decision with the reason.

$ErrorActionPreference = "Stop"

function Get-GitExe {
    $c = Get-Command git -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $base = Join-Path $env:LOCALAPPDATA "GitHubDesktop"
    if (-not (Test-Path $base)) { return $null }
    $d = Get-ChildItem $base -Directory -Filter "app-*" -ErrorAction SilentlyContinue |
        Sort-Object { try { [version]($_.Name -replace '^app-', '') } catch { [version]"0.0" } } -Descending |
        Select-Object -First 1
    if (-not $d) { return $null }
    $p = Join-Path $d.FullName "resources\app\git\cmd\git.exe"
    if (Test-Path $p) { return $p }
    return $null
}

function Test-Sensitive([string]$p) {
    $n = ($p -replace '\\', '/').Trim('"')
    if ($n -match '(^|/)__pycache__/') { return $true }
    $leaf = ($n -split '/')[-1].ToLower()
    $ext = [IO.Path]::GetExtension($leaf)
    $exact = @("config.json", "service_account.json", "users.json", "app_state.json",
               "miles_bundles_store.json", "miles_bundles.json", "image_url_key", ".env")
    if ($exact -contains $leaf) { return $true }
    if ($leaf.StartsWith("config.json") -or $leaf.StartsWith(".env")) { return $true }
    if (@(".db", ".db-wal", ".db-shm", ".pem", ".key", ".p12", ".pfx", ".pyc") -contains $ext) { return $true }
    if ($leaf -match 'secret|credential') { return $true }
    $source = @(".py", ".js", ".css", ".html", ".md", ".jsx", ".ts", ".ps1", ".bat", ".command")
    if ($leaf -match 'key|token' -and -not ($source -contains $ext)) { return $true }
    return $false
}

try {
    $j = [Console]::In.ReadToEnd() | ConvertFrom-Json
} catch { exit 0 }
$cmd = [string]$j.tool_input.command
if (-not $cmd) { exit 0 }

# Only git add / git commit. git is usually called through a variable
# (`& $g commit ...`) because it is not on PATH, so look for the verb anywhere
# in a command that mentions git.
$isCommit = $cmd -match '(?i)(^|[\s;&|])commit(\s|$)'
$isAdd = $cmd -match '(?i)(^|[\s;&|])add(\s|$)'
if (-not ($isCommit -or $isAdd)) { exit 0 }
$viaVar = $cmd -match '(?i)&\s*\$[\w:]+\s+(-C\s+("[^"]*"|''[^'']*''|\S+)\s+)?(add|commit)\b'
if (-not ($cmd -match '(?i)git' -or $viaVar)) { exit 0 }

$git = Get-GitExe
if (-not $git) { exit 0 }

$repo = [string]$j.cwd
if ($cmd -match '(?i)\s-C\s+"([^"]+)"') { $repo = $Matches[1] }
elseif ($cmd -match "(?i)\s-C\s+'([^']+)'") { $repo = $Matches[1] }
elseif ($cmd -match '(?i)\s-C\s+(\S+)') { $repo = $Matches[1] }
if (-not $repo -or -not (Test-Path -LiteralPath $repo)) { exit 0 }

$staged = @(& $git -C $repo diff --cached --name-only 2>$null)
$status = @(& $git -C $repo status --porcelain --untracked-files=all 2>$null) |
    ForEach-Object { if ($_.Length -gt 3) { ($_.Substring(3) -split ' -> ')[-1].Trim('"') } }

$candidates = New-Object System.Collections.Generic.List[string]
foreach ($s in $staged) { if ($s) { $candidates.Add($s) } }

$broad = $cmd -match '(?i)\badd\b[^;|]*(\s-A\b|\s--all\b|\s\.(\s|$|;)|\s-u\b|\s--update\b)' -or
         $cmd -match '(?i)\bcommit\b[^;|]*\s-(a|am|-all)\b'
foreach ($s in $status) {
    if (-not $s) { continue }
    if (-not (Test-Sensitive $s)) { continue }
    $leaf = (($s -replace '\\', '/') -split '/')[-1]
    if ($broad -or $cmd.Contains($leaf)) { $candidates.Add($s) }
}

$hits = @($candidates | Where-Object { Test-Sensitive $_ } | Sort-Object -Unique)
if ($hits.Count -eq 0) { exit 0 }

$reason = "BLOCKED by guard_commit: these files must never be committed (CLAUDE.md Rule 2): " +
          ($hits -join ", ") +
          ". Unstage them (git restore --staged <file>) and make sure .gitignore covers them. " +
          "If one is really source code, tell the owner and ask before changing the rule."
$out = @{ hookSpecificOutput = @{ hookEventName = "PreToolUse"; permissionDecision = "deny"; permissionDecisionReason = $reason } }
[Console]::Out.Write(($out | ConvertTo-Json -Depth 5 -Compress))
exit 0
