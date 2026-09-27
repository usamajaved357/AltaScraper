# PreToolUse hook (PowerShell | Bash | Read | Grep | Glob | Edit | Write |
# MultiEdit | NotebookEdit).
# Denies any tool call that names a secret-bearing file. The permission deny
# rules in settings.json stop the Read/Edit tools and simple cmdlets; this hook
# also catches the indirect routes they miss, e.g.
#   [IO.File]::ReadAllText('...config.json')   python -c "open('config.json')"
#   Copy-Item config.json x.txt                  sqlite3 altascraper.db
# It matches file NAMES in the command text. It never opens the files, so it
# cannot leak their contents. It is a name check, so a deliberately disguised
# name (built from pieces at run time) is not caught.
#
# Legitimate source files are not blocked for containing "token" or "key"
# (auth/token_crypto.py, routes/keywords_routes.py, _tokens.css).
#
# FAIL SAFE: if the check cannot complete, the call is DENIED. Output: nothing
# (allow) or a JSON decision; exit code always 0 (see _hooklib.ps1).

$ErrorActionPreference = "Stop"

# Protected names as they appear inside a command or path. Left boundary: not
# preceded by a name character or a dot (so process.env / os.environ / data.db
# module paths do not match); right boundary: not followed by a name character.
$L = '(?<![\w.$-])'
$R = '(?![\w-])'
$Patterns = @(
    "${L}config\.json(\.[\w-]+)*$R",
    "${L}service_account\.json$R",
    "${L}\.env(\.[\w-]+)?$R",
    "${L}users\.json$R",
    "${L}app_state\.json$R",
    "${L}miles_bundles[\w-]*\.json$R",
    "${L}image_url_key$R",
    "(?<![\w-])[\w-]+\.(db|db-wal|db-shm|pem|p12|pfx)(?![\w.-])",
    "(?i)[\w./\\-]*(secret|credential)[\w./\\-]*"
)

# "secret" / "credential" in a SOURCE file's name (this very hook,
# guard_secrets.ps1, for one) is code, not a secret; the rule is for data files.
$SourceExt = @(".py", ".js", ".ps1", ".md", ".css", ".html", ".jsx", ".ts", ".bat", ".command")

function Find-Protected([string]$text) {
    if (-not $text) { return $null }
    foreach ($p in $Patterns) {
        foreach ($m in [regex]::Matches($text, $p, 'IgnoreCase')) {
            $hit = $m.Value
            if ($hit -match '(?i)secret|credential') {
                $leaf = ($hit -split '[\\/]')[-1]
                if ($SourceExt -contains [IO.Path]::GetExtension($leaf).ToLower()) { continue }
            }
            # `import data.db` / `from data.db import ...` is the Python module, not a file.
            if ($hit -ieq "data.db") {
                $before = $text.Substring(0, $m.Index)
                if ($before -match '(?i)(import|from)\s+$') { continue }
            }
            return $hit
        }
    }
    return $null
}

try {
    . (Join-Path $PSScriptRoot "_hooklib.ps1")
    $j = Read-HookInput
    Invoke-HookSelfTest "guard_secrets"
    Assert-HookBudget
    $tool = [string]$j.tool_name
    $ti = $j.tool_input
    $texts = @()
    if ($tool -in @("PowerShell", "Bash")) {
        $texts += [string]$ti.command
    } else {
        foreach ($k in @("file_path", "path", "notebook_path", "pattern", "glob")) {
            if ($ti.PSObject.Properties.Name -contains $k) {
                $v = [string]$ti.$k
                # a Grep regex pattern is search text, not a file name
                if ($tool -eq "Grep" -and $k -eq "pattern") { continue }
                if ($v) { $texts += $v }
            }
        }
    }
    Assert-HookBudget
    foreach ($t in $texts) {
        $hit = Find-Protected $t
        if ($hit) {
            $name = ($hit -split '[\\/]')[-1]
            Write-PreToolDecision "deny" ("BLOCKED by guard_secrets: this $tool call refers to '" + $name +
                "', a protected secret-bearing file (CLAUDE.md Rule 2 / docs/security.md). Claude must not read, copy, " +
                "search, print or modify it by any route. If something from it is really needed, ask the owner to look himself.")
            exit 0
        }
    }
    exit 0
}
catch {
    $why = [string]$_.Exception.Message
    try {
        Write-PreToolDecision "deny" ("guard_secrets could not complete its check (" + $why +
            "), so this call is DENIED to be safe. Tell the owner; do not work around the guard.")
    } catch {
        [Console]::Out.Write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard_secrets failed; call denied to be safe."}}')
    }
    exit 0
}
