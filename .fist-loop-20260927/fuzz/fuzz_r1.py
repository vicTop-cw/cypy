"""Mutation fuzz round 1 for the Cypy compiler front-end.

Runs the in-process pipeline (Preprocessor -> Lexer -> Parser -> analyzers ->
CythonGenerator) exactly like cypy_hook.CypyHook._parse_and_analyze does, but
WITHOUT the blanket `except Exception` so that internal crashes are visible.

Usage:
    python .fist-loop-20260927/fuzz/fuzz_r1.py            # run all mutants
    python .fist-loop-20260927/fuzz/fuzz_r1.py --verify    # only seed corpus

Outputs:
    fuzz_r1.log          human readable log
    results_r1.jsonl     one JSON record per mutant (resumable)
    current_r1.json      mutant in flight (used to detect hangs after a kill)
    mutants/*.cypy       mutants kept (interesting ones)
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MUTDIR = os.path.join(HERE, "mutants")
RESULTS = os.path.join(HERE, "results_r1.jsonl")
LOG = os.path.join(HERE, "fuzz_r1.log")
CURRENT = os.path.join(HERE, "current_r1.json")

SEED = 20260927
TIMEOUT_S = 5.0
sys.setrecursionlimit(1000)  # keep the CLI default so results match the user path

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_LOG_F = open(LOG, "a", encoding="utf-8", errors="replace")


def log(msg: str = "") -> None:
    _LOG_F.write(msg + "\n")
    _LOG_F.flush()
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "backslashreplace").decode())


# --------------------------------------------------------------------------
# the pipeline under test
# --------------------------------------------------------------------------
def run_pipeline(source: str) -> str:
    from cypyc.parser.preprocessor import Preprocessor
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
    from cypyc.analyzer.type_checker import TypeChecker
    from cypyc.analyzer.pointer_checker import PointerChecker
    from cypyc.analyzer.cycle_detector import CycleDetector
    from cypyc.analyzer.build_block_checker import BuildBlockChecker
    from cypyc.codegen.cython_generator import CythonGenerator

    src = Preprocessor().process(source)
    tokens = list(Lexer(src).tokenize())
    ast = Parser(tokens).parse()

    scope = ScopeAnalyzer()
    scope.analyze(ast)
    tc = TypeChecker()
    tmap = tc.check(ast)
    pc = PointerChecker()
    pc.check(ast, tmap)
    cd = CycleDetector()
    cd.analyze(ast)
    bb = BuildBlockChecker()
    bb.check(ast)

    diag = []
    diag += list(getattr(scope, "errors", []) or [])
    diag += list(getattr(tc, "errors", []) or [])
    diag += list(getattr(pc, "errors", []) or [])
    diag += list(getattr(bb, "errors", []) or [])
    if diag:
        raise DiagnosticError(diag)

    gen = CythonGenerator()
    return gen.generate(ast)


class DiagnosticError(Exception):
    """Analyzer reported user-facing diagnostics (structured errors)."""


LOC_RE = re.compile(r"(line\s*:?\s*\d+|at\s+\d+[:.]|\b\d+:\d+\b)", re.I)
CLEAN_TYPES = {"ValueError", "SyntaxError", "IncludeError", "DiagnosticError"}


def classify(exc: BaseException) -> tuple[str, str]:
    name = type(exc).__name__
    text = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    if name == "DiagnosticError":
        # analyzers produced messages -> clean only when they carry a location
        joined = " | ".join(str(x) for x in getattr(exc, "args", ()))
        return ("a", text) if LOC_RE.search(joined) else ("b", "analyzer error without location: " + joined[:300])
    if name in CLEAN_TYPES and LOC_RE.search(text):
        return "a", text
    if name == "KeyboardInterrupt":
        raise KeyboardInterrupt
    return "b", text


# --------------------------------------------------------------------------
# mutations
# --------------------------------------------------------------------------
PRINTABLE = list("abcdefghijklmnopqrstuvwxyz0123456789 \t:;,()[]{}.<>=+-*/\"'#!@%^&|~?\\_$") + ["\u4e2d", "\u00e9"]
BRACKETS = ["(", ")", "[", "]", "{", "}", "((", "))", "[(]", "{{"]


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def mut_del_char(rng, text):
    if not text:
        return text
    i = rng.randrange(len(text))
    return text[:i] + text[i + 1:]


def mut_del_char_smart(rng, text):
    """delete a char that is a syntax-bearing character"""
    idxs = [i for i, c in enumerate(text) if c in "()[]{}:\"'<>=:;,"]
    if not idxs:
        return mut_del_char(rng, text)
    i = rng.choice(idxs)
    return text[:i] + text[i + 1:]


def mut_repl_char(rng, text):
    if not text:
        return text
    i = rng.randrange(len(text))
    return text[:i] + rng.choice(PRINTABLE) + text[i + 1:]


def mut_dup_line(rng, text):
    ls = _lines(text)
    if not ls:
        return text
    i = rng.randrange(len(ls))
    ls.insert(i, ls[i])
    return "".join(ls)


def mut_dup_block(rng, text):
    ls = _lines(text)
    if len(ls) < 4:
        return text
    n = rng.randint(2, min(6, len(ls) - 1))
    i = rng.randrange(len(ls) - n)
    blk = ls[i:i + n]
    j = rng.randrange(len(ls) + 1)
    ls[j:j] = blk
    return "".join(ls)


def mut_flip_quote(rng, text):
    idxs = [i for i, c in enumerate(text) if c in "\"'"]
    if idxs and rng.random() < 0.7:
        i = rng.choice(idxs)
        other = "'" if text[i] == '"' else '"'
        return text[:i] + other + text[i + 1:]
    return text + '\nlet s = "unclosed\n'


def mut_truncate(rng, text):
    if len(text) < 20:
        return text
    cut = int(len(text) * rng.uniform(0.15, 0.9))
    return text[:cut]


def mut_truncate_eol(rng, text):
    ls = _lines(text)
    if len(ls) < 3:
        return text
    return "".join(ls[:rng.randrange(1, len(ls))])


def mut_insert_bracket(rng, text):
    b = rng.choice(BRACKETS)
    if not text:
        return b
    i = rng.randrange(len(text) + 1)
    return text[:i] + b + text[i:]


def mut_insert_nl_indent(rng, text):
    ls = _lines(text)
    i = rng.randrange(len(ls)) if ls else 0
    frag = rng.choice(["    x = 1\n", "\t\treturn\n", "\n  bad indent here\n", "        end\n"])
    ls.insert(i, frag)
    return "".join(ls)


def mut_kw_surgery(rng, text):
    kw = rng.choice(["let ", "const ", "def ", "class ", "struct ", "if ", "else", "for ", "while ",
                     "return ", "match ", "import ", "fn ", "->", "::", ":=", "|>"])
    i = rng.randrange(len(text) + 1)
    return text[:i] + kw + text[i:]


def mut_insert_control_char(rng, text):
    c = rng.choice(["\x00", "\x07", "\x1b", "\x0b", "\x7f", "\x1a", "\ufeff", "\u202e", "\ud800"])
    i = rng.randrange(len(text) + 1) if text else 0
    return text[:i] + c + text[i:]


def mut_swap_lines(rng, text):
    ls = _lines(text)
    if len(ls) < 3:
        return text
    i = rng.randrange(len(ls) - 1)
    ls[i], ls[i + 1] = ls[i + 1], ls[i]
    return "".join(ls)


def mut_dedent(rng, text):
    ls = _lines(text)
    idxs = [i for i, l in enumerate(ls) if l.startswith(("  ", "\t"))]
    if not idxs:
        return text
    i = rng.choice(idxs)
    ls[i] = ls[i].lstrip()
    return "".join(ls)


OPS = [
    ("del_char", mut_del_char),
    ("del_sigil", mut_del_char_smart),
    ("repl_char", mut_repl_char),
    ("dup_line", mut_dup_line),
    ("dup_block", mut_dup_block),
    ("flip_quote", mut_flip_quote),
    ("truncate", mut_truncate),
    ("truncate_eol", mut_truncate_eol),
    ("ins_bracket", mut_insert_bracket),
    ("ins_indent", mut_insert_nl_indent),
    ("kw_surgery", mut_kw_surgery),
    ("ins_ctrl_char", mut_insert_control_char),
    ("swap_lines", mut_swap_lines),
    ("dedent", mut_dedent),
]


def seed_files():
    ex = os.path.join(ROOT, "examples")
    out = []
    for name in sorted(os.listdir(ex)):
        if not name.endswith(".cypy") or name.startswith("_"):
            continue
        with open(os.path.join(ex, name), "r", encoding="utf-8") as f:
            out.append((name, f.read()))
    return out


def build_mutants(seeds, total=95):
    rng = random.Random(SEED)
    plan = []
    # first: sanity entries for the unmutated seeds (class baseline)
    for i, (name, text) in enumerate(seeds):
        plan.append({"id": f"seed{i:03d}", "op": "none", "src": name, "text": text, "bytes": None})
    n = 0
    nonutf8 = 0
    entries = []
    while len(entries) < total:
        name, text = seeds[rng.randrange(len(seeds))]
        opname, fn = OPS[n % len(OPS)]
        n += 1
        try:
            mutated = fn(rng, text)
            mutated = fn(rng, mutated) if rng.random() < 0.25 else mutated
        except Exception:
            continue
        if mutated == text or not mutated:
            continue
        entries.append({"id": f"m{n:04d}", "op": opname, "src": name, "text": mutated, "bytes": None})
        # every 6th text mutant also gets a byte-level (non-UTF8) sibling
        if n % 6 == 0 and nonutf8 < 14:
            nonutf8 += 1
            b = mutated.encode("utf-8", "surrogatepass")
            cut = rng.randint(20, max(21, len(b) - 1))
            entries.append({"id": f"nm{nonutf8:03d}", "op": "nonutf8_" + opname, "src": name,
                            "text": mutated, "bytes": b[:cut] + bytes([0xff, 0xfe, 0x80, 0xc0, 0xaf])})
    plan.extend(entries)
    return plan


def done_ids():
    ids = set()
    if os.path.exists(RESULTS):
        with open(RESULTS, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ids.add(json.loads(line)["id"])
                    except Exception:
                        pass
    return ids


def save_mutant(entry, text=None):
    path = os.path.join(MUTDIR, entry["id"] + "_" + entry["src"])
    payload = text if text is not None else entry["text"]
    if entry.get("bytes") is not None:
        with open(path, "wb") as f:
            f.write(entry["bytes"])
    else:
        with open(path, "w", encoding="utf-8", errors="surrogatepass", newline="") as f:
            f.write(payload)
    return path


def record(rec):
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(CURRENT, "w", encoding="utf-8") as f:
        f.write("{}\n")
    log(f"[{rec['cls']}] {rec['id']} {rec['op']:>18} {rec['src']:<28} {rec['note'][:150]}")


def run_one(entry, deadline_state):
    rec = {"id": entry["id"], "op": entry["op"], "src": entry["src"], "cls": "?", "note": "", "tb": ""}
    text = entry["text"]
    if entry.get("bytes") is not None:
        # non-UTF8 input: decode the way the CLI reads files
        try:
            text = entry["bytes"].decode("utf-8")
        except UnicodeDecodeError as e:
            rec["cls"] = "b"
            rec["note"] = "read stage: " + type(e).__name__
            rec["tb"] = "".join(traceback.format_exception_only(type(e), e)).strip()
            rec["kept"] = save_mutant(entry)
            return rec

    t0 = time.monotonic()
    deadline_state[0] = t0 + TIMEOUT_S
    try:
        out = run_pipeline(text)
        rec["cls"] = "c"
        rec["note"] = f"generated {len(out)} chars in {time.monotonic() - t0:.2f}s"
    except BaseException as e:  # noqa: BLE001 - fuzz harness must catch everything
        cls, note = classify(e)
        rec["cls"] = cls
        rec["note"] = note[:400]
        rec["tb"] = "".join(traceback.format_tb(e.__traceback__)).strip()[-2500:]
        rec["exc"] = type(e).__name__
        rec["elapsed"] = round(time.monotonic() - t0, 2)
    deadline_state[0] = float("inf")
    if rec["cls"] in ("b", "d"):
        rec["kept"] = save_mutant(entry, text)
    return rec


def watchdog(deadline_state, cur_holder):
    while True:
        time.sleep(0.25)
        if time.monotonic() > deadline_state[0]:
            with open(CURRENT, "w", encoding="utf-8") as f:
                json.dump(cur_holder[0], f)
            log(f"@@HANG {cur_holder[0]}  > {TIMEOUT_S}s -> killed")
            _LOG_F.flush()
            os._exit(42)


def main() -> int:
    os.makedirs(MUTDIR, exist_ok=True)
    seeds = seed_files()
    log(f"seed corpus: {len(seeds)} files, SEED={SEED}, recursionlimit={sys.getrecursionlimit()}")
    plan = build_mutants(seeds)
    log(f"mutants planned (incl. {len(seeds)} unmutated baselines): {len(plan)}")

    # a hang kills the process; mark that mutant and continue on next invocation
    if os.path.exists(CURRENT):
        try:
            with open(CURRENT, "r", encoding="utf-8") as f:
                hung = json.load(f)
            if hung and hung.get("id") and hung["id"] not in done_ids():
                hung_rec = {"id": hung["id"], "op": hung.get("op", "?"), "src": hung.get("src", "?"),
                            "cls": "d", "note": f"timeout > {TIMEOUT_S}s (watchdog kill)", "tb": ""}
                for p in plan:
                    if p["id"] == hung["id"]:
                        hung_rec["kept"] = save_mutant(p, p["text"])
                record(hung_rec)
        except Exception:
            pass

    deadline_state = [float("inf")]
    cur_holder = [{}]
    threading.Thread(target=watchdog, args=(deadline_state, cur_holder), daemon=True).start()

    skip = done_ids()
    ran = 0
    for entry in plan:
        if entry["id"] in skip:
            continue
        cur_holder[0] = {"id": entry["id"], "op": entry["op"], "src": entry["src"]}
        record(run_one(entry, deadline_state))
        ran += 1
    counts = {}
    with open(RESULTS, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                counts[r["cls"]] = counts.get(r["cls"], 0) + 1
    log(f"@@SUMMARY ran_this_invocation={ran} counts={counts} total={sum(counts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
