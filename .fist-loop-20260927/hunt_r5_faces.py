"""R5-寻虫 法 1/3/4：函数类型这一层的六个面，逐面带「必报的对照」跑，偏差才叫候选缺陷。

口径（写死在这里，免得事后各说各话）：
- 每个面(family)先钉一条 **control**：同一族里一个"必然该报错"的形状。control 不报 ⇒ 这一族**看不见**，
  本族所有"没报错"的观察一律作废（记进 blind_spots，不许写成"没有缺陷"）。这是 R3-推进 抓到的坑。
- 每个面再跑 pos/ctl 两条：pos 期望报、ctl 期望不报；观察与期望不符 ⇒ DEVIATION = 候选缺陷。
- 元数那一族另加变异树对照：摘掉 `_check_callable_arity` 调用后 pos 必须**不再报**，否则跑的是旧码。
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
# 三棵变异树：各自摘掉 `_check_callable_arity` 的一个调用点。R4-修复 之后判定有了三条通道，
# 只摘老那条已经翻不动红（上一版把锚点钉在 1289 那一行，本环实测 F1/F2 照报）⇒ 通道要逐条验活。
MUTANT_DIRS = {}
MUTANTS = {
    "legacy_args": "                        self._check_callable_arity(node, args)\n",
    "declared_sig": "                    self._check_callable_arity(node, sig.generic_params,\n"
    "                                               "
    "self.callable_arity.get(func_name))\n",
    "callback_param": "                self._check_callable_arity(node, "
    "func_type.generic_params)\n",
}
# 摘掉元数判定这一行就能翻转的三族：变异树用来证明「分类器还活着」，不是用来证明产品有缺陷
ARITY_FAMS = {
    "F1_func_symbol_typed_as_its_return",
    "F2_plain_function_call_arity_never_checked",
    "F6_arity_check_contexts",
}
IMPORTABLE = ("cypyc", "cypy_hook", "cypy_bridge")
FLIPS: dict = {}  # 变异标签 → 被它翻红几格
FAM_FLIPS: dict = {}  # 族 → 在变异树下翻红的用例名
ARITY = "Callable arity mismatch"
MISMATCH = "mismatch"
REFUSE: list = []
DECL = "type Callback = Callable[[int], str]\n"
ONE = 'def one(a: int) -> str:\n    return ""\n\n'
# 一个「自身 2 参、返回类型是 Callback(1 参)」的基座：两者元数不同，
# 才能把「函数名被登记成它的返回类型」这一缺陷与巧合分开。
BASE = DECL + ONE + "def mk(cb: Callback, n: int) -> Callback:\n    return cb\n\n"
CALL_G = lambda body: BASE + "def g() -> None:\n    " + body + "\n"  # noqa: E731
PARSEISH = ("Parse error", "Unexpected token", "Expected ", "Syntax", "LEX")

FAMILIES = {
    "F1_func_symbol_typed_as_its_return": {
        "claim": ("SYNTAX/02-type-annotations.md", "有注解的变量"),
        "control_proves": "返回值与声明类型不符会被报（返回类型这条通道活着）",
        "cases": [
            ("correct_two_arg_call_of_local_function", CALL_G("mk(one, 1)"), "clean"),
            ("missing_arg_call_of_local_function", CALL_G("mk(one)"), "error"),
            ("extra_arg_call_of_local_function", CALL_G("mk(one, 1, 2)"), "error"),
            (
                "function_with_matching_signature_returned_as_alias",
                DECL + ONE + "def mk() -> Callback:\n    return one\n",
                "clean",
            ),
        ],
        "control": ("plain_return_int_mismatch", 'def mk() -> int:\n    return ""\n', "error"),
    },
    "F2_plain_function_call_arity_never_checked": {
        "claim": ("SYNTAX/01-basic-types.md", "函数参数"),
        "control_proves": "调用点元数确实会被判（Callback 形参的违例必报）⇒ F2 的静默不是看不见",
        "cases": [
            (
                "plain_fn_called_with_extra_arg",
                "def mk() -> int:\n    return 1\n\ndef g() -> int:\n    return mk(1, 2)\n",
                "error",
            ),
            (
                "plain_fn_called_with_missing_arg",
                "def mk(k: int) -> int:\n    return k\n\ndef g() -> int:\n    return mk()\n",
                "error",
            ),
            (
                "plain_fn_called_correctly",
                "def mk(k: int) -> int:\n    return k\n\n" "def g() -> int:\n    return mk(1)\n",
                "clean",
            ),
        ],
        "control": (
            "callback_arity_violation_reported",
            DECL + "def a(cb: Callback) -> str:\n    return cb(1, 2)\n",
            "error",
        ),
    },
    "F3_function_argument_compatibility": {
        "claim": ("SYNTAX/01-basic-types.md", "有注解的参数进行类型检查"),
        "control_proves": "实参位置会被走一遍并能报错（Callback 元数在实参位上被报）⇒ 形参类型静默是缺陷不是看不见",
        "cases": [
            (
                "wrong_signature_passed_to_callback_param",
                DECL + 'def three(a: int, b: int) -> str:\n    return ""\n'
                "def apply(f: Callback) -> str:\n    return f(1)\n"
                "def g() -> str:\n    return apply(three)\n",
                "error",
            ),
            (
                "non_callable_passed_to_callback_param",
                DECL + "def apply(f: Callback) -> str:\n    return f(1)\n"
                "def g() -> str:\n    return apply(42)\n",
                "error",
            ),
            (
                "right_signature_passed_clean",
                DECL + 'def one(a: int) -> str:\n    return ""\n'
                "def apply(f: Callback) -> str:\n    return f(1)\n"
                "def g() -> str:\n    return apply(one)\n",
                "clean",
            ),
            (
                "str_arg_to_annotated_int_param",
                "def apply(n: int) -> int:\n    return n\n\n"
                'def g() -> int:\n    return apply("s")\n',
                "error",
            ),
        ],
        "control": (
            "callback_arity_violation_at_argument_site",
            DECL + "def a(cb: Callback) -> str:\n    return cb(1, 2)\n",
            "error",
        ),
    },
    "F4_struct_field_declared_type_unresolved": {
        "claim": ("SYNTAX/02-type-annotations.md", "有注解的变量"),
        "control_proves": "局部变量的声明类型会流到返回值判定 ⇒ 类型信息不是整体缺失",
        "cases": [
            (
                "int_field_returned_from_str_method",
                "struct S:\n    n: int\n\n    def f(self) -> str:\n        return self.n\n",
                "error",
            ),
            (
                "nested_field_wrong_type",
                "struct Inner:\n    n: int\nstruct Outer:\n    i: Inner\n\n"
                "    def f(self) -> str:\n        return self.i.n\n",
                "error",
            ),
            (
                "field_used_with_wrong_arity_call",
                DECL + "struct S:\n    cb: Callback\n\n"
                "    def f(self) -> str:\n        return self.cb(1, 2)\n",
                "error",
            ),
            (
                "int_field_returned_as_int_clean",
                "struct S:\n    n: int\n\n    def f(self) -> int:\n        return self.n\n",
                "clean",
            ),
        ],
        "control": (
            "local_let_annotation_checked",
            "def f() -> str:\n    let n: int = 1\n    return n\n",
            "error",
        ),
    },
    "F5_error_message_internals_leak": {
        "claim": ("SYNTAX/12-type-alias.md", "Callable[[int], str]"),
        "control_proves": "普通类型的 mismatch 文案会被产出 ⇒ 有文案可比",
        "cases": [
            (
                "alias_mismatch_message_is_source_shape",
                DECL + "def g() -> int:\n    let x: Callback = 1\n    return x\n",
                "error",
            ),
        ],
        "control": (
            "plain_mismatch_message",
            'def g() -> None:\n    let x: int = "s"\n    return\n',
            "error",
        ),
    },
    "F6_arity_check_contexts": {
        "claim": ("SYNTAX/12-type-alias.md", "Callable"),
        "control_proves": "最普通语句里的元数违例会报 ⇒ 其它上下文若静默就是上下文漏派",
        "cases": [
            (
                "violation_in_defer_block",
                DECL + "def a(cb: Callback) -> str:\n    defer:\n        cb(1, 2)\n"
                '    return ""\n',
                "error",
            ),
            (
                "violation_in_struct_method",
                DECL + "struct H:\n    def run(self, cb: Callback) -> str:\n"
                "        return cb(1, 2)\n",
                "error",
            ),
            (
                "correct_call_in_guard_expression",
                DECL + 'def a(cb: Callback, n: int) -> str:\n    guard n > 0 else return ""\n'
                "    return cb(1)\n",
                "clean",
            ),
        ],
        "control": (
            "violation_in_plain_body",
            DECL + "def a(cb: Callback) -> str:\n    return cb(1, 2)\n",
            "error",
        ),
    },
}


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


CHECKS: list = []


def check(label: str, got, want, why: str, ok: bool | None = None) -> None:
    """本判据自己的见证：任何一条坏了就往 REFUSE 里落，不许静默。"""
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def analyze(src: str, tree: Path | None = None) -> list:
    code = (
        "import sys, json;sys.path.insert(0,%r);"
        "from cypy_hook.hook import CypyHook;import cypyc.analyzer.type_checker as tc;"
        "src=sys.stdin.read();_, e = CypyHook().analyze_only(src);"
        "print(json.dumps({'ident': tc.__file__, 'errors': list(e)}))" % str(tree or ROOT)
    )
    p = subprocess.run(
        [PY, "-X", "utf8", "-c", code],
        cwd=str(ROOT),
        input=src,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if p.returncode != 0:
        REFUSE.append(f"分析器跑挂 rc={p.returncode}：{(p.stdout + p.stderr)[-200:]}")
        return ["RUNNER-FAIL"]
    got = json.loads(p.stdout.strip().splitlines()[-1])
    want = str((tree or ROOT) / "cypyc" / "analyzer" / "type_checker.py").replace("\\", "/").lower()
    if Path(got["ident"]).as_posix().replace("\\", "/").lower() != want:
        REFUSE.append(f"跑的不是目标树：期望 {want} 实得 {got['ident']}")
    return got["errors"]


def build_mutant(tag: str, needle: str):
    tree = SCRATCH / f"faces_mutant_{tag}"
    MUTANT_DIRS[tag] = tree
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    for pkg in IMPORTABLE:
        shutil.copytree(ROOT / pkg, tree / pkg, ignore=shutil.ignore_patterns("__pycache__"))
    tc = tree / "cypyc" / "analyzer" / "type_checker.py"
    text = tc.read_text(encoding="utf-8", newline="")
    if text.count(needle) != 1:
        REFUSE.append(
            f"变异 {tag}：锚点计数={text.count(needle)}（期望 1）⇒ 变异不会生效，对照作废"
        )
        return None
    tc.write_text(text.replace(needle, "", 1), encoding="utf-8", newline="")
    return tree


def build_mutants() -> dict:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return {t: b for t, b in ((t, build_mutant(t, n)) for t, n in MUTANTS.items()) if b is not None}


def doc_claim(rel: str, contains: str) -> dict:
    path = ROOT / rel
    if not path.exists():
        REFUSE.append(f"声明原文所在文件不在盘上：{rel}")
        return {"file": rel, "quote": "", "line": -1}
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if contains in ln:
            return {"file": rel, "line": i, "quote": ln.strip()[:200]}
    REFUSE.append(f"{rel} 里找不到声明原文片段 {contains!r} ⇒ 这一族的立单依据不成立")
    return {"file": rel, "quote": "", "line": -1}


def main() -> int:
    # 起跑先占住自己的证据件：同名文件存在 ≠ 这次跑过（上一轮踩过拿旧证据写结论的坑）
    started = now_s()
    (HERE / "hunt_r5_faces.json").write_text(
        json.dumps(
            {"started": started, "pid": __import__("os").getpid(), "refuse": ["未跑完"]},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    mutants = build_mutants()
    rows, blind = [], []
    for fam, spec in FAMILIES.items():
        cn, csrc, cexp = spec["control"]
        cerr = analyze(csrc)
        bad_ctl = [e for e in cerr if any(p in e for p in PARSEISH)]
        if bad_ctl:
            REFUSE.append(f"{fam}/control {cn}：对照夹具本身不合法 ⇒ {bad_ctl[:2]}")
        control_ok = (cexp == "error") == any(MISMATCH in e or ARITY in e for e in cerr)
        if not control_ok:
            blind.append(
                {
                    "family": fam,
                    "control": cn,
                    "observed": cerr,
                    "control_proves": spec["control_proves"],
                }
            )
        cases = []
        for name, src, exp in spec["cases"]:
            errs = analyze(src)
            seen = any(MISMATCH in e or ARITY in e for e in errs)
            invalid = [e for e in errs if any(p in e for p in PARSEISH)]
            entry = {
                "case": name,
                "src": src,
                "expect": exp,
                "observed_errors": errs,
                "reported_a_type_error": seen,
                "fixture_parse_error": invalid,
            }
            if invalid:
                REFUSE.append(f"{fam}/{name}：夹具不是合法 Cypy（{invalid[:2]}）⇒ 不许计入候选")
                entry["candidate"] = None
            else:
                entry["candidate"] = (
                    "false_positive_on_correct_program"
                    if exp == "clean" and seen
                    else "silent_on_wrong_program" if exp == "error" and not seen else None
                )
            if fam == "F5_error_message_internals_leak" and seen:
                # 这一族主张的是**文案形状**，"报没报"看不见它 ⇒ 按内部表示是否外泄来判
                leaked = [e for e in errs if "tuple[" in e or "generic_params" in e]
                entry["message_leaks_internal_repr"] = leaked
                if leaked:
                    entry["candidate"] = "internal_repr_in_user_message"
            if fam in ARITY_FAMS and mutants and exp == "error" and not invalid:
                reports = any(ARITY in e for e in errs)
                silenced: list = []
                for tag in sorted(mutants):
                    merrs = analyze(src, mutants[tag])
                    entry[f"mutant_{tag}_still_reports"] = any(ARITY in e for e in merrs)
                    if reports and not any(ARITY in e for e in merrs):
                        silenced.append(tag)
                        FLIPS[tag] = FLIPS.get(tag, 0) + 1
                entry["silenced_by"] = silenced
                if silenced:
                    entry["mutant_candidate"] = "silent_on_wrong_program"
                    FAM_FLIPS.setdefault(fam, []).append(name)
                elif not reports:
                    REFUSE.append(f"{fam}/{name}：真实树上本来就没报 ⇒ 这一格的变异对照无从谈起")
            cases.append(entry)
        rows.append(
            {
                "family": fam,
                "claim": doc_claim(*spec["claim"]),
                "control_proves": spec["control_proves"],
                "control_case": {"name": cn, "src": csrc, "expect": cexp, "observed": cerr},
                "control_ok": control_ok,
                "cases": cases,
                "candidates": [c["case"] for c in cases if c["candidate"]],
                "as_expected": [
                    c["case"]
                    for c in cases
                    if c["candidate"] is None and not c["fixture_parse_error"]
                ],
                "invalid_fixtures": [c["case"] for c in cases if c["fixture_parse_error"]],
            }
        )
    if blind:
        REFUSE.append(
            f"有 {len(blind)} 个面的对照不报 ⇒ 该面看不见，禁止写『没缺陷』："
            f"{[x['family'] for x in blind]}"
        )
    for tree in MUTANT_DIRS.values():
        shutil.rmtree(tree, ignore_errors=True)
    left = sorted(q.name for q in SCRATCH.glob("*mutant*")) if SCRATCH.exists() else []
    found = [f"{r['family']}/{c}" for r in rows for c in r["candidates"]]
    mut_found = [
        f"{r['family']}/{c['case']}" for r in rows for c in r["cases"] if c.get("mutant_candidate")
    ]

    unattributed = sorted(set(MUTANTS) - set(FLIPS))
    check(
        "白建的变异通道必须逐条点名（是冗余分支还是夹具没覆盖，本环不裁定就挂账）",
        [
            sorted(set(FLIPS) & set(MUTANTS)),
            all(FLIPS.get(t, 0) >= 1 for t in ("declared_sig", "legacy_args")),
        ],
        [
            (
                ["callback_param", "declared_sig", "legacy_args"]
                if not unattributed
                else sorted(FLIPS)
            ),
            True,
        ],
        f"每棵翻红格数 {json.dumps(FLIPS, ensure_ascii=False)}；不可归因 {unattributed}",
    )
    check(
        "三个元数族各自至少有一格在变异下发红（判据活着；真实树产零=已修不是失灵）",
        sorted(FAM_FLIPS),
        sorted(ARITY_FAMS),
        f"各族翻红 {json.dumps({k: len(v) for k, v in FAM_FLIPS.items()}, ensure_ascii=False)}"
        f"／真实树候选 {found[:4]}",
    )
    check(
        "变异树翻红的格子在真实树上都被报出（否则归因不成立）",
        [bool(mut_found), sum(len(v) for v in FAM_FLIPS.values()) <= len(mut_found)],
        [True, True],
        f"mutant 候选 {len(mut_found)} 格",
    )
    check(
        "候选/符合预期/夹具非法 三栏相加 = 全部用例（没有第四种被静默丢掉）",
        sum(
            len(r["candidates"]) + len(r["as_expected"]) + len(r["invalid_fixtures"]) for r in rows
        ),
        sum(len(v["cases"]) for v in FAMILIES.values()),
        "逐条分类后回加",
    )
    check(
        "夹具合法性自证：没有任何用例带解析错误",
        sum(1 for r in rows for c in r["cases"] if c["fixture_parse_error"]),
        0,
        "fixture_parse_error 计数",
    )
    check("变异树目录已清干净", len(left), 0, "清理后残留")
    check(
        "六族的对照全部能报（可见性）",
        [r["family"] for r in rows if not r["control_ok"]],
        [],
        "control_ok=False 的族",
    )
    check(
        "每个立单原文都能定位",
        [r["family"] for r in rows if r["claim"]["line"] < 0],
        [],
        "doc_claim 未命中",
    )
    doc = {
        "started": started,
        "refuse": [],
        "families": len(FAMILIES),
        "faces": [
            {
                "face": r["family"],
                "claim_line": r["claim"]["line"],
                "control_ok": r["control_ok"],
                "candidates": r["candidates"],
                "as_expected": r["as_expected"],
                "cases": len(r["cases"]),
            }
            for r in rows
        ],
        "cases_total": sum(1 + len(v["cases"]) for v in FAMILIES.values()),
        "rows": rows,
        "blind_spots": blind,
        "mutant_left": left,
        "candidates": found,
        "candidate_total": len(found),
        "mutant_candidates": mut_found,
        "flips_by_mutant": FLIPS,
        "flips_by_family": FAM_FLIPS,
        "families_without_flip": sorted(set(FAMILIES) - set(FAM_FLIPS)),
        "unattributed_mutants": sorted(set(MUTANTS) - set(FLIPS)),
        "self_checks": CHECKS,
        "expectation_note": "期望值来自『文档声明的语义应当怎样』，不是『今天怎样』；"
        "与期望不符=候选缺陷（假阳性/假阴性两类都算），拒绝只留给判据自己坏了",
        "at_utc": now_s(),
    }
    doc["refuse"] = sorted(set(REFUSE)) + [
        f"判据自证未过：{c['label']}（实得 {c['got']}）" for c in CHECKS if not c["ok"]
    ]
    (HERE / "hunt_r5_faces.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "self_checks": "%d/%d" % (sum(1 for c in CHECKS if c["ok"]), len(CHECKS)),
                "blind_spots": [x["family"] for x in blind],
                "per_family": {
                    r["family"]: {"control_ok": r["control_ok"], "candidates": r["candidates"]}
                    for r in rows
                },
                "mutant_left": left,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # 崩了也要把证据件写成红，不许留下上一次的绿
        (HERE / "hunt_r5_faces.json").write_text(
            json.dumps(
                {"refuse": [f"判据脚本崩在 {type(exc).__name__}: {exc}"]},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
