#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared harness for the R2 feature-round probes (feat_constraint_* / feat_subtype_* / feat_dispatch_*).

This module is NOT a probe: its name starts with "_" so that
``repro_gate.py <prefix> ...`` (which globs ``{prefix}*.py``) never picks it up.

Contract used by every probe (same semantics as Find_BUG/audit_2026q3/repro_gate.py,
plus the third code the R2 task pack requires):

    exit 0  = the *expected* behaviour IS implemented (probe green)
    exit 1  = the expected behaviour is NOT implemented (probe red -- the R2 unit-1 state)
    exit 2  = the judge itself broke: the compiler crashed, a control/canary expectation
              about *current* documented behaviour failed, or the harness raised.
              This is neither an implementation gap nor a probe bug and must never be
              reported as "not implemented".

Read-only and idempotent: every .cypy corpus goes into a per-process
``tempfile.TemporaryDirectory()`` and the working directory is switched there, so
``cypy_hook``'s ``output/`` scratch lands outside the repository (verified: a transpile
run from the repo root writes ``output/<mod>.pyx``; with the chdir it writes
``<tmp>/output/<mod>.pyx`` and the repo tree is untouched).
"""
from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))

if hasattr(sys.stdout, "reconfigure"):                       # console may be GBK
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer, TokenType                # noqa: E402
from cypyc.parser.parser import Parser                       # noqa: E402
from cypy_hook.hook import CypyHook                          # noqa: E402

HOOK = CypyHook()
_TMP = tempfile.mkdtemp(prefix="cypy_feat_probe_")
atexit.register(shutil.rmtree, _TMP, True)

# Every corpus gets a fresh file name: cypy_hook's incremental cache is keyed by source
# path, and re-using a path with different content would let a stale cache answer the
# probe instead of the compiler.
_SEQ = [0]


def _unique(name: str) -> str:
    _SEQ[0] += 1
    return "%s_%d" % (re.sub(r"[^0-9a-zA-Z_]", "_", name), _SEQ[0])


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def z(text) -> str:
    """Decode/normalise subprocess output so it prints on any console codepage."""
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return _ANSI.sub("", text).encode("ascii", "replace").decode("ascii")


class HarnessError(Exception):
    """The judge itself is broken -> exit 2 (never 'not implemented')."""


# ---------------------------------------------------------------- compiler faces


def token_type(tok) -> str:
    """TokenType renders inconsistently across releases; normalise to a bare name."""
    value = getattr(getattr(tok, "type", None), "value", None)
    return str(value if value is not None else getattr(tok, "type", tok))


def parse(source: str):
    """Lexer+Parser only.  Returns (module_or_None, error_text_or_None).

    This is the face that exposes *silent swallowing*: when it returns a module,
    whatever the declaration really became is visible in ``module.body`` kinds.
    """
    try:
        return Parser(Lexer(source).tokenize()).parse(), None
    except Exception as exc:                                      # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, exc)


def top_kinds(source: str):
    """Kind list of the top-level statements; [] when the parse failed."""
    mod, _ = parse(source)
    return [] if mod is None else [s.kind for s in mod.body]


def transpile(name: str, source: str):
    """Full cypyc pipeline (lexer->parser->analyzers->codegen) on ``source``.

    Returns dict(success, errors, code, raised).  Runs with the CWD inside the
    probe's temp directory so no artifact is written into the repository.
    """
    path = os.path.join(_TMP, "%s.cypy" % _unique(name))
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(source)
    old = os.getcwd()
    os.chdir(_TMP)
    try:
        try:
            result = HOOK.transpile_file(path)
        except Exception as exc:                                  # noqa: BLE001
            raise HarnessError("transpile_file raised %s: %s" % (type(exc).__name__, exc))
        if not hasattr(result, "success") or not hasattr(result, "errors"):
            raise HarnessError("CompileResult shape changed: %r" % (type(result),))
        return {"success": bool(result.success),
                "errors": [str(e) for e in (result.errors or [])],
                "code": result.cython_code or "",
                "pyx": result.pyx_path or ""}
    finally:
        os.chdir(old)


def cli(name: str, source: str, command: str = "transpile", timeout: int = 300):
    """The real user-facing entry point: ``python -m cypyc <command> <file>``.

    NOTE (measured 2026-09-26): ``python -m cypyc`` ALWAYS exits 0 --
    cypyc/__main__.py:4 calls main() without sys.exit(), so cli() return code is
    useless; verdicts must be read out of the text and the produced artifact.
    Returns (stdout, stderr, returncode, artifact_exists).
    """
    path = os.path.join(_TMP, "%s.cypy" % name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(source)
    out = os.path.join(_TMP, "%s.pyx" % name)
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-m", "cypyc", command, path, "-o", out],
                          cwd=_TMP, env=env, capture_output=True, timeout=timeout)
    return z(proc.stdout), z(proc.stderr), proc.returncode, os.path.isfile(out)


def error_summary(result):
    """One-line rendering of a transpile() result for the evidence dump."""
    if result["success"]:
        return "transpile OK (no diagnostics)"
    return "transpile FAILED: " + " | ".join(result["errors"][:4])


# ------------------------------------------------------------------- reporting


class Report:
    """Collects decisive checks; a single unmet expectation makes the probe red."""

    def __init__(self, title, clauses):
        self.title = title
        self.clauses = clauses
        self.pending = []           # expectation checks (feature behaviour)
        self.evidence = []

    def banner(self, *purpose):
        print("=" * 78)
        print(self.title)
        print("=" * 78)
        print("clauses under test : %s" % self.clauses)
        for part in purpose:
            print("purpose            : %s" % part)
        print("scratch (auto-removed at exit): %s" % _TMP)

    def note(self, text):
        self.evidence.append(text)
        print("  . %s" % text)

    def raw(self, label, value):
        """Dump 'current behaviour, verbatim' -- the R2 unit-1 deliverable."""
        lines = str(value).rstrip("\n").splitlines() or ["(empty)"]
        print("  > %s" % label)
        for line in lines[:14]:
            print("      | %s" % line)
        if len(lines) > 14:
            print("      | ... (%d more lines)" % (len(lines) - 14))

    def control(self, label, ok, detail=""):
        """An expectation about *already documented current* behaviour (canary).

        Failure means the judge's own premise is gone -> exit 2, not exit 1.
        """
        flag = "OK " if ok else "XX "
        print("  [control] %s%-58s %s" % (flag, label[:58], detail))
        if not ok:
            raise HarnessError("control expectation broken: %s %s" % (label, detail))

    def expect(self, label, ok, detail=""):
        """An expectation of the *specified* (not yet implemented) behaviour."""
        print("  [%s] %-64s %s" % ("HOLD" if ok else "MISS", label[:64], detail))
        self.pending.append((label, bool(ok), detail))
        return bool(ok)

    def verdict(self):
        missed = [label for label, ok, _ in self.pending if not ok]
        print("-" * 78)
        print("checks=%d unmet=%d" % (len(self.pending), len(missed)))
        if missed:
            print("RESULT: NOT-IMPLEMENTED (red) -- %d expectation(s) unmet:" % len(missed))
            for label in missed:
                print("  * " + label)
            print("  (red 只说明这些 expect 未达成；归因看上面的 detail，"
                  "别把「未实现」与「探针夹具错」混成一条 —— 逐条核对 detail 里的诊断文本)")
            return 1
        print("RESULT: IMPLEMENTED (green) -- every specified expectation holds.")
        return 0


def run_probe(report: Report, body):
    """Entry helper: body(report) may raise HarnessError -> exit 2."""
    try:
        body(report)
    except HarnessError as exc:
        print("-" * 78)
        print("JUDGE ERROR (exit 2, not an implementation gap): %s" % exc)
        return 2
    except Exception:                                            # noqa: BLE001
        import traceback
        print("-" * 78)
        print("JUDGE CRASH (exit 2)")
        traceback.print_exc()
        return 2
    return report.verdict()


# --------------------------------------------------------------- corpora utils

KIND_UNION_BOUND = "UnionType"


def has_node_kind(module, kind: str) -> bool:
    """Walk the whole AST looking for a node kind (declarations may nest)."""
    if module is None:
        return False
    stack, seen = [module], set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if getattr(node, "kind", None) == kind:
            return True
        for value in vars(node).values():
            if hasattr(value, "kind"):
                stack.append(value)
            elif isinstance(value, (list, tuple)):
                stack.extend(v for v in value if hasattr(v, "kind"))
    return False


def find_nodes(module, kind: str):
    out = []
    stack, seen = ([module] if module is not None else []), set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if getattr(node, "kind", None) == kind:
            out.append(node)
        for value in vars(node).values():
            if hasattr(value, "kind"):
                stack.append(value)
            elif isinstance(value, (list, tuple)):
                stack.extend(v for v in value if hasattr(v, "kind"))
    return out
