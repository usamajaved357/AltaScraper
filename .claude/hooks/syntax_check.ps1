# PostToolUse hook (Edit | Write | MultiEdit).
# Compiles the ONE file that was just changed, so a syntax error is reported the
# moment it is made rather than at the end of a task (CLAUDE.md Rule 3).
#   .py -> Python compile() (same check as py_compile, but writes no .pyc)
#   .js -> node --check (parses only: it cannot catch runtime errors)
#
# The error reaches Claude as a JSON "block" decision on stdout. An exit code 2
# would be turned into 1 by the PowerShell that runs hooks here, and Claude
# would never see it (see _hooklib.ps1). Always exits 0.

$ErrorActionPreference = "Stop"

function Invoke-Native([string]$exe, [string[]]$argv) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    # Quote only arguments that need it: the py launcher does not recognise a
    # quoted "-3.11" as its version switch and falls through to another Python.
    $psi.Arguments = ($argv | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join " "
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $o = $p.StandardOutput.ReadToEndAsync(); $e = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit(20000)) { try { $p.Kill() } catch {}; return @{ code = -1; out = "timed out" } }
    return @{ code = $p.ExitCode; out = ($o.Result + $e.Result) }
}

try {
    . (Join-Path $PSScriptRoot "_hooklib.ps1")
    $j = Read-HookInput
} catch { exit 0 }   # nothing to check; a syntax check failing open is harmless

$path = $null
if ($j.tool_input -and $j.tool_input.file_path) { $path = [string]$j.tool_input.file_path }
if (-not $path) { exit 0 }
if (-not [IO.Path]::IsPathRooted($path) -and $j.cwd) { $path = Join-Path ([string]$j.cwd) $path }
if (-not (Test-Path -LiteralPath $path)) { exit 0 }

$ext = [IO.Path]::GetExtension($path).ToLower()
$r = $null
if ($ext -eq ".py") {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $exe = $py.Source; $pre = @("-3.11") }
    else {
        $p2 = Get-Command python -ErrorAction SilentlyContinue
        if (-not $p2) { exit 0 }
        $exe = $p2.Source; $pre = @()
    }
    $code = "import sys; p=sys.argv[1]; compile(open(p,'rb').read(), p, 'exec')"
    $r = Invoke-Native $exe ($pre + @("-c", $code, $path))
    $lang = "Python"
} elseif ($ext -eq ".js") {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { exit 0 }
    $r = Invoke-Native $node.Source @("--check", $path)
    $lang = "JavaScript"
} else { exit 0 }

if ($r.code -ne 0) {
    $detail = ($r.out -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 6) -join "`n"
    Write-PostToolFeedback ("SYNTAX ERROR ($lang) in ${path}:`n" + $detail +
        "`nFix it before doing anything else (CLAUDE.md Rule 3)." +
        $(if ($lang -eq "JavaScript") { " A syntax error in one classic script stops every later script on the page." } else { "" }))
}
exit 0
