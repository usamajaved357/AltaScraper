# Shared helpers for the AltaScraper Claude Code hooks (not a hook itself).
#
# Every guard dot-sources this file INSIDE its try block, so a broken or missing
# helper makes the guard fail SAFE (deny / ask), never open.
#
# Why decisions are written as JSON on stdout and the exit code is always 0:
# Claude Code on this machine runs hook commands through PowerShell, which turns
# a child's exit code 2 into 1 -- and 1 is a "non-blocking" error that Claude
# never sees (measured 27 Sep 2026). A JSON decision arrives intact.

$script:HookClock = [Diagnostics.Stopwatch]::StartNew()
# settings.json gives each hook 30 s; a guard gives up (and fails safe) well
# before Claude Code's own timeout, which would otherwise let the action through.
$script:HookBudgetMs = 10000

function Read-HookInput {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw -or -not $raw.Trim()) { throw "empty hook input" }
    return ($raw | ConvertFrom-Json)
}

# Test-only switch. ALTA_HOOK_TEST_FAIL=<hook>:crash or <hook>:slow makes that
# hook fail on purpose so its fail-safe path can be exercised in a real session.
# It can only make a guard stricter, never looser.
function Invoke-HookSelfTest([string]$name) {
    $v = [string]$env:ALTA_HOOK_TEST_FAIL
    if (-not $v) { return }
    if ($v -eq "${name}:crash") { throw "simulated failure (ALTA_HOOK_TEST_FAIL)" }
    if ($v -eq "${name}:slow") { Start-Sleep -Milliseconds ($script:HookBudgetMs + 500) }
}

function Assert-HookBudget {
    if ($script:HookClock.ElapsedMilliseconds -gt $script:HookBudgetMs) {
        throw "the safety check ran past its time budget"
    }
}

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

function ConvertTo-ArgString([string[]]$argv) {
    return ($argv | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join " "
}

# Runs git with what is left of the time budget. Throws on timeout or failure,
# so the caller's catch turns "could not check" into deny / ask.
function Invoke-GitChecked([string]$git, [string[]]$argv) {
    $left = [int]($script:HookBudgetMs - $script:HookClock.ElapsedMilliseconds)
    if ($left -le 0) { throw "no time left for git" }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $git
    $psi.Arguments = ConvertTo-ArgString $argv
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $errTask = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($left)) {
        try { $p.Kill() } catch {}
        throw "git timed out"
    }
    if ($p.ExitCode -ne 0) { throw ("git " + ($argv -join " ") + " failed: " + $errTask.Result.Trim()) }
    return @($outTask.Result -split "`r?`n" | Where-Object { $_ -ne "" })
}

function Write-PreToolDecision([string]$decision, [string]$reason) {
    $out = @{ hookSpecificOutput = @{ hookEventName = "PreToolUse"; permissionDecision = $decision; permissionDecisionReason = $reason } }
    [Console]::Out.Write(($out | ConvertTo-Json -Depth 5 -Compress))
}

# "ask" is only a stop when someone can be asked. Measured 27 Sep 2026: in
# bypassPermissions mode Claude Code received a hook's "ask" for a file write and
# wrote the file anyway. So where no prompt will be shown, an ask becomes a DENY:
# the owner does the action himself, or re-runs it in a normal-mode session where
# he is asked. $edits = the call edits a file (acceptEdits also skips prompts there).
function Write-AskOrDeny($j, [string]$reason, [switch]$edits) {
    $mode = ""
    try { $mode = [string]$j.permission_mode } catch {}
    $noPrompt = @("bypassPermissions", "dontAsk")
    if ($edits) { $noPrompt += "acceptEdits" }
    if ($noPrompt -contains $mode) {
        Write-PreToolDecision "deny" ($reason + " [Denied rather than asked: this session runs in '" + $mode +
            "' mode, where no confirmation prompt would be shown. The owner can do it himself or approve it in a normal-mode session.]")
    } else {
        Write-PreToolDecision "ask" $reason
    }
}

function Write-PostToolFeedback([string]$reason) {
    $out = @{ decision = "block"; reason = $reason;
              hookSpecificOutput = @{ hookEventName = "PostToolUse"; additionalContext = $reason } }
    [Console]::Out.Write(($out | ConvertTo-Json -Depth 5 -Compress))
}

# Does this shell command run git (directly, or through a variable holding
# git.exe as in `& $g add ...`, since git is not on PATH here)?
function Test-GitCommand([string]$cmd, [string]$verb) {
    if ($cmd -notmatch "(?i)(^|[\s;&|])$verb(\s|$)") { return $false }
    if ($cmd -match '(?i)git') { return $true }
    return ($cmd -match "(?i)&\s*\`$[\w:]+\s+(-C\s+(`"[^`"]*`"|'[^']*'|\S+)\s+)?$verb\b")
}
