"""R4-寻虫 法 1/3/4 的探针电池：把 R3-推进刚落的 `Callable` 元数判定放到**各种语句上下文**里跑，
看它在哪些上下文里真的会报、在哪些上下文里静默。

三档证据（缺一档就不下结论，这是 R3 两轮被抓后的硬规矩）：
  pos   = 违例调用（声明 1 元、实给 2 元）在该上下文里**是否报** `Callable arity mismatch`；
  ctl   = 同一上下文的**正确**调用 ⇒ 必须不报（报了就是过严，也是缺陷）；
  visit = 同一上下文里塞一条**返回类型不符**（那是本仓早就活着的判定）⇒ 它报了就证明"这个上下文被
          类型检查器走查过"。于是 pos 不报 + visit 报 ⇒ **真静默**（缺陷）；
          pos 不报 + visit 也不报 ⇒ 上下文整个没被走查（另一类缺陷，口径要分开写）。
再加一条**判据可观察性对照**：同一批夹具在"摘掉元数判定"的变异树上再跑一遍，pos 与变异树必须成对差；
若整批在任何一档都没差别 ⇒ 我的电池看不见这把尺子，本轮"没找到"就不许写成"没有"。
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
SCRATCH = HERE / "tmp_hunt2"
MUTANT = SCRATCH / "mutant"
IMPORTABLE = ("cypyc", "cypy_hook", "cypy_bridge")
NEEDLE = "                        self._check_callable_arity(node, args)\n"
ARITY = "Callable arity mismatch"
RETURN_ERR = "Return type mismatch"
REFUSE: list = []

DECL = "type Callback = Callable[[int], str]\n"

# 每条：(上下文名, 该上下文的违例夹具, 该上下文的正确夹具, 该上下文的"走查过吗"夹具)
# 违例夹具一律 `cb(1, 2)` 打声明为 1 元的 Callback；正确夹具 `cb(1)`；
# 走查夹具把返回值写成 int ⇒ 早就活着的返回类型判定必须报。
CASES = [
    ("plain_body",
     DECL + "def a(cb: Callback) -> str:\n    return cb(1, 2)\n",
     DECL + "def a(cb: Callback) -> str:\n    return cb(1)\n",
     DECL + "def a(cb: Callback) -> int:\n    return cb(1)\n"),
    ("let_initializer",
     DECL + "def a(cb: Callback) -> str:\n    let v: str = cb(1, 2)\n    return v\n",
     DECL + "def a(cb: Callback) -> str:\n    let v: str = cb(1)\n    return v\n",
     DECL + "def a(cb: Callback) -> int:\n    let v: int = cb(1)\n    return v\n"),
    ("if_body",
     DECL + "def a(cb: Callback, n: int) -> str:\n    if n > 0:\n        return cb(1, 2)\n    return \"\"\n",
     DECL + "def a(cb: Callback, n: int) -> str:\n    if n > 0:\n        return cb(1)\n    return \"\"\n",
     DECL + "def a(cb: Callback, n: int) -> int:\n    if n > 0:\n        return cb(1)\n    return 0\n"),
    ("elif_else_body",
     DECL + "def a(cb: Callback, n: int) -> str:\n    if n > 5:\n        return \"\"\n"
     "    elif n > 0:\n        return cb(1, 2)\n    else:\n        return \"\"\n",
     DECL + "def a(cb: Callback, n: int) -> str:\n    if n > 5:\n        return \"\"\n"
     "    elif n > 0:\n        return cb(1)\n    else:\n        return \"\"\n",
     DECL + "def a(cb: Callback, n: int) -> int:\n    if n > 5:\n        return 0\n"
     "    elif n > 0:\n        return cb(1)\n    else:\n        return 0\n"),
    ("for_body",
     DECL + "def a(cb: Callback, xs: list[int]) -> None:\n    for x in xs:\n        cb(1, 2)\n    return\n",
     DECL + "def a(cb: Callback, xs: list[int]) -> None:\n    for x in xs:\n        cb(1)\n    return\n",
     DECL + "def a(cb: Callback, xs: list[int]) -> int:\n    for x in xs:\n        return cb(1)\n    return 0\n"),
    ("while_body",
     DECL + "def a(cb: Callback) -> None:\n    let i: int = 0\n    while i < 3:\n        cb(1, 2)\n"
     "        i = i + 1\n    return\n",
     DECL + "def a(cb: Callback) -> None:\n    let i: int = 0\n    while i < 3:\n        cb(1)\n"
     "        i = i + 1\n    return\n",
     DECL + "def a(cb: Callback) -> int:\n    let i: int = 0\n    while i < 3:\n        return cb(1)\n"
     "    return 0\n"),
    ("defer_block",
     DECL + "def a(cb: Callback) -> str:\n    defer:\n        cb(1, 2)\n    return \"\"\n",
     DECL + "def a(cb: Callback) -> str:\n    defer:\n        cb(1)\n    return \"\"\n",
     DECL + "def a(cb: Callback) -> int:\n    defer:\n        cb(1)\n    return \"\"\n"),
    ("try_except",
     DECL + "def a(cb: Callback) -> str:\n    try:\n        return cb(1, 2)\n    except:\n        return \"\"\n",
     DECL + "def a(cb: Callback) -> str:\n    try:\n        return cb(1)\n    except:\n        return \"\"\n",
     DECL + "def a(cb: Callback) -> int:\n    try:\n        return cb(1)\n    except:\n        return 0\n"),
    ("struct_method",
     DECL + "struct Holder:\n    def run(self, cb: Callback) -> str:\n        return cb(1, 2)\n",
     DECL + "struct Holder:\n    def run(self, cb: Callback) -> str:\n        return cb(1)\n",
     DECL + "struct Holder:\n    def run(self, cb: Callback) -> int:\n        return cb(1)\n"),
    ("guard_expression",
     DECL + "def a(cb: Callback, n: int) -> str:\n    guard n > 0 else return \"\"\n    return cb(1, 2)\n",
     DECL + "def a(cb: Callback, n: int) -> str:\n    guard n > 0 else return \"\"\n    return cb(1)\n",
     DECL + "def a(cb: Callback, n: int) -> int:\n    guard n > 0 else return 0\n    return cb(1)\n"),
    ("nested_function",
     DECL + "def outer(cb: Callback) -> str:\n    def inner() -> str:\n        return cb(1, 2)\n"
     "    return inner()\n",
     DECL + "def outer(cb: Callback) -> str:\n    def inner() -> str:\n        return cb(1)\n"
     "    return inner()\n",
     DECL + "def outer(cb: Callback) -> int:\n    def inner() -> int:\n        return cb(1)\n"
     "    return inner()\n"),
    ("after_return_unreachable",
     DECL + "def a(cb: Callback) -> str:\n    return \"\"\n    cb(1, 2)\n",
     DECL + "def a(cb: Callback) -> str:\n    return \"\"\n    cb(1)\n",
     DECL + "def a(cb: Callback) -> int:\n    return \"\"\n    cb(1)\n"),
    ("binary_operand",
     DECL + "def a(cb: Callback) -> str:\n    let s: str = cb(1, 2) + cb(1)\n    return s\n",
     DECL + "def a(cb: Callback) -> str:\n    let s: str = cb(1) + cb(1)\n    return s\n",
     DECL + "def a(cb: Callback) -> int:\n    let s: int = cb(1) + cb(1)\n    return s\n"),
    ("let_aliased_callback",
     DECL + "def double(n: int) -> str:\n    return \"x\"\n\n"
     "def a() -> str:\n    let cb: Callback = double\n    return cb(1, 2)\n",
     DECL + "def double(n: int) -> str:\n    return \"x\"\n\n"
     "def a() -> str:\n    let cb: Callback = double\n    return cb(1)\n",
     DECL + "def double(n: int) -> str:\n    return \"x\"\n\n"
     "def a() -> int:\n    let cb: Callback = double\n    return cb(1)\n"),
    ("callable_return_type",
     DECL + "def mk() -> Callback:\n    return \"\"\n\n"
     "def use(mk_it: Callable[[], Callback]) -> str:\n    let f: Callback = mk_it()\n    return f(1, 2)\n",
     DECL + "def mk() -> Callback:\n    return \"\"\n\n"
     "def use(mk_it: Callable[[], Callback]) -> str:\n    let f: Callback = mk_it()\n    return f(1)\n",
     DECL + "def mk() -> Callback:\n    return \"\"\n\n"
     "def use(mk_it: Callable[[], Callback]) -> int:\n    let f: Callback = mk_it()\n    return f(1)\n"),
    ("struct_field_callback",
     DECL + "struct Runner:\n    cb: Callback\n\n    def run_it(self) -> str:\n        return self.cb(1, 2)\n",
     DECL + "struct Runner:\n    cb: Callback\n\n    def run_it(self) -> str:\n        return self.cb(1)\n",
     DECL + "struct Runner:\n    cb: Callback\n\n    def run_it(self) -> int:\n        return self.cb(1)\n"),
]

RUNNER = """
import json, sys
sys.path.insert(0, {0!r})
from cypy_hook.hook import CypyHook
import cypyc.analyzer.type_checker as _tc
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
identity = _tc.__file__
cases = json.loads(sys.stdin.read())
out = []
for name, src in cases:
    try:
        Parser(Lexer(src).tokenize()).parse()
        parsed = True
    except Exception as exc:
        out.append({{"name": name, "parsed": False, "parse_error": type(exc).__name__ + ": " + str(exc)[:120]}})
        continue
    _, errors = CypyHook().analyze_only(src)
    out.append({{"name": name, "parsed": True, "errors": list(errors)}})
