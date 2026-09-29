"""R1-打磨 law2/law5 的落地探针：把「形状可疑」跑到**调用面**，能证才写。

三条都要有可复算的输出，不许从代码形状外推（历史上这么报过错现场）：

 P1 重复定义的测试类会不会吞掉前一组用例：`import` 那个模块，比较
    `vars(mod)['TestPointerBoundary'].__code__.co_firstlineno` 与源码里两处 `class` 的行号，
    并数两处各自的 `test_` 方法数 ⇒ 若线上只有一份生效，前一份的用例就是**静默不跑**。
 P2 产品码里重复的 `_visit_*`：拿类的 `__dict__[name].__code__.co_firstlineno` 看生效的是哪一处，
    再数被遮掉那份的语句数 ⇒ 断言「有一处实现是死代码」，不断言「哪份才是对的」（那要人裁决）。
 P3 skip 标记的定性：把被 skip 的测试函数**绕过标记直接调用**，看它到底过不过 ⇒
    过了就是「掩盖失效」（标记该摘），不过就是「真失效但被 skip 藏着」（转缺陷单）。
    计数自证：实际试跑的条数必须等于扫到的 skip 条数，不等就报 parse_broken。
"""

from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
sys.path.insert(0, str(ROOT))

OUT = HERE / "polish_probe_r1.json"
DOC: dict = {"refuse": []}


def class_sites(rel: str, name: str) -> list:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8", errors="replace"))
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            tests = [
                f.name
                for f in node.body
                if isinstance(f, ast.FunctionDef) and f.name.startswith("test_")
            ]
            sites.append({"first_line": node.lineno, "n_methods": len(tests), "methods": tests})
    return sites


def p1() -> None:
    rel = "tests/test_boundary_comprehensive.py"
    import importlib

    mod = importlib.import_module("tests.test_boundary_comprehensive")
    res = {}
    for name in ("TestPointerBoundary", "TestPipelineBoundary"):
        live = getattr(mod, name, None)
        try:
            live_line = inspect.getsourcelines(live)[1] if live else None
        except (OSError, TypeError) as e:
            live_line = None
            DOC["refuse"].append(f"P1 {name}: 取不到源码行（{e}）")
        sites = class_sites(rel, name)
        shadowed = [s for s in sites if s["first_line"] != live_line]
        res[name] = {
            "defined_at": [s["first_line"] for s in sites],
            "methods_per_def": {s["first_line"]: s["n_methods"] for s in sites},
            "live_line": live_line,
            "shadowed_methods": sum(s["n_methods"] for s in shadowed),
            "live_methods": len([m for m in dir(live) if m.startswith("test_")]) if live else 0,
        }
        if len(sites) < 2:
            DOC["refuse"].append(
                f"P1 {name}: 源码里只找到 {len(sites)} 处定义，与 F811 报的重复不符 ⇒ 口径要重查"
            )
        elif res[name]["shadowed_methods"] == 0:
            DOC["refuse"].append(
                f"P1 {name}: 有两处定义但被遮的那处没有 test_ 方法 ⇒ 不构成静默漏跑"
            )
    DOC["p1_shadowed_test_classes"] = res


def p2() -> None:
    res = {}
    targets = [
        (
            "cypyc.codegen.cython_generator",
            "CythonGenerator",
            "_visit_ExprStmt",
            "cypyc/codegen/cython_generator.py",
        ),
        (
            "cypyc.analyzer.scope_analyzer",
            "ScopeAnalyzer",
            "_visit_MetaBlock",
            "cypyc/analyzer/scope_analyzer.py",
        ),
    ]
    import importlib

    for mod_name, cls_name, meth, rel in targets:
        try:
            cls = getattr(importlib.import_module(mod_name), cls_name)
        except (ImportError, AttributeError) as e:
            DOC["refuse"].append(f"P2 {cls_name} 导不进来（{e}）⇒ 判据没跑到调用面")
            continue
        fn = cls.__dict__.get(meth)
        live_line = fn.__code__.co_firstlineno if fn else None
        sites = []
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == meth:
                sites.append(
                    {
                        "first_line": node.lineno,
                        "stmts": len(node.body),
                        "lines": node.end_lineno - node.lineno + 1,
                    }
                )
        dead = [s for s in sites if s["first_line"] != live_line]
        res[f"{cls_name}.{meth}"] = {
            "defined_at": [s["first_line"] for s in sites],
            "live_line": live_line,
            "sizes": {s["first_line"]: s["lines"] for s in sites},
            "dead_branches": dead,
            "note": "后定义覆盖前定义 ⇒ dead_branches 那份从不被调用；"
            "「哪份才是意图」不在此断言，交人类/缺陷单",
        }
        if len(sites) < 2:
            DOC["refuse"].append(
                f"P2 {cls_name}.{meth}: 只扫到 {len(sites)} 处定义，F811 说有两处 ⇒ 口径重查"
            )
        if live_line is None:
            DOC["refuse"].append(f"P2 {cls_name}.{meth}: 类上取不到该属性，说明它根本没被绑定")
    DOC["p2_dead_visitors"] = res


