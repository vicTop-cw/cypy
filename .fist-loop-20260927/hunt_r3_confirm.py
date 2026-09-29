#!/usr/bin/env python3
"""R3-寻虫 v2：8 条候选逐条亲测（v1 有 5 条被**我自己的探针**炸掉，见报告 §五）。

v1 翻车原因写在这里，因为它们同样是这一环的产出：
- `Parser(...)` 的入参是 **token 列表**（`Parser(Lexer(src).tokenize()).parse()`），
  我按"源码字符串"传 ⇒ `'str' object has no attribute 'type'`；
- 运行时模块在 `cypy_bridge/`，不是 `cypyc.runtime`；
- 想在同进程里靠改 `os.environ['PYTHONHASHSEED']` 复现 set 顺序——**没用**，字符串哈希在解释器
  启动时就定了 ⇒ 必须起子进程；
- `cli.subparsers` 是函数内局部对象，模块上取不到 ⇒ 拿 `--help` 的实际输出当调用面。

判定分四档：`CONFIRMED`（码与自己的声明矛盾）/ `DESIGN`（自己的文本里明说是取舍，不入账）/
`REJECTED`（推翻）/ `PROBE-BROKEN`（判据坏了）。只要还剩 PROBE-BROKEN，本件就 refuse——
"全红"从来不是产品信号，是我自己的夹具坏了。
"""

from __future__ import annotations

import ast
import ctypes
import inspect
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
OUT = HERE / "hunt_r3_confirm.json"

from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402


def parse(src: str):
    return Parser(Lexer(src).tokenize()).parse()


def walk(node):
    seen, stack = set(), [node]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        yield cur
        for val in list(vars(cur).values()) if hasattr(cur, "__dict__") else []:
            if isinstance(val, list):
                stack.extend(v for v in val if hasattr(v, "__dict__"))
            elif hasattr(val, "__dict__") and not isinstance(val, type):
                stack.append(val)


CASES = []


def run_case(cid, claim, pos, ctl, declared, mode="confirm"):
    """mode="confirm"：缺陷现形(pos) + 对照成立(ctl) 才算 CONFIRMED。

    mode="check-only"：pos 就是那句主张本身，pos 不现形即 REJECTED（ctl 只是夹具是否读对了名字的
    自检，它失败说明**我的判据**坏 ⇒ PROBE-BROKEN）。上一版把这两种形状混在一个桶里，
    C7 那条"死码"主张就既没被确认也没被干净推翻。
    """
    row = {"id": cid, "claim": claim, "declared": declared, "mode": mode}
    broken = False
    for name, fn in (("pos", pos), ("ctl", ctl)):
        try:
            observed, want, ok = fn()
        except Exception as exc:  # noqa: BLE001
            observed, want, ok = f"{type(exc).__name__}: {exc}"[:240], "探针不该自己炸", False
            broken = True
        row[name] = {"observed": observed, "want": want, "ok": bool(ok)}
    if broken:
        row["verdict"] = "PROBE-BROKEN"
    elif mode == "declared-scope":
        # ctl 读的是**它自己的定位声明**：声明里已写明没实现 ⇒ 这一条是设计，不入账
        row["verdict"] = "DESIGN" if row["ctl"]["ok"] else (
            "CONFIRMED" if row["pos"]["ok"] else "REJECTED")
    elif mode == "check-only":
        row["verdict"] = "CONFIRMED" if row["pos"]["ok"] and row["ctl"]["ok"] else (
            "REJECTED" if row["ctl"]["ok"] else "UNSURE")
    else:
        row["verdict"] = "CONFIRMED" if row["pos"]["ok"] and row["ctl"]["ok"] else (
            "REJECTED" if not row["pos"]["ok"] else "UNSURE")
    CASES.append(row)


# ---------------------------------------------------------------- C1 泛型收集器恒空
def c1():
    from cypyc.transformer.generic_transformer import GenericTransformer

    src = textwrap.dedent(
        """
        generic struct Box<T>:
            value: T

        generic def unwrap<T>(b: Box<T>) -> T:
            return b.value
        """
    )
    tree = parse(src)
    holders = [n for n in walk(tree) if getattr(n, "generic_params", None)]

    def pos():
        tr = GenericTransformer()
        tr.transform(tree)
        return ({"generic_param_nodes": [(type(n).__name__, n.generic_params) for n in holders],
                 "generic_defs_collected": len(tr.generic_defs)},
                "有泛型节点时被收集到（docstring 第 5 行『注册泛型参数』）",
                len(holders) > 0 and len(tr.generic_defs) == 0)

    def ctl():
        class Fake:
            kind = "StructDef"
            type_params = ["T"]
            line, col = 1, 1

        tr = GenericTransformer()
        tr._collect_generics(Fake())
        return ({"collected_with_type_params_attr": len(tr.generic_defs)},
                "只要属性叫 type_params 就能收 ⇒ 坏的是名字对不上，不是收集器逻辑",
                len(tr.generic_defs) == 1)

    run_case("C1", "generic_transformer 读 `type_params`，parser 的泛型节点带的是 `generic_params` ⇒ 泛型收集恒为空",
             pos, ctl, "cypyc/transformer/generic_transformer.py:5（自称注册泛型参数）与 :39（读 type_params）")