print(json.dumps({{"identity": identity, "rows": out}}, ensure_ascii=False))
"""


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def build_mutant() -> dict:
    if MUTANT.exists():
        shutil.rmtree(MUTANT)
    MUTANT.mkdir(parents=True)
    copied = 0
    for pkg in IMPORTABLE:
        shutil.copytree(ROOT / pkg, MUTANT / pkg, ignore=shutil.ignore_patterns("__pycache__"))
        copied += 1
    tc = MUTANT / "cypyc" / "analyzer" / "type_checker.py"
    text = tc.read_text(encoding="utf-8", newline="")
    if text.count(NEEDLE) != 1:
        REFUSE.append(f"变异树锚点计数={text.count(NEEDLE)}（期望 1）⇒ 变异没生效，对照不作数")
        return {"packages_copied": copied, "mutated": False}
    tc.write_text(text.replace(NEEDLE, "", 1), encoding="utf-8", newline="")
    return {"packages_copied": copied, "mutated": True,
            "removed_line": NEEDLE.strip(), "tree": str(MUTANT).replace("\\", "/")}


def run_battery(tree: Path) -> dict:
    payload = json.dumps([[c[0], c[i]] for c in CASES for i in (1, 2, 3)], ensure_ascii=False)
    p = subprocess.run([PY, "-X", "utf8", "-c", RUNNER.format(str(tree), str(ROOT))],
                       cwd=str(ROOT), input=payload, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        REFUSE.append(f"电池在 {tree.name} 上跑挂了 rc={p.returncode}：{(p.stdout + p.stderr)[-300:]}")
        return {}
    rows = json.loads(p.stdout.strip().splitlines()[-1])
    ident = Path(rows["identity"]).resolve().as_posix()
    tree_pos = Path(tree).resolve().as_posix()
    if not ident.startswith(tree_pos):
        REFUSE.append(f"电池跑的不是那棵树：{tree.name} 的 type_checker 取自 {ident}")
        return {}
    out: dict = {}
    for idx, row in enumerate(rows["rows"]):
        ctx = CASES[idx // 3][0]
        slot = ("pos", "ctl", "visit")[idx % 3]
        out.setdefault(ctx, {})[slot] = row
    return out


def has(row: dict, needle: str) -> bool:
    return any(needle in e for e in (row or {}).get("errors", []))


def main() -> int:
    mutant_info = build_mutant()
    restored = run_battery(ROOT)
    mutated = run_battery(MUTANT)
    rows, invalid = [], []
    witness_pos_differ = 0
    silent, over_strict, unvisited = [], [], []
    for name, pos_src, ctl_src, visit_src in CASES:
        r = restored.get(name, {})
        m = mutated.get(name, {})
        rp, rc_, rv = r.get("pos", {}), r.get("ctl", {}), r.get("visit", {})
        bad_parse = [x for x in (rp, rc_, rv) if x and not x.get("parsed", True)]
        if bad_parse:
            invalid.append({"ctx": name, "parse_errors":
                            sorted({x.get("parse_error", "?")[:90] for x in bad_parse})})
            continue
        arity_pos = has(rp, ARITY)
        arity_ctl = has(rc_, ARITY)
        arity_mut = has(m.get("pos", {}), ARITY)
        visited = has(rv, RETURN_ERR)
        if arity_pos and not arity_mut:
            witness_pos_differ += 1
        verdict = "reported" if arity_pos else ("silent" if visited else "context-not-visited")
        if arity_ctl:
            over_strict.append(name)
        if not arity_pos and visited:
            silent.append(name)
        if not arity_pos and not visited:
            unvisited.append(name)
        rows.append({"ctx": name, "pos_reports_arity": arity_pos, "ctl_reports_arity": arity_ctl,
                     "mutant_reports_arity": arity_mut,
                     "context_visited_by_type_checker": visited,
                     "visit_probe_errors": rv.get("errors", []),
                     "pos_errors": rp.get("errors", []), "ctl_errors": rc_.get("errors", []),
                     "verdict": verdict, "sources": {"pos": pos_src, "ctl": ctl_src,
                                                     "visit": visit_src}})
    if not witness_pos_differ:
        REFUSE.append("整批夹具在摘掉判定后没有任何一条差别 ⇒ 电池看不见这把尺子，"
                      "本轮'没找到静默缺陷'不能写")
    if over_strict:
        REFUSE.append(f"正确调用被报 arity（过严，缺陷）：{over_strict}")
    if invalid:
        REFUSE.append(f"有夹具解析不过（夹具坏，不是产品结论）：{[x['ctx'] for x in invalid]}")
    doc = {"refuse": REFUSE, "battery_cases": len(CASES), "ran_on_trees": 2,
           "mutant_build": mutant_info, "witness_pos_differ": witness_pos_differ,
           "rows": rows, "invalid_fixtures": invalid,
           "silent_in_visited_context": silent, "context_not_visited": unvisited,
           "counts": {"reported": sum(1 for x in rows if x["pos_reports_arity"]),
                      "silent": len(silent), "not_visited": len(unvisited)},
           "at_utc": now_s()}
    shutil.rmtree(MUTANT, ignore_errors=True)
    left = [p.name for p in SCRATCH.glob("mutant*")] if SCRATCH.exists() else []
    doc["mutant_left"] = left
    if left:
        REFUSE.append(f"变异树没清干净：{left}")
    doc["refuse"] = REFUSE
    (HERE / "hunt_r4_probe.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "battery_cases": len(CASES),
                      "witness_pos_differ": witness_pos_differ, "counts": doc["counts"],
                      "silent": silent, "not_visited": unvisited, "invalid": [x["ctx"] for x in invalid],
                      "mutant_left": left}, ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