def p3() -> None:
    """把 polish_scan 扫到的每一处 skip 类标记都试跑一遍（绕过标记直接调函数）。

    基数自证：扫描件里的标记数 == 本函数记录的条数，少一条就是判据漏数。
    """
    import importlib

    scan = json.loads((HERE / "polish_scan_r1.json").read_text(encoding="utf-8"))
    sites = scan["law2_skip_marks"]
    rows, wanted = [], {}
    for s in sites:
        rel, _line = s["where"].rsplit(":", 1)
        wanted.setdefault(rel, 0)
        wanted[rel] += 1
    for rel, cnt in wanted.items():
        mod_name = rel.replace("/", ".").removesuffix(".py")
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:  # noqa: BLE001 — 导不进来本身就是结论
            rows.append(
                {
                    "module": mod_name,
                    "expected_marks": cnt,
                    "outcome": f"import 失败：{type(e).__name__}: {str(e)[:120]}",
                }
            )
            continue
        got = 0
        for nm, obj in vars(mod).items():
            if not (nm.startswith("test_") and callable(obj)):
                continue
            kinds = {str(m.name) for m in getattr(obj, "pytestmark", [])}
            if not (kinds & {"skip", "skipif", "xfail"}):
                continue
            got += 1
            fn = obj
            rec = {"module": mod_name, "test": nm, "marks": sorted(kinds)}
            try:
                sig = inspect.signature(fn)
                if len(sig.parameters):
                    r = subprocess.run(
                        [
                            sys.executable,
                            "-X",
                            "utf8",
                            "-m",
                            "pytest",
                            f"{rel}::{nm}",
                            "-q",
                            "--runxfail",
                            "-p",
                            "no:cacheprovider",
                        ],
                        cwd=str(ROOT),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    rec["outcome"] = f"带参数，改走 pytest --runxfail（rc={r.returncode}）"
                    rec["pytest_tail"] = (r.stdout or "").strip().splitlines()[-1][:170]
                else:
                    fn()
                    rec["outcome"] = "裸调通过 ⇒ 标记是**掩盖失效**（该摘或换更窄条件）"
            except Exception as e:  # noqa: BLE001 — 失败本身就是数据
                rec["outcome"] = (
                    f"裸调抛 {type(e).__name__}: {str(e)[:120]} ⇒ 真会失败，skip 有实据"
                )
            rows.append(rec)
        if got < cnt:
            rows.append(
                {
                    "module": mod_name,
                    "expected_marks": cnt,
                    "found_on_functions": got,
                    "outcome": "标记数与函数上可读的 pytestmark 数不等：可能是类级标记或"
                    "skipif 写在参数上 ⇒ 记为清单级，不猜结论",
                }
            )
    DOC["p3_skip_experiments"] = rows
    if len(rows) < sum(wanted.values()):
        DOC["refuse"].append(
            f"P3 基数自证失败：扫到 {sum(wanted.values())} 处标记，只试跑到 {len(rows)} 条记录"
        )


def main() -> int:
    p1()
    p2()
    p3()
    OUT.write_text(json.dumps(DOC, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(DOC, ensure_ascii=False, indent=1)[:2600])
    return 1 if DOC["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
