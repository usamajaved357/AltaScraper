# PreToolUse hook (PowerShell | Bash).
# Before any `git add` or `git commit`, refuses if a secret-bearing file would be
# staged or committed. The list is CLAUDE.md Rule 2 "Never commit".
#
# It does NOT block every file whose name contains "key" or "token": the repo
# tracks real source files such as auth/token_crypto.py, routes/keywords_routes.py
# and _tokens.css. Those words block only NON-source files (a .json, .txt, a file
# with no extension, ...), where a key would live.
#
# FAIL SAFE: if this check cannot complete (bad input, missing git, a git error,
# out of time, any crash) the command is DENIED. Output: nothing (allow) or a
# JSON PreToolUse decision; the exit code is always 0 (see _hooklib.ps1).

$ErrorActionPreference = "Stop"

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
    # "secret", "credential", "key", "token" in a NON-source file's name: a
    # source file (e.g. .claude/hooks/guard_secrets.ps1, auth/token_crypto.py)
    # is code, not a secret.
    $source = @(".py", ".js", ".css", ".html", ".md", ".jsx", ".ts", ".ps1", ".bat", ".command")
    if ($leaf -match 'secret|credential|key|token' -and -not ($source -contains $ext)) { return $true }
    return $false
}

try {
    . (Join-Path $PSScriptRoot "_hooklib.ps1")
    $j = Read-HookInput
    Invoke-HookSelfTest "guard_commit"
    Assert-HookBudget
    $cmd = [string]$j.tool_input.command
    if (-not $cmd) { exit 0 }

    $isCommit = Test-GitCommand $cmd "commit"
    $isAdd = Test-GitCommand $cmd "add"
    if (-not ($isCommit -or $isAdd)) { exit 0 }

    $git = Get-GitExe
    if (-not $git) { throw "git.exe not found" }

    $repo = [string]$j.cwd
    if ($cmd -match '(?i)\s-C\s+"([^"]+)"') { $repo = $Matches[1] }
    elseif ($cmd -match "(?i)\s-C\s+'([^']+)'") { $repo = $Matches[1] }
    elseif ($cmd -match '(?i)\s-C\s+(\S+)') { $repo = $Matches[1] }
    if (-not $repo) { $repo = (Get-Location).Path }
    if (-not [IO.Path]::IsPathRooted($repo) -and $j.cwd) { $repo = Join-Path ([string]$j.cwd) $repo }
    if (-not (Test-Path -LiteralPath $repo)) { throw "repository path not found: $repo" }

    $staged = Invoke-GitChecked $git @("-C", $repo, "diff", "--cached", "--name-only")
    $status = Invoke-GitChecked $git @("-C", $repo, "status", "--porcelain", "--untracked-files=all") |
        ForEach-Object { if ($_.Length -gt 3) { ($_.Substring(3) -split ' -> ')[-1].Trim('"') } }
    Assert-HookBudget

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

    Write-PreToolDecision "deny" ("BLOCKED by guard_commit: these files must never be committed (CLAUDE.md Rule 2): " +
        ($hits -join ", ") + ". Unstage them (git restore --staged <file>) and make sure .gitignore covers them. " +
        "If one is really source code, tell the owner and ask before changing the rule.")
    exit 0
}
catch {
    $why = [string]$_.Exception.Message
    try {
        Write-PreToolDecision "deny" ("guard_commit could not complete its safety check (" + $why +
            "), so this shell command is DENIED to be safe. Tell the owner; do not work around the guard.")
    } catch {
        [Console]::Out.Write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard_commit failed; command denied to be safe."}}')
    }
    exit 0
}
