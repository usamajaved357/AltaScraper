# PostToolUse hook (Edit | Write | MultiEdit).
# Compiles the ONE file that was just changed, so a syntax error is reported the
# moment it is made rather than at the end of a task (CLAUDE.md Rule 3).
#   .py -> Python compile() (same check as py_compile, but writes no .pyc)
#   .js -> node --check (parses only: it cannot catch runtime errors)
# Exit 0 = fine or not applicable. Exit 2 = error; stderr is shown to Claude.

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
    $out = $p.StandardOutput.ReadToEnd() + $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    return @{ code = $p.ExitCode; out = $out }
}

try {
    $raw = [Console]::In.ReadToEnd()
    $j = $raw | ConvertFrom-Json
} catch { exit 0 }

$path = $null
if ($j.tool_input -and $j.tool_input.file_path) { $path = [string]$j.tool_input.file_path }
if (-not $path) { exit 0 }
if (-not [IO.Path]::IsPathRooted($path) -and $j.cwd) { $path = Join-Path ([string]$j.cwd) $path }
if (-not (Test-Path -LiteralPath $path)) { exit 0 }

$ext = [IO.Path]::GetExtension($path).ToLower()

if ($ext -eq ".py") {
    $py = (Get-Command py -ErrorAction SilentlyContinue)
    if ($py) { $exe = $py.Source; $pre = @("-3.11") }
    else {
        $p2 = Get-Command python -ErrorAction SilentlyContinue
        if (-not $p2) { exit 0 }
        $exe = $p2.Source; $pre = @()
    }
    $code = "import sys; p=sys.argv[1]; compile(open(p,'rb').read(), p, 'exec')"
    $r = Invoke-Native $exe ($pre + @("-c", $code, $path))
    if ($r.code -ne 0) {
        [Console]::Error.WriteLine("SYNTAX ERROR (Python) in ${path}:`n" + $r.out.Trim() + "`nFix it before continuing (CLAUDE.md Rule 3).")
        exit 2
    }
    exit 0
}

if ($ext -eq ".js") {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { exit 0 }
    $r = Invoke-Native $node.Source @("--check", $path)
    if ($r.code -ne 0) {
        [Console]::Error.WriteLine("SYNTAX ERROR (JavaScript) in ${path}:`n" + $r.out.Trim() + "`nFix it before continuing. A syntax error in one classic script stops every later script on the page.")
        exit 2
    }
    exit 0
}

exit 0
