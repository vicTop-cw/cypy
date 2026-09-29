#!/usr/bin/env python3
"""Polish lane 1 -- marker inventory over the three production packages.

Run twice (baseline, rescan) and diff the JSON:
    python .fist-polish-20260926/marker_scan.py .fist-polish-20260926/markers_baseline.json
Read-only; never edits source. Every hit keeps file:line + the line text so a defect
claim can cite an exact location, and so a rescan diff is auditable.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ["cypyc", "cypy_bridge", "cypy_hook"]

RE_TODO = re.compile(r"#.*\bTODO\b")
RE_FIXME = re.compile(r"#.*\bFIXME\b")
RE_HACK = re.compile(r"#.*\bHACK\b")
RE_XXX = re.compile(r"#.*\bXXX\b")
RE_TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore")
RE_BARE_EXCEPT = re.compile(r"^\s*except\s*:")
RE_BROAD_EXCEPT = re.compile(r"^\s*except\s+(Exception|BaseException)\b")
RE_EXCEPT_HEADER = re.compile(r"^\s*except\b[^:]*:\s*(#.*)?$")
RE_INLINE_SWALLOW = re.compile(r"^\s*except\b[^:]*:\s*(pass|\.\.\.)\s*(#.*)?$")
RE_SWALLOW_BODY = re.compile(r"^\s*(pass|\.\.\.)\s*(#.*)?$")
RE_MUTABLE_DEFAULT = re.compile(r"^\s*(?:async\s+)?def\s+\w+\([^)]*=\s*(\[\]|\{\}|set\(\))")
RE_OPEN = re.compile(r"\bopen\(")
RE_SUBPROCESS = re.compile(r"subprocess\.(Popen|run|call|check_output|check_call)")


def py_files():
    for t in TARGETS:
        for p in sorted((ROOT / t).rglob("*.py")):
            if "__pycache__" not in p.parts:
                yield p


def scan():
    cats = ("TODO", "FIXME", "HACK", "XXX", "type_ignore", "bare_except",
            "except_swallowed", "broad_except", "mutable_default_arg",
            "open_without_with", "subprocess_call")
    hits = {c: [] for c in cats}
    lines = 0
    for path in py_files():
        rel = path.relative_to(ROOT).as_posix()
        src = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lines += len(src)
        for no, line in enumerate(src, 1):
            def add(cat):
                hits[cat].append([rel, no, line.strip()[:100]])
            if RE_TODO.search(line):
                add("TODO")
            if RE_FIXME.search(line):
                add("FIXME")
            if RE_HACK.search(line):
                add("HACK")
            if RE_XXX.search(line):
                add("XXX")
            if RE_TYPE_IGNORE.search(line):
                add("type_ignore")
            if RE_BARE_EXCEPT.match(line):
                add("bare_except")
            if RE_BROAD_EXCEPT.match(line):
                add("broad_except")
            if RE_INLINE_SWALLOW.match(line) or (
                    RE_EXCEPT_HEADER.match(line)
                    and no <= len(src) and RE_SWALLOW_BODY.match(src[no] if no < len(src) else "")):
                add("except_swallowed")
            if RE_MUTABLE_DEFAULT.match(line):
                add("mutable_default_arg")
            if RE_OPEN.search(line) and "with " not in line:
                add("open_without_with")
            if RE_SUBPROCESS.search(line):
                add("subprocess_call")
    return hits, lines


def git_head():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else ".fist-polish-20260926/markers.json"
    hits, lines = scan()
    files = [p.relative_to(ROOT).as_posix() for p in py_files()]
    doc = {
        "taken_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": git_head(),
        "files_scanned": len(files),
        "lines_scanned": lines,
        "counts": {k: len(v) for k, v in hits.items()},
        "detail": hits,
    }
    dest = ROOT / out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": out, "files": doc["files_scanned"], "lines": lines,
                      "counts": doc["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
