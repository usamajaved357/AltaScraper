# PreToolUse hook (Edit | Write | MultiEdit | NotebookEdit | PowerShell | Bash).
# The governance layer -- CLAUDE.md, .claude/settings*.json, .claude/hooks/,
# .claude/agents/, .claude/skills/ -- may change only with the owner's
# confirmation (CLAUDE.md Rule 18). This hook turns any edit of those files
# into an ASK, so the owner sees and approves it; after he approves, the edit
# goes through normally, which keeps the system maintainable.
#
# Reading them is never blocked. For shell commands, a command that names a
# governance file AND looks like a write (Set-Content, Out-File, >, Remove-Item,
# git checkout/restore, a Python open(..., 'w'), ...) is asked about.
# Limit: a shell command that changes these files WITHOUT naming them (e.g.
# `git checkout .`) is not recognised.
#
# FAIL SAFE: if the check cannot complete, the call gets an ASK. Output: nothing
# (allow) or a JSON decision; exit code always 0 (see _hooklib.ps1).

$ErrorActionPreference = "Stop"

$Gov = '(?i)((^|[\\/\s"''=(])CLAUDE\.md(?![\w.-])|\.claude[\\/](settings(\.local)?\.json|hooks([\\/]|\b)|agents([\\/]|\b)|skills([\\/]|\b)))'
$WriteHint = '(?i)(\b(Set-Content|Add-Content|Out-File|Clear-Content|Remove-Item|Move-Item|Rename-Item|Copy-Item|New-Item|Tee-Object|del|erase|rm|rmdir|mv|cp|move|copy|ren|ni|sc|ac|tee|sed|truncate)\b|WriteAll|AppendAll|\.Delete\(|\.MoveTo\(|\.CopyTo\(|\b(checkout|restore|reset|stash|clean|apply)\b|open\([^)]*[''"][wax+]b?[''"]|(^|[^\d&])>>?(?!\s*\$null)|\|\s*(Set-Content|Out-File|Add-Content|tee))'

try {
    . (Join-Path $PSScriptRoot "_hooklib.ps1")
    $j = Read-HookInput
    Invoke-HookSelfTest "guard_rules"
    Assert-HookBudget
    $tool = [string]$j.tool_name
    $ti = $j.tool_input
    $target = $null
    $isEdit = $false

    if ($tool -in @("PowerShell", "Bash")) {
        $cmd = [string]$ti.command
        if ($cmd -and $cmd -match $Gov -and $cmd -match $WriteHint) { $target = "a governance file named in this shell command" }
    } else {
        foreach ($k in @("file_path", "notebook_path")) {
            if ($ti.PSObject.Properties.Name -contains $k) {
                $v = [string]$ti.$k
                if ($v -and (" " + $v) -match $Gov) { $target = $v; $isEdit = $true }
            }
        }
    }
    Assert-HookBudget
    if (-not $target) { exit 0 }

    Write-AskOrDeny $j -edits:$isEdit ("GOVERNANCE CHANGE: this edits " + $target + ". CLAUDE.md, .claude/settings, hooks, " +
        "agents and skills change only with the owner's confirmation (CLAUDE.md Rule 18). Before approving, the owner " +
        "should have been shown what changes and why.")
    exit 0
}
catch {
    $why = [string]$_.Exception.Message
    $msg = "guard_rules could not complete its check (" + $why + "). This call might change a governance file, so the owner must confirm it."
    try {
        if ($null -eq $j) { Write-PreToolDecision "deny" ($msg + " [Denied: the hook input could not be read, so it is unknown whether a prompt would be shown.]") }
        else { Write-AskOrDeny $j $msg -edits }
    } catch {
        [Console]::Out.Write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"guard_rules failed; owner must confirm this call."}}')
    }
    exit 0
}
