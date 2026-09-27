# PreToolUse hook (PowerShell | Bash).
# Every `git push` asks the owner first. A push to main is the production deploy
# (Render builds origin/main), so it gets a louder warning (CLAUDE.md Rule 2).
#
# A permission rule alone cannot catch this: git is not on PATH here and is
# called as `& $g push ...`, which a "git push*" pattern never matches. A hook
# also runs in every permission mode.
#
# Output: nothing (not a push) or a PreToolUse "ask" decision with the reason.

$ErrorActionPreference = "Stop"

try {
    $j = [Console]::In.ReadToEnd() | ConvertFrom-Json
} catch { exit 0 }
$cmd = [string]$j.tool_input.command
if (-not $cmd) { exit 0 }
if ($cmd -notmatch '(?i)(^|[\s;&|])push(\s|$)') { exit 0 }
# git is usually called through a variable holding git.exe (`& $g push ...`),
# so a command counts as git if it names git OR invokes a variable before push.
$viaVar = $cmd -match '(?i)&\s*\$[\w:]+\s+(-C\s+("[^"]*"|''[^'']*''|\S+)\s+)?push\b'
if (-not ($cmd -match '(?i)git' -or $viaVar)) { exit 0 }

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

$out = @{ hookSpecificOutput = @{ hookEventName = "PreToolUse"; permissionDecision = "ask"; permissionDecisionReason = $reason } }
[Console]::Out.Write(($out | ConvertTo-Json -Depth 5 -Compress))
exit 0
