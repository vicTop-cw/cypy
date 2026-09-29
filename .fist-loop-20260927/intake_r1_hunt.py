#!/usr/bin/env python3
"""R1-寻虫 · 入账件：把 5 条已确诊缺陷逐条 report_bug(publish_task=true) 并建三向对照。

每条在入账前当场重跑一次取证据（产物片段 / 诊断 / CLI rc），证据不成立就不入账——
禁止「上一段会话里见过」当成本件的复现。文案只用相对 Cypy 根的路径（路径安全红线）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
HUNTS = HERE / "hunts"

from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402
from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402

EXTRACTOR = """struct Email:
    address: str

    def __unapply__(self) -> tuple<str, str> | None:
        if '@' in self.address:
            parts = self.address.split('@')
            return (parts[0], parts[1])
        return None

def classify(e: Email) -> str:
    match e:
        case Email(user, domain):
            return user
        case _:
            return "none"

def main() -> int:
    print(classify(Email("a@b.com")))
    return 0

if __name__ == "__main__":
    main()
"""
NO_UNAPPLY = """struct Email:
    address: str

def classify(e: Email) -> str:
    match e:
        case Email(user, domain):
            return user
        case _:
            return "none"
"""


def gen(src: str) -> dict:
    out = {"diagnostics": [], "artifact": "", "exception": None}
    try:
        ast = Parser(list(Lexer(src).tokenize())).parse()
        tc = TypeChecker()
        tc.check(ast)
        out["diagnostics"] = [str(d) for d in (getattr(tc, "errors", None) or [])]
        out["artifact"] = CythonGenerator().generate(ast)
    except BaseException as exc:  # noqa: BLE001
        out["exception"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


def cli_run(sample: Path) -> dict:
    r = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "cypyc",
            "run",
            str(sample.relative_to(ROOT).as_posix()),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
    )
    return {"rc": r.returncode, "tail": (r.stdout + r.stderr).strip().splitlines()[-3:]}


def main() -> int:
    HUNTS.mkdir(parents=True, exist_ok=True)
    samples = {
        "hunt_e": (HUNTS / "hunt_e_extractor_positional.cypy", EXTRACTOR),
        "hunt_f": (HUNTS / "hunt_f_pattern_binding_int.cypy", NO_UNAPPLY),
    }
    for path, src in samples.values():
        path.write_text(src, encoding="utf-8", newline="\n")

    ev = {}
    ev["hunt_e_gen"] = gen(EXTRACTOR)
    ev["hunt_f_gen"] = gen(NO_UNAPPLY)
    ev["hunt_e_cli"] = cli_run(samples["hunt_e"][0])
    ev["hunt_a_cli"] = cli_run(HUNTS / "adv_03_unterminated_string.cypy")
    ev["hunt_c_cli"] = cli_run(HUNTS / "adv_05_deep_nesting.cypy")
    ev["hunt_c_text"] = " ".join(ev["hunt_c_cli"]["tail"])
    ev["hunt_b_gen"] = gen((HUNTS / "adv_10_slice_step_zero.cypy").read_text(encoding="utf-8"))
    e_lines = [l for l in ev["hunt_e_gen"]["artifact"].splitlines() if re.search(r"\.__f\d", l)]
    extractor_called = any(".__unapply__(" in l for l in ev["hunt_e_gen"]["artifact"].splitlines())
    b_lines = [l for l in ev["hunt_b_gen"]["artifact"].splitlines() if "Constant(" in l]
    (HUNTS / "hunt_evidence.json").write_text(
        json.dumps(
            {
                "hunt_e_binding_lines": e_lines,
                "hunt_e_extractor_called": extractor_called,
                "hunt_e_diagnostics": ev["hunt_e_gen"]["diagnostics"],
                "hunt_e_cli": ev["hunt_e_cli"],
                "hunt_f_diagnostics": ev["hunt_f_gen"]["diagnostics"],
                "hunt_a_cli": ev["hunt_a_cli"],
                "hunt_a_artifact_swallows_return": any(
                    "return 0" in l and "s: str" in l
                    for l in gen(
                        (HUNTS / "adv_03_unterminated_string.cypy").read_text(encoding="utf-8")
                    )["artifact"].splitlines()
                ),
                "hunt_b_lines": b_lines,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
        newline="\n",
    )

    # 入账前的硬门：每条各自的证据必须当场成立，否则这条不入账并打印缺什么。
    need = {
        "BUG-E": bool(e_lines) and not extractor_called,
        "BUG-F": any("Return type mismatch" in d for d in ev["hunt_f_gen"]["diagnostics"]),
        "BUG-A": ev["hunt_a_cli"]["rc"] == 0,
        "BUG-B": bool(b_lines),
        "BUG-C": ("读取文件错误" in ev["hunt_c_text"] and "recursion" in ev["hunt_c_text"].lower()),
    }
    print(json.dumps({k: bool(v) for k, v in need.items()}, ensure_ascii=False))
    print("hunt_e 绑定行:", e_lines[:4])
    print("hunt_f 诊断:", ev["hunt_f_gen"]["diagnostics"][:2])
    print("hunt_b 泄漏行:", b_lines[:2])
    print("hunt_a cli:", ev["hunt_a_cli"])

    items = [
        (
            "BUG-A",
            "[对抗样例:词法] lexer 对未闭合字符串不诊断，静默吞掉后续源码",
            "复现：python -X utf8 -m cypyc run .fist-loop-20260927/hunts/adv_03_unterminated_string.cypy"
            '（样例 3 行：s: str = "abc 未闭合，后面还有 return 0）\n'
            f"实际：rc={ev['hunt_a_cli']['rc']}，CLI 打 [OK] Transpiled successfully；产物里写成 "
            "s: str = 'abc\\n    return 0\\n'——整条 return 语句被当字符串内容吃掉，main 变成隐式返回 None。\n"
            "期望：未闭合字符串必须报词法错误（带行列）并非零退出。宁可拒绝，不可静默改语义。\n"
            "证据：.fist-loop-20260927/hunts/adv_03_unterminated_string.cypy、adv_r1.json(adv_03)、"
            "hunt_evidence.json(hunt_a_cli / hunt_a_artifact_swallows_return)",
        ),
        (
            "BUG-B",
            "[对抗样例:类型标注] 非法标注形态把 AST 节点的 repr 写进产物（xs: Constant(line=2, col=9)）",
            "复现：python -X utf8 -m cypyc transpile "
            ".fist-loop-20260927/hunts/adv_10_slice_step_zero.cypy -o .fist-loop-20260927/cliout --emit-cython\n"
            f"实际：产物出现 {' | '.join(b_lines[:1])!r}——把 ASTNode 的 Python repr 当成类型名发进 Cython 源，"
            "该 .pyx 必编译失败；adv_19 同型（空列表）。\n"
            "期望：SYNTAX/02 规定的列表写法是 list<int>；`[int]` 之类未文档化形态必须诊断（带行列），"
            "任何情况下不得把内部节点 repr 落进产物。\n"
            "证据：.fist-loop-20260927/hunts/adv_10_slice_step_zero.cypy、adv_19_negative_index_const.cypy、"
            "hunt_evidence.json(hunt_b_lines)、cliout/adv_10_slice_step_zero.pyx",
        ),
        (
            "BUG-C",
            "[读码+对抗] parse/lex 阶段的一切异常在用户面被归入「读取文件错误」，深嵌套 RecursionError 同桶且无行列",
            '站点：cypy_hook/hook.py:413 的 except 分支把整段 read+parse 的异常统一写成 f"读取文件错误: {e}"。\n'
            f"实际：adv_07/16/18/20（语法诊断）与 adv_05（200 层括号 RecursionError，parser.py:3314 _parse_call）"
            f"在 CLI 上都被显示成「读取文件错误」；adv_05 本次实跑 rc={ev['hunt_c_cli']['rc']}，"
            f"末三行 {ev['hunt_c_cli']['tail']}——既没有源码行列，也把解析失败说成读文件失败。\n"
            "期望：读文件的 I/O 失败与语法/语义诊断分桶；深嵌套应有深度守卫并给出带行列的诊断。\n"
            "证据：.fist-loop-20260927/hunts/adv_r1.json（adv_05/07/16/18/20 五条 trace_tail）、"
            ".fist-loop-20260927/cliout/、cypyc/parser/parser.py:901/:880/:3314",
        ),
        (
            "BUG-E",
            "[转结确诊:模式匹配] 位置模式不调用 __unapply__，产物访问不存在的 __f0/__f1",
            "复现：python -X utf8 -m cypyc transpile "
            ".fist-loop-20260927/hunts/hunt_e_extractor_positional.cypy -o .fist-loop-20260927/cliout --emit-cython\n"
            f"实际：产物里是 {' ; '.join(l.strip() for l in e_lines[:2])!r}——Email 只有 address 一个字段，"
            '生成器（cython_generator.py:1619 field_name = fields[i] if i < len(fields) else f"__f{i}"）'
            "在该场景下 fields 为空，两个绑定名都落到 __f{i} 占位，既不调用 __unapply__，也不访问任何真实字段。\n"
            "期望：SYNTAX/17-pattern-matching.md:201-215 与 :269-278 —— __unapply__ 优先，"
            "case Email(a, b) 应调提取器并按返回元组逐位置绑定。\n"
            f"证据：.fist-loop-20260927/hunts/hunt_e_extractor_positional.cypy、hunt_evidence.json"
            f"(hunt_e_binding_lines)、run rc={ev['hunt_e_cli']['rc']}（被 BUG-F 的假阳性诊断挡在前面）",
        ),
        (
            "BUG-F",
            "[类型检查假阳性] 位置模式把绑定名判成 int，有效程序被判「Return type mismatch」并非零退出",
            "复现：python -X utf8 -m cypyc run "
            ".fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy\n"
            f"实际：诊断 {ev['hunt_f_gen']['diagnostics'][:1]}——classify 的两个 return 都是 str，"
            "位置模式绑定的 user 被当成 int，且位置指向 case 行而非 return 行；"
            f"run rc={ev['hunt_e_cli']['rc']}（同类程序被拒）。\n"
            "期望：结构体位置解构的绑定名类型应取字段/提取器元组的对应位置类型；"
            "无 __unapply__ 的 struct（本例）也不该给出与源码不符的 int 判定。\n"
            "证据：.fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy、hunt_evidence.json"
            "(hunt_f_diagnostics)",
        ),
    ]
    missing = [k for k, ok in need.items() if not ok]
    if missing:
        print(f"SKIP 入账（证据不成立）: {missing}")
    c = lfist_lib.Client(timeout=180)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    mapping = []
    for key, summary, detail in items:
        if key in missing:
            continue
        res = c.call(
            "report_bug",
            {
                "project_dir": ".",
                "summary": summary,
                "detail": detail,
                "severity": "high",
                "reported_by": "cypy-loop-hunter",
                "publish_task": True,
                "now": lfist_lib.utc_now(),
            },
        )
        mapping.append(
            {
                "key": key,
                "bug_id": res.get("bug_id"),
                "task_id": res.get("task_id"),
                "status": res.get("status"),
                "path": res.get("resolved_path"),
                "samples": summary.split("]")[0],
            }
        )
        print(json.dumps(mapping[-1], ensure_ascii=False))
    c.close()
    (HERE / "intake_r1_hunt.json").write_text(
        json.dumps(
            {"mapping": mapping, "skipped_for_missing_evidence": missing},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    bad = [m for m in mapping if not (m["bug_id"] and m["task_id"])]
    if bad:
        print(f"REFUSE — 这些入账没拿到 bug id + 修复单号: {bad}")
        return 1
    print(f"OK 入账 {len(mapping)} 条：{[m['bug_id'] for m in mapping]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
