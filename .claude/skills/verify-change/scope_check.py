"""Deleted-function check (CLAUDE.md Rule 3), for every changed .py file.

Compares the functions defined in each file at a base commit against the
working tree, and prints what disappeared or appeared. Unlike the old
*.baseline.py copies it needs no snapshot: the base is a git commit (default:
the merge-base of HEAD and origin/main), and it covers every changed Python
file, not only the two monoliths. It counts `async def` too.

Usage (from the repo root):
    py -3.11 .claude/skills/verify-change/scope_check.py            # changed files vs merge-base
    py -3.11 .claude/skills/verify-change/scope_check.py --base origin/main routes/x.py

Exit 1 if any function was removed (it must then be a faithful move, explained,
or restored). Read-only.
"""
import argparse
import ast
import os
import subprocess
import sys


def git_exe():
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, "git.exe")
        if os.path.isfile(p):
            return p
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "GitHubDesktop")
    if os.path.isdir(base):
        def ver(n):
            try:
                return tuple(int(x) for x in n[4:].split("."))
            except ValueError:
                return (0,)
        apps = sorted((n for n in os.listdir(base) if n.startswith("app-")), key=ver, reverse=True)
        for a in apps:
            p = os.path.join(base, a, "resources", "app", "git", "cmd", "git.exe")
            if os.path.isfile(p):
                return p
    return "git"


GIT = git_exe()


def git(*args):
    r = subprocess.run([GIT, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout


def functions(src, label):
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {label}: {e}")
        return None
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(node.name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="commit to compare against (default: merge-base HEAD origin/main)")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()

    base = a.base
    if not base:
        code, out = git("merge-base", "HEAD", "origin/main")
        base = out.strip() if code == 0 and out.strip() else "HEAD"

    files = a.files
    if not files:
        _, committed = git("diff", "--name-only", f"{base}", "--", "*.py")
        _, untracked = git("ls-files", "--others", "--exclude-standard", "--", "*.py")
        files = sorted({f.strip() for f in (committed + untracked).splitlines() if f.strip().endswith(".py")})

    print(f"base: {base}")
    if not files:
        print("no changed .py files")
        return 0

    removed_any = False
    for f in files:
        code, old_src = git("show", f"{base}:{f}")
        old = functions(old_src, f"{f}@base") if code == 0 else set()
        if not os.path.exists(f):
            print(f"{f}: DELETED FILE (had {len(old or [])} functions)")
            removed_any = removed_any or bool(old)
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            new = functions(fh.read(), f)
        if old is None or new is None:
            removed_any = True
            continue
        removed = sorted(old - new)
        added = sorted(new - old)
        tag = "NEW FILE" if code != 0 else "changed"
        print(f"{f} ({tag}): REMOVED {removed}  ADDED {added}")
        if removed:
            removed_any = True
    return 1 if removed_any else 0


if __name__ == "__main__":
    sys.exit(main())
