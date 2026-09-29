"""R3-推进 法 1/3/5 的证据件：元数判定实测、codegen 产物逐字差分、半径外形状点名。

每格都带**自证**：违例必报与正确调用必不报是成对的（只有一边等于没判），
产物差分必须点名"哪些行允许不同"（时间戳两行），半径外的形状逐条给**实测原文**而不是印象。
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
AD = HERE / "tmp_advance"
BEFORE_DIR = AD / "pyx_before"
AFTER_DIR = AD / "pyx_after"
SNAPSHOT_FILES = ["cypyc/analyzer/type_checker.py"]
TIME_LINES = ("__compile_time__", "__generated_at__")
VIOLATION_CASES = {
    "one_expected_two_given": "def apply(f: Callable[[int], str]) -> str:\n    return f(1, 2)\n",
    "one_expected_zero_given": "def apply(f: Callable[[int], str]) -> str:\n    return f()\n",
    "two_expected_one_given": "def run(f: Callable[[int, str], bool], a: int) -> bool:\n    return f(a)\n",
    "zero_expected_one_given": "def run(f: Callable[[], int]) -> int:\n    return f(1)\n",
    "alias_one_expected_two_given": (
        "type Callback = Callable[[int], str]\ndef process(cb: Callback):\n    return cb(1, 2)\n"),
}
CLEAN_CASES = {
    "one_expected_one_given": "def apply(f: Callable[[int], str]) -> str:\n    return f(1)\n",
    "two_expected_two_given": (
        "def run(f: Callable[[int, str], bool], a: int, b: str) -> bool:\n    return f(a, b)\n"),
    "zero_expected_zero_given": "def run(f: Callable[[], int]) -> int:\n    return f()\n",
    "nested_form_matched": ("def a(f: Callable[[Callable[[int], int]], int]) -> int:\n"
                             "    return f(1)\n"),
}
SKIP_CASES = {
    "bare_Callable": "def a(f: Callable) -> int:\n    return f(1, 2)\n",
    "one_slot_Callable": "def a(f: Callable[int]) -> int:\n    return f(1, 2)\n",
    "keyword_args_call": "def apply(f: Callable[[int], str]) -> str:\n    return f(x=1)\n",
    "tuple_literal_arg": "def apply(f: Callable[[int], str]) -> str:\n    return f((1, 2))\n",
}
COGEN_SOURCES = ["alias_use_param", "direct_annot", "ctl_callable_arity_bad",
                 "examples/demos/data_structures/type_alias_demo.cypy",
                 "examples/demos/boundary_cases/combined_features.cypy"]
# 这一档是**故意的违例夹具**：改前静默出码（pyx_before 里有它的产物、开工前件里分析层零报错），
# 改后必须被新判定挡住。把它混进"必须能出码"的集合里就是判据写错了，而不是产品坏了。
REFUSED_EXPECTED = {"ctl_callable_arity_bad": "Callable arity mismatch"}
ARITY_RE = re.compile(r"Callable arity mismatch: expected (\d+), got (\d+) at \d+:\d+")
REFUSE: list = []


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sh(cmd, timeout=600):
    p = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")


def analyze(src: str) -> list:
    sys.path.insert(0, str(ROOT))
    from cypy_hook.hook import CypyHook
    _, errors = CypyHook().analyze_only(src)
    return list(errors)


def arity() -> dict:
    viol = {k: analyze(v) for k, v in VIOLATION_CASES.items()}
    clean = {k: analyze(v) for k, v in CLEAN_CASES.items()}
    skip = {k: analyze(v) for k, v in SKIP_CASES.items()}
    miss = [k for k, errs in viol.items() if not ARITY_RE.search("; ".join(errs))]
    if miss:
        REFUSE.append(f"违例案例没报出 arity 错 ⇒ 判定没落地：{miss}")
    noisy = {k: v for k, v in clean.items() if any("arity" in e for e in v)}
    if noisy:
        REFUSE.append(f"正确调用被误判（成对锁的另一边必须静默）：{ {k: v for k, v in noisy.items()} }")
    noisy_skip = {k: v for k, v in skip.items() if any("arity" in e for e in v)}
    if noisy_skip:
        REFUSE.append(f"形状不认识/关键字调用本该跳过却在报错：{ {k: v for k, v in noisy_skip.items()} }")
    # 报错必须带位点，否则人无法定位
    no_locus = [k for k, errs in viol.items()
                if not any(re.search(r" at \d+:\d+$", e) for e in errs if "arity" in e)]
    if no_locus:
        REFUSE.append(f"arity 错缺位点（行:列）：{no_locus}")
    both = analyze("def apply(f: Callable[[int], str]) -> int:\n    return f(1, 2)\n")
    if not (any("arity" in e for e in both) and any("Return type mismatch" in e for e in both)):
        REFUSE.append(f"元数错与返回类型错没有共存（早退吞掉了一条）：{both}")
    return {"violation_cases": viol, "violation_total": len(viol),
            "clean_cases_green": all(not any("arity" in e for e in v) for v in clean.values()),
            "clean_cases": clean, "skipped_shapes": skip,
            "cases_with_locus": len(viol) - len(no_locus),
            "coexist_with_return_error": both,
            "measured_message": next(iter(viol.values()))[0] if viol else "",
            "type_checker_sha_now": hashlib.sha256(
                (ROOT / SNAPSHOT_FILES[0]).read_bytes()).hexdigest()[:16],
            "at_utc": now_s()}


def strip_time(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not any(t in ln for t in TIME_LINES))


def codegen_diff() -> dict:
    AFTER_DIR.mkdir(parents=True, exist_ok=True)
    pre = json.loads((HERE / "advance_r3_pre_baseline.json").read_text(encoding="utf-8"))
    rows = []
    refused_rows = []
    for rel in COGEN_SOURCES:
        src = (AD / f"{rel}.cypy") if "/" not in rel else (ROOT / rel)
        if not src.exists():
            REFUSE.append(f"产物差分的源不在盘上：{src}")
            continue
        stem = src.stem
        before = BEFORE_DIR / f"{stem}.pyx"
        if not before.exists():
            REFUSE.append(f"缺改前产物快照 {stem}.pyx ⇒ 无法证明 codegen 没动")
            continue
        rc, out = sh([PY, "-X", "utf8", "-m", "cypyc.cli", "transpile", str(src),
                      "-o", str(AFTER_DIR)], 300)
        after = AFTER_DIR / f"{stem}.pyx"
        if rel in REFUSED_EXPECTED:
            needle = REFUSED_EXPECTED[rel]
            before_silent = pre["analyzer_errors_before"].get(stem)
            if rc == 0:
                REFUSE.append(f"违例夹具 {rel} 改后居然仍出码 ⇒ 新判定没作用到 CLI 这条路上")
                continue
            if needle not in out:
                REFUSE.append(f"违例夹具 {rel} 是被别的错误挡住的（不是 {needle}）：{out.strip()[-200:]}")
                continue
            if before_silent != []:
                REFUSE.append(f"违例夹具 {rel} 改前就不是静默通过（开工前件记 {before_silent}）⇒ 对表主张不成立")
                continue
            refused_rows.append({"source": rel, "refusal_needle": needle,
                                 "before_artifact_bytes": before.stat().st_size,
                                 "after_artifact_written": after.exists(),
                                 "refusal_excerpt": out.strip()[-160:]})
            continue
        if rc != 0 or not after.exists():
            REFUSE.append(f"改后 transpile 失败（本环只该加分析层判定）：{rel} rc={rc} "
                          f"{out.strip()[-160:]}")
            continue
        b, a = strip_time(before.read_text(encoding="utf-8", errors="replace")), \
            strip_time(after.read_text(encoding="utf-8", errors="replace"))
        diff = [ln for ln in difflib.unified_diff(b.splitlines(), a.splitlines(), n=0)
                if ln[:1] in ("+", "-") and ln[:3] not in ("+++", "---")]
        rows.append({"source": rel if "/" in rel else src.name, "artifact": f"{stem}.pyx",
                     "diff_lines": len(diff), "identical_after_strip": not diff,
                     "diff_sample": diff[:4],
                     "kept_time_lines": sum(1 for ln in before.read_text(
                         encoding="utf-8", errors="replace").splitlines()
                         if any(t in ln for t in TIME_LINES))})
    bad = [r["source"] for r in rows if not r["identical_after_strip"]]
    if bad:
        REFUSE.append(f"codegen 产物被本环改动（主张是逐字不动）：{bad}")
    for r in rows:
        if r["kept_time_lines"] != 2:
            REFUSE.append(f"{r['source']} 的时间戳行数不是 2 ⇒ 差分口径（剥哪两行）漂了")
    if len(refused_rows) != len(REFUSED_EXPECTED):
        REFUSE.append(f"预期被挡住的夹具应有 {len(REFUSED_EXPECTED)} 档、实际分类出 {len(refused_rows)} 档"
                      "⇒ 分错栏就是漏检")
    if len(rows) + len(refused_rows) != len(COGEN_SOURCES):
        REFUSE.append(f"产物差分只覆盖 {len(rows) + len(refused_rows)}/{len(COGEN_SOURCES)} 档 ⇒ 有源没进任何一栏")
    return {"cases": rows, "all_textual_identical": not bad and bool(rows),
            "identical_total": len(rows),
            "refused_by_new_check": refused_rows,
            "refused_expected_total": len(REFUSED_EXPECTED),
            "stripped_line_markers": list(TIME_LINES),
            "sources_scanned": len(rows) + len(refused_rows), "at_utc": now_s()}


def try_parse(src: str) -> str:
    """在进程内解析，把失败形状原样返回（不经过 shell、不重打转义）。"""
    sys.path.insert(0, str(ROOT))
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser
    try:
        Parser(Lexer(src).tokenize()).parse()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return "parsed ok"


def declared_variadic_forms() -> list:
    hits = []
    for d in ("SYNTAX", "PROJECT-SPEC", "docs"):
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if "Callable[..." in ln:
                    hits.append(f"{path.relative_to(ROOT)}:{i}: {ln.strip()[:120]}")
    return hits


def scope_face() -> dict:
    vari_text = try_parse("def a(f: Callable[..., int]) -> int:\n    return f(1)\n")
    declared_variadic = declared_variadic_forms()
    alias_pyx = (AFTER_DIR / "alias_use_param.pyx")
    alias_sig = ""
    if alias_pyx.exists():
        text = alias_pyx.read_text(encoding="utf-8", errors="replace")
        alias_sig = next((ln for ln in text.splitlines() if ln.startswith("def process")), "")
    frozen_rows = []
    for rel, pat in (("SYNTAX/appendix-C-features.md", r"Callable\[\[T\], R\]"),
                     ("SYNTAX/12-type-alias.md", r"type Callback = Callable")):
        for ln in (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines():
            if re.search(pat, ln):
                frozen_rows.append({"file": rel, "line": ln.strip()[:180]})
    if len(frozen_rows) < 2:
        REFUSE.append(f"冻结文档声明行取不全（半径主张要贴原文）：{frozen_rows}")
    outside = {
        "alias_signature_collapses_to_object": {
            "observed_emitted_signature": alias_sig,
            "claim": "类型别名在**产物**签名里塌成无标注（分析层已能顺着别名查元数，codegen 层未等距传递）",
            "why_not_this_round": "改产物签名要动 codegen 的类型映射，属新语义，不在『已声明未实现里挑最小的那件』范围内"},
        "variadic_Callable_ellipsis_not_parsed": {
            "observed": vari_text,
            "declared_in_docs": bool(declared_variadic),
            "grep_of_declaration": declared_variadic[:3],
            "why_not_this_round": "SYNTAX/PROJECT-SPEC/docs 里搜不到 `Callable[...]` 变长写法 ⇒ 它不是『已声明』，"
                                  "本环半径只覆盖文档声明过的 `Callable[[T], R]`"},
        "argument_type_check_not_implemented": {
            "observed": "元数一致但实参类型不符（如 `f('a')` 对 `Callable[[int], str]`）当前不报错",
            "why_not_this_round": "需要先把赋值处的类型兼容级联抽成共用谓词（现在散在 type_checker.py 五六个分支里），"
                                  "属重构决定，交裁决后再做"},
    }
    for k, v in outside.items():
        if not any(str(val) for key, val in v.items() if key.startswith("observed")):
            REFUSE.append(f"半径外条目 {k} 没有实测值 ⇒ 不能凭印象挂账")
    argt = analyze("def a(f: Callable[[int], str]) -> str:\n    return f('x')\n")
    outside["argument_type_check_not_implemented"]["measured_errors"] = argt
    # 挂账理由的两条负面主张也要当场验，不能续写上一环的措辞
    if declared_variadic:
        REFUSE.append(f"文档里搜到了变长写法 ⇒ 挂账理由『未声明』不成立：{declared_variadic[:2]}")
    if "DOT_DOT" not in vari_text:
        REFUSE.append(f"变长写法没被 parser 拒（实测 {vari_text[:80]}）⇒ 挂账理由『词法不认』不成立")
    if any("arity" in e for e in argt):
        REFUSE.append("实参类型不符这条本该只报元数（元数是对的），却报出 arity ⇒ 判定过宽")
    return {"outside_radius": outside,
            "outside_total": len(outside),
            "frozen_doc_rows": frozen_rows,
            "frozen_docs_modified": 0,
            "variadic_probe_outcome": vari_text,
            "note": "本环不碰 SYNTAX/PROJECT-SPEC：appendix-C 那行『尚未实现』在实现后变陈旧，"
                    "改它属冻结面动作 ⇒ 只点名交人工，不自己动刀",
            "at_utc": now_s()}


def main() -> int:
    AD.mkdir(exist_ok=True)
    doc = {"refuse": [], "started_at_utc": now_s()}
    doc["arity"] = arity()
    doc["codegen_diff"] = codegen_diff()
    doc["scope_face"] = scope_face()
    doc["refuse"] = REFUSE
    doc["finished_at_utc"] = now_s()
    for rel, key in (("advance_r3_arity.json", "arity"),
                     ("advance_r3_codegen_diff.json", "codegen_diff"),
                     ("advance_r3_scope_face.json", "scope_face")):
        payload = dict(doc[key])
        payload["refuse"] = REFUSE
        payload["lane_files"] = SNAPSHOT_FILES
        payload["type_checker_sha_before"] = json.loads(
            (HERE / "advance_r3_pre_baseline.json").read_text(encoding="utf-8")
        )["type_checker_sha_before"]
        (HERE / rel).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE,
                      "arity": {k: doc["arity"][k] for k in
                                ("violation_total", "clean_cases_green", "cases_with_locus",
                                 "measured_message")},
                      "codegen": {k: doc["codegen_diff"][k] for k in
                                  ("sources_scanned", "all_textual_identical")},
                      "scope": {k: doc["scope_face"][k] for k in
                                ("outside_total", "frozen_doc_rows")}},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
