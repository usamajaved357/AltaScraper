# PreToolUse hook (PowerShell | Bash).
# Every `git push` asks the owner first. A push to main is the production deploy
# (Render builds origin/main), so it gets a louder warning (CLAUDE.md Rule 2).
#
# A permission rule alone cannot catch this: git is not on PATH here and is
# called as `& $g push ...`, which a "git push*" pattern never matches.
#
# FAIL SAFE: if this check cannot complete (bad input, any crash, out of time)
# the command gets an ASK. Output: nothing (not a push) or a JSON decision; the
# exit code is always 0 (see _hooklib.ps1).

$ErrorActionPreference = "Stop"

try {
    . (Join-Path $PSScriptRoot "_hooklib.ps1")
    $j = Read-HookInput
    Invoke-HookSelfTest "guard_push"
    Assert-HookBudget
    $cmd = [string]$j.tool_input.command
    if (-not $cmd) { exit 0 }
    if (-not (Test-GitCommand $cmd "push")) { exit 0 }
    Assert-HookBudget

    $toMain = $cmd -match '(?i)(:main\b|:refs/heads/main\b|\spush\b[^;|]*\smain(\s|$|;)|\s--all\b|\s--mirror\b)'
    $force = $cmd -match '(?i)\s(--force|--force-with-lease|-f)(\s|$|=)'

    if ($toMain) {
        $reason = "PRODUCTION DEPLOY: this pushes to main, and Render deploys origin/main within about a minute. " +
                  "Allow only if the owner explicitly said to merge/deploy in this conversation. " +
                  "Say that Rule 2's production-confirmation wait is being waived on his instruction."
    } else {
        $reason = "git push: allowed only on the owner's explicit instruction (CLAUDE.md Rule 2). " +
                  "Pushing a branch does not deploy; pushing to main does."
    }
    if ($force) { $reason = "FORCE PUSH. " + $reason }
    Write-AskOrDeny $j $reason
    exit 0
}
catch {
    $why = [string]$_.Exception.Message
    $msg = "guard_push could not complete its check (" + $why + "). This command might be a git push, so the owner must confirm it."
    try {
        # Input never parsed: the permission mode is unknown, and an ask may be
        # ignored in bypass mode, so deny. Parsed: ask, or deny where no prompt shows.
        if ($null -eq $j) { Write-PreToolDecision "deny" ($msg + " [Denied: the hook input could not be read, so it is unknown whether a prompt would be shown.]") }
        else { Write-AskOrDeny $j $msg }
    } catch {
        [Console]::Out.Write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"guard_push failed; owner must confirm this command."}}')
    }
    exit 0
}
