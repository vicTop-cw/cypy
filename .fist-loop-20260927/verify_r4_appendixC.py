"""R4-验证 法④：`SYNTAX/appendix-C-features.md:598`《已实现的限制修复》逐行复测。

口径：
· 行清单**从冻结文档当场反解**（不手抄），条数与文档不符就 refuse——文档改了尺子必须跟着改；
· 每行现写一段最小 `.cypy`，走 `cypyc.cli transpile`（真出 `.pyx`），
  证据是**生成物里的实际形状**或**codegen 方法的调用计数**（用公开 API 包一层计数器），
  不是「源码里出现了这个字样」；
· 每行结论分三档：`verified`（两面都过）/ `claim-false`（文档说已实现，调用面不成立）/
  `unverified`（本件没能测到，写明为什么）——`unverified` 一律进 deviations，不许混进 verified；
· canary：拿一个必然不存在的证据 needle 复核一遍匹配器，匹配器若说「过」，本件自己就是装饰。
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TMP = HERE / "verify_r4_tmp" / "appendixC"
DOC = ROOT / "SYNTAX" / "appendix-C-features.md"
OUT = HERE / "verify_r4_appendixC.json"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
CHECKS: list = []
REFUSE: list = []
TYPE_F_ALIAS = 'type F = Callable[[int], int]\n'

COUNTER_DRIVER = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, %(root)r)
import cypyc.codegen.cython_generator as cg
from cypy_hook.hook import CypyHook

counts = {}
for name in ("_generate_tuple_condition", "_generate_array_condition", "_generate_dict_condition"):
    orig = getattr(cg.CythonGenerator, name)
    def make(n, f):
        def wrapper(self, *a, **kw):
            counts[n] = counts.get(n, 0) + 1
            return f(self, *a, **kw)
        return wrapper
    setattr(cg.CythonGenerator, name, make(name, orig))
src = Path(sys.argv[1]).read_text(encoding="utf-8")
ast, errs = CypyHook().analyze_only(src)
code = cg.CythonGenerator("probe").generate(ast)
print(json.dumps({"counts": counts, "len": len(code), "analyze_errors": errs}))
'''

PROBES = {
    "切片语法": {
        "codegen_src": "def f() -> int:\n    let xs: list<int> = [1, 2, 3, 4]\n"
                       "    let a = xs[1:3]\n    return 0\n",
        "typeface_src": "def f() -> list<int>:\n    let xs: list<int> = [1, 2, 3, 4]\n"
                        "    return xs[1:3]\n",
        "needles": ["[1:3]"], "kind": "slice"},
    "`not in`": {"src": "def f(xs: list<int>) -> bool:\n    return 5 not in xs\n",
                 "needles": ["not in"], "kind": "plain"},
    "`not is`": {"src": "def f(a: object, b: object) -> bool:\n    return a not is b\n",
                 "needles": ["is not", "not is"], "needles_any": True, "kind": "plain"},
    "_generate_tuple_condition": {
        "src": "def f(p) -> int:\n    match p:\n        case (0, 0):\n            return 0\n"
               "        case (x, 0):\n            return x\n"
               "        case _:\n            return -1\n",
        "needles": ["isinstance(_match_subject_1, (list, tuple))",
                    "len(_match_subject_1) == 2"],
        "count": "_generate_tuple_condition", "kind": "counted"},
    "_generate_array_condition": {
        "src": "def f(xs) -> int:\n    match xs:\n        case [head, *rest]:\n"
               "            return head\n"
               "        case _:\n            return 0\n",
        "needles": ["isinstance(_match_subject_1, (list, tuple))",
                    "len(_match_subject_1) >= 1", "rest = _match_subject_1[1:]"],
        "count": "_generate_array_condition", "kind": "counted"},
    "_generate_dict_condition": {
        "src": 'def f(d) -> int:\n    match d:\n        case {"a": v}:\n            return v\n'
               "        case _:\n            return 0\n",
        "needles": ["isinstance(_match_subject_1, dict)", "'a' in _match_subject_1"],
        "count": "_generate_dict_condition", "kind": "counted"},
    "三元条件表达式": {
        "src": 'def f(x: int) -> str:\n    return "pos" if x > 0 else "neg"\n',
        "needles": [" if ", " else "], "kind": "plain"},
    "*args": {
        "src": "def f(*args, **kwargs) -> int:\n    let n: int = 0\n    for a in args:\n"
               "        n += 1\n    return n\n",
        "needles": ["*args", "**kwargs"], "kind": "plain"},
    "整除运算符": {
        "src": "def f(a: int, b: int) -> int:\n    return a // b\n",
        "needles": ["//"], "kind": "plain"},
    "复合赋值": {
        "src": "def f(x: int) -> int:\n    x //= 3\n    x %= 5\n    return x\n",
        "needles": ["x = x // 3", "x = x % 5"],
        "desugar_note": "生成物把 `//=`/`%=` 脱糖成 `x = x // 3` 形式", "kind": "plain"},
    "global": {
        "src": "counter: int = 0\n\ndef bump() -> None:\n    global counter\n"
               "    counter += 1\n\ndef outer() -> int:\n    total = 0\n\n"
               "    def inner() -> None:\n        nonlocal total\n        total += 1\n\n"
               "    inner()\n    return total\n",
        "needles": ["global ", "nonlocal "], "kind": "plain"},
    "`await` 表达式": {
        "src": "async def helper(v: int) -> int:\n    return v\n\nasync def drive(v: int) -> int:\n"
               "    return await helper(v)\n",
        "needles": ["await "], "kind": "plain"},
    "`async def`": {"src": "async def helper(v: int) -> int:\n    return v\n",
                    "needles": ["async def"], "kind": "plain"},
    "BacktickBlock": {"src": "def f() -> None:\n    let s = ```print(1)```\n",
                      "needles": ["'print(1)'"], "kind": "plain"},
}

DEMO = "examples/demos/upcoming_features/planned_features.cypy"


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def doc_rows() -> list:
    """从冻结文档反解《已实现的限制修复》表体（只读，不改文档一个字）。"""
    text = DOC.read_text(encoding="utf-8")
    sec = text.split("### 已实现的限制修复", 1)[1]
    sec = sec.split("\n### ", 1)[0]
    lines = [ln.strip() for ln in sec.splitlines() if ln.strip().startswith("|")]
    body = [ln for ln in lines if not set(ln.replace("|", "").strip()) <= {"-", " "}
            and "特性" not in ln]
    return body


def transpile(src_path: Path) -> dict:
    cmd = [sys.executable, "-X", "utf8", "-m", "cypyc.cli", "transpile", str(src_path),
           "-o", str(TMP / "out")]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    text = ANSI_RE.sub("", (p.stdout or "") + (p.stderr or ""))
    diags = [ln.strip()[2:] for ln in text.splitlines() if ln.strip().startswith("- ")]
    return {"command_verbatim": " ".join(cmd), "rc": p.returncode, "diags": diags}


def check_only(src_path: Path) -> dict:
    cmd = [sys.executable, "-X", "utf8", "-m", "cypyc.cli", "transpile", str(src_path),
           "-o", str(TMP / "out"), "--check-only"]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    text = ANSI_RE.sub("", (p.stdout or "") + (p.stderr or ""))
    diags = [ln.strip()[2:] for ln in text.splitlines() if ln.strip().startswith("- ")]
    return {"command_verbatim": " ".join(cmd), "rc": p.returncode, "diags": diags}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    TMP.mkdir(parents=True, exist_ok=True)
    rows = doc_rows()
    check("文档行清单必须当场反解到 14 行", len(rows), 14, "《已实现的限制修复》表体")

    unmapped = [ln for ln in rows if not any(k in ln for k in PROBES)]
    check("每行都要有对应探针（映射漏行=无人认领）", unmapped, [], "见 rows")

    results = []
    for idx, ln in enumerate(rows, start=1):
        key = next((k for k in PROBES if k in ln), None)
        probe = PROBES[key]
        item = {"n": idx, "doc_row_verbatim": ln, "matched_key": key, "kind": probe["kind"]}
        if probe["kind"] == "slice":
            cg_src = TMP / f"r{idx}_codegen.cypy"
            cg_src.write_text(probe["codegen_src"], encoding="utf-8", newline="\n")
            gen = transpile(cg_src)
            pyx = (TMP / "out" / f"{cg_src.stem}.pyx")
            body = pyx.read_text(encoding="utf-8") if pyx.exists() else ""
            tf_src = TMP / f"r{idx}_typeface.cypy"
            tf_src.write_text(probe["typeface_src"], encoding="utf-8", newline="\n")
            tf = check_only(tf_src)
            demo = check_only(ROOT / DEMO)
            missing = [n for n in probe["needles"] if n not in body]
            faces_ok = tf["rc"] == 0 and demo["rc"] == 0 and not missing
            reason = (
                "生成面含切片证据且 --check-only 与仓内 DEMO 两路都 rc=0" if faces_ok else
                f"生成面 .pyx 证据缺 {missing}；类型面把切片表达式的类型判成容器**元素**类型："
                f"实测 {tf['diags']}；仓内自带 DEMO {DEMO} 走 --check-only 得 {demo['rc']} 码、"
                f"{len(demo['diags'])} 条诊断 ⇒ 文档「已实现 v0.2」在调用面不成立")
            item.update({
                "codegen": gen, "codegen_evidence_missing": missing,
                "typeface": tf, "demo_face": {"file": DEMO, **demo},
                "verdict": "verified" if faces_ok else "claim-false",
                "reason": reason})
        else:
            src = TMP / f"r{idx}.cypy"
            src.write_text(probe["src"], encoding="utf-8", newline="\n")
            gen = transpile(src)
            pyx = (TMP / "out" / f"{src.stem}.pyx")
            body = pyx.read_text(encoding="utf-8") if pyx.exists() else ""
            missing = [n for n in probe["needles"] if n not in body]
            if probe.get("needles_any"):
                missing = probe["needles"] if not any(n in body for n in probe["needles"]) else []
            counts = {}
            method_calls = -1
            if probe["kind"] == "counted":
                drv = TMP / "counter_driver.py"
                drv.write_text(COUNTER_DRIVER % {"root": str(ROOT)}, encoding="utf-8",
                               newline="\n")
                r = subprocess.run([sys.executable, "-X", "utf8", str(drv), str(src)],
                                   cwd=str(ROOT), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=300)
                try:
                    counts = json.loads(r.stdout.strip().splitlines()[-1])
                except Exception:
                    counts = {"error": (r.stderr or r.stdout)[-300:]}
                if counts.get("error"):
                    REFUSE.append(f"r{idx} 计数器跑不动：{counts['error'][:160]}")
                    method_calls = -1
                else:
                    method_calls = int(counts.get("counts", {}).get(probe["count"], 0))
            behaviour_ok = gen["rc"] == 0 and pyx.exists() and not missing
            if not pyx.exists():
                verdict, reason = "unverified", f"没有生成物可看：rc={gen['rc']} 诊断={gen['diags']}"
            elif not behaviour_ok:
                verdict, reason = "claim-false", (
                    f"rc={gen['rc']} pyx=True 缺证据={missing} 诊断={gen['diags']}")
            elif probe["kind"] == "counted" and method_calls == 0:
                verdict, reason = "claim-half-true", (
                    f"行为面成立（生成物含 {probe['needles']}），但文档点名的私有方法 "
                    f"`{probe['count']}` 调用计数为 0 ⇒ 该名字不在活路径上"
                    f"（活路径在 `_pattern_match_info`，把同样的条件就地拼出来）")
            else:
                verdict = "verified"
                reason = probe.get("desugar_note", "")
            item.update({
                "probe": gen, "pyx_exists": pyx.exists(),
                "pyx_tail": body[-260:], "evidence_missing": missing,
                "call_counts": counts, "named_method_calls": method_calls,
                "verdict": verdict, "reason": reason})
        results.append(item)

    verified = [r for r in results if r["verdict"] == "verified"]
    claim_false = [r for r in results if r["verdict"] == "claim-false"]
    half_true = [r for r in results if r["verdict"] == "claim-half-true"]
    unverified = [r for r in results if r["verdict"] == "unverified"]

    # canary：证据匹配器必须能判「不过」——用一个必然不存在的 needle 复跑一次
    sample = TMP / "canary.cypy"
    sample.write_text(PROBES["三元条件表达式"]["src"], encoding="utf-8", newline="\n")
    canary = transpile(sample)
    can_body = (TMP / "out" / "canary.pyx")
    can_text = can_body.read_text(encoding="utf-8") if can_body.exists() else ""
    canary_missing = "__NEVER_PRESENT_9e1c__" not in can_text
    canary_caught = 1 if (canary["rc"] == 0 and canary_missing) else 0
    check("canary：必然缺失的证据必须被判为缺失（否则匹配器恒真）", canary_caught, 1,
          f"rc={canary['rc']} pyx_len={len(can_text)}")

    check("每行结论必须四档之一",
          set(r["verdict"] for r in results) <= {"verified", "claim-false", "unverified",
                                                 "claim-half-true"},
          True, "见 verdict")
    check("行数分类必须穷尽",
          len(verified) + len(claim_false) + len(half_true) + len(unverified), len(results),
          "verified+claim-false+claim-half-true+unverified")
    check("「名字在活路径上」不得被算成 verified",
          [r["n"] for r in verified if r.get("named_method_calls") == 0], [],
          "counted 行的 method 调用为 0 却进了 verified")
    if len(verified) + len(half_true) < 10:
        REFUSE.append(f"只有 {len(verified)}+{len(half_true)} 行拿到行为证据（合计 <10）"
                      f"⇒ 要么文档大面积不符，要么探针没写好")
    for r in claim_false + unverified + half_true:
        if not r["reason"]:
            REFUSE.append(f"r{r['n']} 判为 {r['verdict']} 却没写原因")

    doc = {"started": started, "doc": "SYNTAX/appendix-C-features.md:598《已实现的限制修复》",
           "face": "python -X utf8 -m cypyc.cli transpile …（真出 .pyx）",
           "rows_total": len(results), "rows": results,
           "verified": [r["n"] for r in verified], "claim_false": [r["n"] for r in claim_false],
           "claim_half_true": [r["n"] for r in half_true],
           "unverified": [r["n"] for r in unverified],
           "deviations": [{"n": r["n"], "doc_row": r["doc_row_verbatim"],
                           "verdict": r["verdict"], "reason": r["reason"]}
                          for r in results if r["verdict"] != "verified"],
           "canary_caught": canary_caught,
           "note": "行清单从冻结文档反解；`claim-false` 是「文档说已实现而调用面不成立」，"
                   "`claim-half-true` 是「行为成立但文档点名的私有方法不在活路径上」；"
                   "本环不改文档（冻结面）、不改产品码，只入账交裁决",
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"rows_total": len(results), "verified": len(verified),
                      "claim_false": [r["doc_row_verbatim"][:36] for r in claim_false],
                      "claim_half_true": [r["doc_row_verbatim"][:36] for r in half_true],
                      "unverified": [r["doc_row_verbatim"][:36] for r in unverified],
                      "canary_caught": canary_caught, "refuse": doc["refuse"]},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
