# SessionStart hook. Prints a short orientation that is added to Claude's
# context: where this session is, which branch, and what is in flight.
# Read-only and fast: no fetch, no network.

$ErrorActionPreference = "SilentlyContinue"

function Get-GitExe {
    $c = Get-Command git -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $base = Join-Path $env:LOCALAPPDATA "GitHubDesktop"
    $d = Get-ChildItem $base -Directory -Filter "app-*" |
        Sort-Object { try { [version]($_.Name -replace '^app-', '') } catch { [version]"0.0" } } -Descending |
        Select-Object -First 1
    if ($d) {
        $p = Join-Path $d.FullName "resources\app\git\cmd\git.exe"
        if (Test-Path $p) { return $p }
    }
    return $null
}

try { $j = [Console]::In.ReadToEnd() | ConvertFrom-Json } catch { $j = $null }
$here = if ($j -and $j.cwd) { [string]$j.cwd } else { (Get-Location).Path }

$git = Get-GitExe
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("== AltaScraper session start ==")
$lines.Add("Directory: $here")

$main = $null
if ($git) {
    $top = (& $git -C $here rev-parse --show-toplevel 2>$null)
    $branch = (& $git -C $here branch --show-current 2>$null)
    $upstream = (& $git -C $here rev-parse --abbrev-ref "@{upstream}" 2>$null)
    $common = (& $git -C $here rev-parse --path-format=absolute --git-common-dir 2>$null)
    if ($common) { $main = Split-Path -Parent ($common -replace '/', '\') }
    $dirty = @(& $git -C $here status --porcelain 2>$null).Count
    $ab = (& $git -C $here rev-list --left-right --count "origin/main...HEAD" 2>$null)
    $lines.Add("Worktree: $top")
    $lines.Add("Branch: $branch" + $(if ($upstream) { " (upstream $upstream)" } else { " (no upstream)" }))
    if ($ab) {
        $parts = ($ab -split '\s+')
        $lines.Add("Versus local origin/main ref (not fetched): behind $($parts[0]), ahead $($parts[1])")
    }
    $lines.Add("Uncommitted entries: $dirty")
    if ($branch -eq "main") { $lines.Add("WARNING: on main. Create a worktree from origin/main before editing (CLAUDE.md Rule 2).") }
}

if ($main) {
    $lines.Add("Main checkout (shared working state): $main")
    $cw = Join-Path $main "current-work.md"
    if (Test-Path $cw) {
        $lines.Add("--- current-work.md (first 30 lines) ---")
        Get-Content $cw -TotalCount 30 -Encoding UTF8 | ForEach-Object { $lines.Add($_) }
        $lines.Add("---")
    } else { $lines.Add("current-work.md: not found at $cw") }
    $act = Join-Path $main "active"
    if (Test-Path $act) { $lines.Add("active/: $act") }
    $rt = Join-Path $main "read.txt"
    if (Test-Path $rt) { $lines.Add("read.txt (task inbox): $rt, last modified " + (Get-Item $rt).LastWriteTime.ToString("yyyy-MM-dd HH:mm")) }
}

$lines.Add("Rules: CLAUDE.md. Push / merge / deploy only on the owner's explicit instruction.")
[Console]::Out.Write(($lines -join "`n"))
exit 0