# ---------------------------------------------------------------- C2 comptime 默认参数
def c2():
    """**撤回**：这条主张的前提就不成立。

    `SYNTAX/19-comptime.md:22` 自己写着『**编译期函数**：`comptime def` 语法未实现』，
    :43 的状态表同样标 `未实现` ⇒ 求值器少绑一个默认参数，是在一个**公开承认没实现**的特性内部，
    不构成缺陷（冻结文档也改不动）。留这一条是为了记下我一度误报，以及"入账前先读它的定位声明"。
    """
    from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator

    doc_lines = [l.rstrip() for l in (ROOT / "SYNTAX" / "19-comptime.md").read_text(encoding="utf-8").split("\n")
                 if "comptime def" in l]

    def pos():
        src = "comptime def add2(a: int, b: int = 10) -> int:\n    return a + b\n"
        try:
            tree = parse(src)
        except Exception as exc:  # noqa: BLE001
            return (f"parser 直接拒了：{type(exc).__name__}", "语法层就没实现", True)
        fn = [n for n in walk(tree) if getattr(n, "kind", "") in ("ComptimeFuncDef", "FuncDef")]
        params = getattr(fn[0], "params", []) if fn else []
        defaults = [getattr(p, "default_value", "<无此属性>") for p in params]
        ev = ComptimeEvaluator()
        ev.functions["add2"] = fn[0]
        try:
            got = ev._call_comptime_function("add2", [1])
            raised = None
        except Exception as exc:  # noqa: BLE001
            got, raised = None, f"{type(exc).__name__}: {exc}"[:80]
        return ({"param_defaults": defaults, "one_arg": repr(got)[:40], "raised": raised},
                "11（默认值该生效）", raised is not None or got != 11)

    def ctl():
        return ({"declared_in_syntax_doc": doc_lines[:3]},
                "文档必须明说 comptime def 未实现（否则本条就该入账）",
                any("未实现" in l for l in doc_lines))

    run_case("C2", "comptime 调用不读 `Param.default_value` ⇒ 但 `comptime def` 整族在 SYNTAX/19 里自述『未实现』"
                   "，故**撤回**（DESIGN，不入账）",
             pos, ctl, "SYNTAX/19-comptime.md:22/:43（自述未实现）对 comptime_evaluator.py:630-632",
             mode="declared-scope")


