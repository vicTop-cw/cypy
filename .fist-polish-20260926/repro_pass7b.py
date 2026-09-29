#!/usr/bin/env python3
"""Seventh-pass reproduction harness, part B — the parser/lexer/incremental candidates.

Every probe here must demonstrate the defect on the pre-fix tree. Part A proved the
bridge/hook/utils ones. The encoding probe is run as a *subprocess without -X utf8*, because
this very shell forces UTF-8 mode and would hide the locale codec in play for real users.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

R = []


def probe(key, fn):
    try:
        v = fn()
    except Exception as exc:
        v = {"crashed": f"{type(exc).__name__}: {exc}"}
    R.append({"probe": key, **v})
    print(f"[{key}] " + json.dumps(v, ensure_ascii=False)[:420])


def toks(src):
    from cypyc.parser.lexer import Lexer
    return [t.token_type.name for t in Lexer(src).tokenize() if not t.token_type.name == "NEWLINE"]


def p_backtick():
    src = 'def a() -> int:\n    return 1\n``\ndef b() -> int:\n    return 2\n'
    from cypyc.parser.parser import parse_source
    from cypyc.codegen.cython_generator import CythonGenerator
    ast = parse_source(src)
    top = [getattr(n, "name", None) for n in getattr(ast, "body", [])]
    gen = CythonGenerator().generate(ast)
    code = gen if isinstance(gen, str) else getattr(gen, "cython_code", "")
    return {"token_kinds": toks(src), "top_level_defs": top,
            "codegen_has_a": "def a" in code, "codegen_has_b": "def b" in code,
            "defect": "def a" in code and "def b" not in code}


def p_struct_decorators():
    src = ('@value struct Config:\n'
           '    let w: int\n'
           '    @python def label() -> str:\n'
           '        return "x"\n')
    from cypyc.parser.parser import parse_source
    from cypyc.codegen.cython_generator import CythonGenerator
    ast = parse_source(src)
    sd = [n for n in ast.body if getattr(n, "kind", "") == "StructDef"]
    dec = list(sd[0].decorators) if sd else None
    gen = CythonGenerator().generate(ast)
    code = gen if isinstance(gen, str) else getattr(gen, "cython_code", "")
    return {"structdef_decorators": dec,
            "codegen_has__eq__": "__eq__" in code, "codegen_has__repr__": "__repr__" in code,
            "defect": dec == [] or "__eq__" not in code}


def p_struct_control():
    src = '@value struct Config:\n    let w: int\n'
    from cypyc.parser.parser import parse_source
    from cypyc.codegen.cython_generator import CythonGenerator
    code = CythonGenerator().generate(parse_source(src))
    code = code if isinstance(code, str) else getattr(code, "cython_code", "")
    return {"control_without_decorated_member_has__eq__": "__eq__" in code, "defect": not ("__eq__" in code)}


def p_incremental_staleness():
    from cypyc.incremental.incremental_manager import IncrementalCompiler
    import inspect
    inc = IncrementalCompiler.__new__(IncrementalCompiler)
    src = ROOT / "setup.py"
    inc.cache = {}
    from cypyc.incremental.incremental_manager import CompilationCacheEntry
    sig = inspect.signature(CompilationCacheEntry)
    keys = [p for p in sig.parameters]
    ent = CompilationCacheEntry(**{k: ("deadbeef" if "hash" in k else None) for k in keys}) \
        if "file_hash" in keys else None
    inc.cache[os.path.abspath(str(src))] = ent
    changed = inc._check_imported_modules_changed(["setup"])
    return {"dep_cache_entry_hash": "deadbeef (differs from real file)",
            "helper_says_dependency_changed": bool(changed),
            "defect": not changed}


def p_hot_reload_union():
    from cypyc.incremental.hot_reload import HotReloadEngine, FileChangeEvent
    eng = HotReloadEngine.__new__(HotReloadEngine)
    calls = []
    eng._on_reload = lambda *a, **k: calls.append(a)
    eng._module_dependencies = {}
    eng._file_hashes = {}
    eng._watched_files = {}
    eng._cache_manager = None
    eng._compiled_modules = {}
    out = {"captured_stdout": None}
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            eng._handle_file_changes([FileChangeEvent(str(ROOT / "gone.cypy"), "deleted")])
        out["captured_stdout"] = buf.getvalue().strip()[:200]
    except Exception as exc:
        out["captured_stdout"] = f"raised {type(exc).__name__}: {exc}"
    out["callback_invoked"] = bool(calls)
    out["defect"] = "Callback error" in (out["captured_stdout"] or "") and not calls
    return out


def p_fr_string():
    src = 'let s = fr"{x}"\n'
    err = None
    try:
        toks(src)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    from cypyc.parser.parser import parse_source
    from cypyc.parser.lexer import Lexer
    kinds = [t.token_type.name for t in Lexer(src).tokenize()]
    pe = None
    try:
        parse_source(src)
    except Exception as exc:
        pe = f"{type(exc).__name__}: {exc}"
    rf_ok = None
    try:
        parse_source('let s = rf"{x}"\n')
        rf_ok = True
    except Exception as exc:
        rf_ok = f"{type(exc).__name__}: {exc}"
    return {"token_kinds_fr": kinds, "parse_error_fr": pe, "parse_ok_rf": rf_ok,
            "defect": bool(pe) and rf_ok is True}


def p_locale_write():
    code = ("import locale,tempfile,os,sys;"
            "print('preferred='+locale.getpreferredencoding(False));"
            "t=tempfile.mkdtemp();p=os.path.join(t,'gen.c')\n"
            "try:\n"
            "    open(p,'w').write('/* \\u0e01 */')\n"
            "    print('wrote-ok')\n"
            "except UnicodeEncodeError as e:\n"
            "    print('UnicodeEncodeError:',e)\n")
    env = {k: v for k, v in os.environ.items() if "UTF8" not in k.upper()}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=str(ROOT))
    out = (r.stdout or "").strip().replace("\n", " | ")
    return {"subprocess_output": out[:220],
            "defect": "UnicodeEncodeError" in out}


for k, f in [("lex_backtick", p_backtick), ("struct_decorators", p_struct_decorators),
             ("struct_control", p_struct_control), ("incremental_staleness", p_incremental_staleness),
             ("hot_reload_union", p_hot_reload_union), ("fr_string", p_fr_string),
             ("locale_write", p_locale_write)]:
    probe(k, f)

bad = [r["probe"] for r in R if r.get("defect")]
print(f"\nprobes={len(R)} defect_confirmed={len(bad)} -> {bad}")
Path(__file__).resolve().with_name("repro_pass7b.out.json").write_text(
    json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote repro_pass7b.out.json")
