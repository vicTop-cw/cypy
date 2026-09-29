#!/usr/bin/env python3
"""Seventh-pass reproduction harness — proves each candidate BEFORE any fix.

Each probe must fail (i.e. demonstrate the defect) on the pre-fix tree and pass after the fix.
Nothing here touches the real cache: the clear_cache probe runs inside a throwaway temp dir.
"""
from __future__ import annotations

import json
import locale
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESULTS = []


def probe(key, fn):
    try:
        verdict = fn()
    except Exception as exc:                       # a crash here is itself the finding
        verdict = {"crashed": f"{type(exc).__name__}: {exc}"}
    RESULTS.append({"probe": key, **verdict})
    print(f"[{key}] " + json.dumps(verdict, ensure_ascii=False)[:400])


# ---------------------------------------------------------------- BUG-15 clear_cache
def p_clear_cache():
    from cypy_hook.hook import CypyCacheManager
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "__pycache__" / "cypy"
        cache.mkdir(parents=True)
        victim = cache / "manifest.json"
        victim.write_text("{}", encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            CypyCacheManager().clear_cache()        # no-arg branch == "clear all"
            survived = victim.exists()
        finally:
            os.chdir(cwd)
        walked = [r for r, _d, _f in os.walk(os.path.join(tmp, "__pycache__"))]
        pred = [(os.path.basename(r), os.path.dirname(r)) for r in walked]
        return {"cache_file_survived_clear_all": survived,
                "walk_roots_seen": [str(x) for x in walked],
                "dirname_comparand": [list(x) for x in pred][:1],
                "defect": survived}


# ---------------------------------------------------------------- BUG-16 _pick_extension
def p_pick_extension():
    from cypyc.project.project_compiler import ProjectCompiler
    with tempfile.TemporaryDirectory() as tmp:
        foreign = os.path.join(tmp, "other_module.cp313-win_amd64.pyd")
        picked = ProjectCompiler._pick_extension([foreign], "mymod", tmp)
        return {"asked_for": "mymod", "candidates": [os.path.basename(foreign)],
                "picked": None if picked is None else os.path.basename(picked),
                "defect": picked is not None}


# ---------------------------------------------------------------- BUG-17 encoding-less writes
def p_encoding():
    import inspect
    import cypy_bridge.compiler as comp
    src = inspect.getsource(comp.BridgeCompiler._compile_c_to_shared_lib)
    hits = [ln.strip() for ln in src.splitlines()
            if "open(" in ln and "'w'" in ln and "encoding" not in ln]
    enc = locale.getpreferredencoding(False)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "gen.c")
        err = None
        try:
            with open(p, "w") as f:                # exactly what the product does
                f.write("/* \u0e01 */")              # a char outside cp936/cp1252
        except UnicodeEncodeError as exc:
            err = f"{type(exc).__name__}: {exc}"
    return {"preferred_encoding": enc, "writes_without_encoding": hits,
            "locale_encode_failure_reproduced": err, "defect": bool(hits)}


# ---------------------------------------------------------------- BUG-18 .pyd-only scan
def p_pyd_only():
    import inspect
    import cypy_bridge.compiler as comp
    src = inspect.getsource(comp.BridgeCompiler._compile_c_to_shared_lib)
    scan = [ln.strip() for ln in src.splitlines() if "endswith('.pyd')" in ln]
    det = inspect.getsource(comp.BridgeCompiler._detect_compiler)
    platforms = [ln.strip() for ln in det.splitlines() if "linux" in ln or "darwin" in ln]
    with tempfile.TemporaryDirectory() as tmp:
        so = os.path.join(tmp, "mod.cpython-313-x86_64-linux-gnu.so")
        Path(so).write_bytes(b"")
        matched = [f for f in os.listdir(tmp) if f.endswith(".pyd")]
    return {"scan_lines": scan, "detected_platforms": platforms,
            "linux_artifact_matched_by_scan": matched,
            "defect": not matched}


# ---------------------------------------------------------------- BUG-19 addr() shadowing
def p_addr():
    import ctypes
    from cypy_bridge.pointer import addr
    box = ctypes.c_void_p(4096)
    got = addr(box)
    null = addr(ctypes.c_void_p(0))
    return {"asked": "c_void_p(4096)", "addr_returned": got, "expected": 4096,
            "addr_of_null_pointer": null, "defect": got != 4096 or null != 0}


# ---------------------------------------------------------------- BUG-20 normalize collapse
def p_normalize():
    from cypyc.utils.indent_detector import IndentDetector
    src = "def f():\n  let a = 1\n  if a:\n    let b = 2\n"
    out = IndentDetector().normalize(src)
    detect = IndentDetector().detect(src)
    return {"indent_style": "2-space", "detect": list(detect),
            "input": src, "output": out,
            "body_dedented_to_column_0": out.startswith("def f():\nlet a"),
            "defect": out != src and out.splitlines()[1] != "    let a = 1"}


# ---------------------------------------------------------------- BUG-21 isfile(None)
def p_isfile_none():
    import os.path as op
    err = None
    try:
        op.isfile(None)
    except TypeError as exc:
        err = f"{type(exc).__name__}: {exc}"
    import subprocess
    r = subprocess.run([sys.executable, "-m", "cypyc", "hook"], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stderr or "").strip().splitlines()[-1:] or ["<no stderr>"]
    return {"bare_cypyc_hook_exitcode": r.returncode,
            "bare_cypyc_hook_last_stderr_line": tail[0],
            "isfile_none_raises": err,
            "defect": "TypeError" in " ".join(tail)}


for k, f in [("bug15_clear_cache", p_clear_cache), ("bug16_pick_extension", p_pick_extension),
             ("bug17_encoding", p_encoding), ("bug18_pyd_only", p_pyd_only),
             ("bug19_addr", p_addr), ("bug20_normalize", p_normalize),
             ("bug21_isfile_none", p_isfile_none)]:
    probe(k, f)

bad = [r["probe"] for r in RESULTS if r.get("defect") or r.get("crashed")]
print(f"\nprobes={len(RESULTS)} defect_confirmed={len(bad)} -> {bad}")
out = Path(__file__).resolve().parent / "repro_pass7.out.json"
out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", out.name)
sys.exit(0 if bad else 3)