# ---------------------------------------------------------------- C3 transpile 的四个旗标
def c3():
    src = (ROOT / "cypyc/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    flags = ("check_only", "emit_ast", "generate_setup", "emit_cython")

    def readers():
        out = {}
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            used = sorted({a for a in flags if any(isinstance(x, ast.Attribute) and x.attr == a
                                                   for x in ast.walk(fn))})
            if used:
                out[fn.name] = used
        return out

    def pos():
        r = readers()
        return ({"flag_readers": r, "run_transpile_reads": r.get("run_transpile", [])},
                "transpile 的帮助文本写了这四个旗标 ⇒ 至少要读一个",
                r.get("run_transpile", []) == [])

    def ctl():
        # 调用面：`cypyc --help` 印出的子命令表 + `transpile --help` 里确有这些旗标
        top = subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc", "--help"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        tp = subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc", "transpile", "--help"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        listed = re.findall(r"\{([a-z,]+)\}", top.stdout)
        opts = [o for o in ("--check-only", "--emit-ast", "--generate-setup", "--emit-cython")
                if o in tp.stdout]
        return ({"top_level_choices": listed, "transpile_help_advertises": opts},
                "transpile --help 确实把这四个旗标承诺给用户", len(opts) == 4)

    run_case("C3", "`cypyc transpile` 的 --check-only/--emit-ast/--generate-setup/--emit-cython 只被印给用户，"
                   "run_transpile 一个都不读（读它们的是只能从不可达分支进入的 run_default）",
             pos, ctl, "docs/USAGE.md 与 transpile --help 的承诺 vs cypyc/cli.py:435-516")


# ---------------------------------------------------------------- C4 CUnion 的自示例
def c4():
    from cypy_bridge.union import CUnion, union

    doc = inspect.getdoc(CUnion) or ""

    def pos():
        try:
            CUnion(int, float)
            return ("没抛", "docstring 示例成立", False)
        except Exception as exc:  # noqa: BLE001
            return (f"{type(exc).__name__}: {exc}"[:160],
                    "docstring 里的示例（若真含 CUnion(int, float)）应可用",
                    "no size" in str(exc) and bool(re.search(r"CUnion\(int,\s*float\)|union\(int,\s*float\)", doc)))

    def ctl():
        u = CUnion(ctypes.c_int, ctypes.c_double)
        return ({"with_ctypes_types": type(u).__name__}, "给 ctypes 类型时构造成功",
                isinstance(u, CUnion))

    run_case("C4", "CUnion/union 的 docstring 示例 `CUnion(int, float)` 一跑就抛 TypeError（对 Python 内建类型取 ctypes.sizeof）",
             pos, ctl, "cypy_bridge/union.py:23-31 与 :179 的示例文本")


# ---------------------------------------------------------------- C5 realloc 静默 None
def c5():
    from cypy_bridge import memory as mem

    def pos():
        got = mem.realloc(0, 0)
        ann = mem.realloc.__annotations__.get("return")
        doc = inspect.getdoc(mem.realloc) or ""
        return ({"returned": repr(got), "annotation": getattr(ann, "__name__", str(ann)),
                 "doc_says": (re.search(r"返回：\s*([^\n]+(?:\n\s+[^\n]+)?)", doc) or ["", ""])[1].strip()[:60]},
                "注解 int + 文档『新的内存地址（int）』⇒ 不该返回 None", got is None)

    def ctl():
        try:
            mem.malloc(0)
            return ("malloc(0) 没抛", "同族入口 malloc 对 size<=0 是抛 MemoryError（说明这不是全局风格）", False)
        except Exception as exc:  # noqa: BLE001
            return (f"malloc(0) raised {type(exc).__name__}", "抛错", True)

    run_case("C5", "realloc(ptr, 0) 先 free 再 `return None`，而签名是 `-> int`、文档只说返回地址，"
                   "malloc 同一形状走的是抛错分支", pos, ctl, "cypy_bridge/memory.py:195-216")


# ---------------------------------------------------------------- C6 编译序依赖哈希
def c6():
    snippet = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, %r)
        from cypyc.project.module_dependency_graph import ModuleDependencyGraph as G
        g = G()
        for a, b in (("a", "b"), ("b", "c"), ("c", "a"), ("d", "e"), ("e", "d")):
            g.add_dependency(a, b)
        print(",".join(g.get_compilation_order()))
        """ % str(ROOT)
    )

    def pos():
        orders = []
        for seed in ("0", "1", "7", "42", "99"):
            r = subprocess.run([sys.executable, "-X", "utf8", "-c", snippet],
                               cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               env={"PYTHONHASHSEED": seed, "PATH": __import__("os").environ["PATH"]})
            orders.append((seed, r.stdout.strip() or r.stderr.strip()[-80:]))
        uniq = {o for _, o in orders}
        return ({"per_seed_orders": orders, "distinct": len(uniq)},
                "同一张图必须给同一个推荐序（文档只说『跳过循环中的模块』）", len(uniq) > 1)

    def ctl():
        from cypyc.project.module_dependency_graph import ModuleDependencyGraph as G
        g = G()
        for a, b in (("x", "y"), ("y", "z")):
            g.add_dependency(a, b)
        got = g.get_compilation_order()
        # add_dependency(from, to) 文档写的是「from 依赖 to」⇒ 被依赖者 must 先编（z, y, x）
        ok = got == ["z", "y", "x"]
        return ({"acyclic_order": got, "edges": "x→y, y→z（x 依赖 y）"},
                "无环时给确定的『被依赖者在前』序 ⇒ 证明 get_compilation_order 本身没坏", ok)

    run_case("C6", "get_compilation_order 把环内模块塞进 `set` 再 extend ⇒ 环存在时推荐编译序随进程哈希种子变化",
             pos, ctl, "cypyc/project/module_dependency_graph.py:200-212（文档只说『跳过循环中的模块』）")


# ---------------------------------------------------------------- C7 死掉的 in_degree
def c7():
    src = (ROOT / "cypyc/project/module_dependency_graph.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "topological_sort")
    body = ast.unparse(fn)

    def pos():
        loads = [x.id for x in ast.walk(fn) if isinstance(x, ast.Name) and x.id == "in_degree"
                 and isinstance(x.ctx, ast.Load)]
        stores = [x.id for x in ast.walk(fn) if isinstance(x, ast.Name) and x.id == "in_degree"
                  and isinstance(x.ctx, ast.Store)]
        pass_bodies = [ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.For)
                       and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)]
        return ({"in_degree_store_count": len(stores), "in_degree_load_count": len(loads),
                 "for_loops_whose_whole_body_is_pass": pass_bodies},
                "第一遍算出来的 in_degree 应被消费（否则前段是死码）", len(pass_bodies) >= 1)

    def ctl():
        # 对照：这个函数里**被真正读取**的计数器必须存在且不止 in_degree —— 证明我没把"有读"误判成"没读"
        loaded = {x.id for x in ast.walk(fn) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
        return ({"loaded_names_sample": sorted(n for n in loaded if n in {"graph", "nodes", "result", "queue"})},
                "确有别的名字被真读（说明 Load 判据不是恒假）", bool(loaded))

    run_case("C7", "子代理主张：topological_sort 先算一遍 in_degree 并把某个循环体写成 `pass`，随后整个丢掉重建 ⇒ 前段是死码",
             pos, ctl, "cypyc/project/module_dependency_graph.py:134-141", mode="check-only")


# ---------------------------------------------------------------- C8 构建块检查器的规则 2
def c8():
    from cypyc.analyzer.build_block_checker import BuildBlockChecker

    mod = sys.modules[BuildBlockChecker.__module__]
    # 规则清单在**模块** docstring（:2-8），类 docstring 只有一行标题 ⇒ 读错地方就会把
    # "承诺存在"判成"承诺不存在"（v3 就是这么把它误判成 REJECTED 的）
    doc = "\n".join([(mod.__doc__ or ""), (inspect.getdoc(BuildBlockChecker) or "")])

    class N:
        """够用的假 AST 节点：检查器只按 `.kind` 分发、按属性取值。

        未知属性一律给 None（v1 就是被 `node.operand` 这类真实读取炸掉的），
        但 `kind` 必须显式给——分发靠它。
        """

        def __init__(self, kind, **attrs):
            self.kind = kind
            self.line = attrs.pop("line", 7)
            self.col = 3
            self.__dict__.update(attrs)

        def __getattr__(self, item):
            return None

    def pos():
        tree = parse("def f() -> int:\n    p: *int = 0\n    return 0\n")  # 真解析出 PointerType
        kinds = [getattr(n, "kind", type(n).__name__) for n in walk(tree)]
        ch = BuildBlockChecker()
        ch.check(tree)
        rule2 = [l.strip() for l in doc.split("\n") if "指针" in l]
        return ({"node_kinds": [k for k in kinds if k in ("PointerType", "DerefExpr", "FuncDef")],
                 "docstring_rule2": rule2, "errors_for_pointer_outside_block": list(ch.errors)},
                "规则 2 承诺『指针语法只能在构建块内部使用』⇒ 函数体内的 PointerType 应报错",
                "PointerType" in kinds and list(ch.errors) == [] and bool(rule2))

    def ctl():
        ch = BuildBlockChecker()
        ch.check(N("Module", body=[
            N("BuildBlockExpr", block_type="assign", body=[N("YieldStmt", value=N("Name", name="v"))]),
        ]))
        live = [e for e in ch.errors if "assign build blocks" in e]
        return ({"errors_from_a_different_rule": live},
                "对照：另一条规则（assign 块里不许 yield）确实在报 ⇒ 检查器不是整体空转，只有规则 2 是空的",
                len(live) == 1)

    run_case("C8", "BuildBlockChecker 的 docstring 规则 2（指针语法只能在构建块内部使用）没有实现："
                   "_visit_DerefExpr/_visit_PointerType 只注释『移除』，不 append 任何 error",
             pos, ctl, "cypyc/analyzer/build_block_checker.py:5-6（声明）对 :75-84（实现）")


def main() -> int:
    for fn in (c1, c2, c3, c4, c5, c6, c7, c8):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            CASES.append({"id": fn.__name__, "verdict": "PROBE-BROKEN",
                          "error": f"{type(exc).__name__}: {exc}"[:400], "claim": "整个用例没跑起来"})
    broken = [c for c in CASES if c.get("verdict") == "PROBE-BROKEN"]
    doc = {
        "cases": CASES,
        "confirmed": [c["id"] for c in CASES if c.get("verdict") == "CONFIRMED"],
        "n_cases": len(CASES),
        "design_or_rejected": [{"id": c["id"], "v": c["verdict"]}
                                for c in CASES if c.get("verdict") in ("DESIGN", "REJECTED", "UNSURE")],
        "refuse": [],
    }
    if broken:
        doc["refuse"].append(f"{len(broken)} 条探针自己炸了（判据坏了，不是产品坏了）：{[c['id'] for c in broken]}")
    out = HERE / "hunt_r3_confirm.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("confirmed", "design_or_rejected", "refuse")}, ensure_ascii=False))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
