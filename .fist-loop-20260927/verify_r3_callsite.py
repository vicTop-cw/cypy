"""R3-验证 法 3：调用面独立复验（与 R3-修复 环不同的脚本，只读盘面）。

每条检查都从**入口**打进去（`python -m cypyc.cli ...` 子进程、`cypy_bridge` 真实构造、
带 PYTHONHASHSEED 的子进程、真实 AST 上的 checker），不 import 任何判据件、
不读上一环的 JSON 结论。检查项刻意与修复环的锁不同形（不同旗标组合、不同图、
不同种子、`get_type_hints` 的对象相等而非字符串相等）。
"""

from __future__ import annotations

import ast
import ctypes
import json
import os
import subprocess
import sys
import typing
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = HERE / "tmp_verify" / "callsite"
PY = sys.executable
FLAGS = ("--check-only", "--emit-ast", "--emit-cython", "--generate-setup")
CHECKS: list = []
REFUSE: list = []

GOOD = "def add(a: int, b: int) -> int:\n    return a + b\n"
BROKEN = "def bad(a: int) -> int:\n    return\n"
GENERIC = "struct Box<T>:\n    value: T\n\n\ndef make() -> int:\n    return 0\n"


def record(name, how, expected, observed, ok):
    CHECKS.append({"name": name, "how": how, "expected": expected,
                   "observed": observed, "ok": bool(ok)})
    return ok


def cli(*argv, tag=""):
    proc = subprocess.run([PY, "-X", "utf8", "-m", "cypyc.cli", *argv], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)
    text = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, text


def _src(name, body):
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / name
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def c_help_advertises_four_flags():
    rc, text = cli("transpile", "--help")
    seen = [f for f in FLAGS if f in text]
    return record("transpile --help 承诺四个旗标", "python -m cypyc.cli transpile --help",
                  "四个旗标全部出现在帮助文本", {"rc": rc, "advertised": seen},
                  rc == 0 and len(seen) == 4)


def c_check_only_clean():
    src = _src("ok.cypy", GOOD)
    out = WORK / "cs_check_ok"
    rc, text = cli("transpile", str(src), "-o", str(out), "--check-only")
    produced = sorted(p.name for p in out.glob("*")) if out.exists() else []
    return record("--check-only 干净源码：rc=0 + 报通过 + 不产码",
                  "cypyc transpile ok.cypy -o out --check-only",
                  "rc=0, 'Static analysis passed', 产物目录空",
                  {"rc": rc, "passed_msg": "Static analysis passed" in text,
                   "produced": produced},
                  rc == 0 and "Static analysis passed" in text and produced == [])


def c_check_only_broken():
    src = _src("bad.cypy", BROKEN)
    out = WORK / "cs_check_bad"
    rc, text = cli("transpile", str(src), "-o", str(out), "--check-only")
    produced = sorted(p.name for p in out.glob("*")) if out.exists() else []
    return record("--check-only 坏源码：非零退出且报问题数",
                  "cypyc transpile bad.cypy -o out --check-only",
                  "rc!=0, 'Static analysis found', 不产码",
                  {"rc": rc, "found_msg": "Static analysis found" in text,
                   "produced": produced},
                  rc != 0 and "Static analysis found" in text and produced == [])


def c_emit_ast():
    src = _src("ast.cypy", GOOD)
    rc, text = cli("transpile", str(src), "-o", str(WORK / "cs_ast"), "--emit-ast")
    lines = [ln for ln in text.splitlines() if "FuncDef" in ln]
    return record("--emit-ast 打印解析后的节点树",
                  "cypyc transpile ast.cypy --emit-ast",
                  "rc=0 且节点行含 'FuncDef add'",
                  {"rc": rc, "funcdef_lines": lines[:3]},
                  rc == 0 and any("FuncDef add" in ln for ln in lines))


def c_emit_cython_cython_mode():
    src = _src("cy.cypy", GOOD)
    rc, text = cli("transpile", str(src), "-o", str(WORK / "cs_cy"), "--emit-cython")
    return record("--emit-cython（Cython 模式）打印 .pyx 文本",
                  "cypyc transpile cy.cypy --emit-cython",
                  "rc=0 + 'Generated Cython code:' + 'def add('",
                  {"rc": rc, "header": "Generated Cython code:" in text,
                   "body": "def add(" in text},
                  rc == 0 and "Generated Cython code:" in text and "def add(" in text)


def c_emit_cython_bridge_mode_declines():
    src = _src("br.cypy", GOOD)
    out = WORK / "cs_br"
    rc, text = cli("transpile", str(src), "-o", str(out), "--bridge", "--emit-cython")
    files = sorted(p.name for p in out.glob("*")) if out.exists() else []
    return record("--bridge --emit-cython 明确说明不适用（而不是静默）",
                  "cypyc transpile br.cypy --bridge --emit-cython",
                  "rc=0 + 提示 'does not apply in --bridge mode' + 产出 .c",
                  {"rc": rc, "notice": "does not apply in --bridge mode" in text,
                   "files": files},
                  rc == 0 and "does not apply in --bridge mode" in text
                  and any(f.endswith(".c") for f in files))


def c_generate_setup_cython_mode():
    src = _src("setup_cy.cypy", GOOD)
    out = WORK / "cs_setup_cy"
    rc, text = cli("transpile", str(src), "-o", str(out), "--generate-setup")
    setup = out / "setup.py"
    body = setup.read_text(encoding="utf-8") if setup.exists() else ""
    sources = []
    if body:
        for node in ast.walk(ast.parse(body)):
            if isinstance(node, ast.keyword) and node.arg == "sources":
                sources = [e.value for e in getattr(node.value, "elts", [])]
    return record("--generate-setup（Cython 模式）写可解析的 setup.py 且 sources 指向 .pyx",
                  "cypyc transpile setup_cy.cypy -o out --generate-setup",
                  "rc=0 + setup.py 存在 + ast.parse 通过 + sources 含 setup_cy.pyx",
                  {"rc": rc, "exists": setup.exists(), "sources": sources},
                  rc == 0 and setup.exists() and any(s.endswith("setup_cy.pyx")
                                                     for s in sources))


def c_generate_setup_bridge_mode():
    src = _src("setup_br.cypy", GOOD)
    out = WORK / "cs_setup_br"
    rc, text = cli("transpile", str(src), "-o", str(out), "--bridge", "--generate-setup")
    setup = out / "setup.py"
    bodies = setup.read_text(encoding="utf-8") if setup.exists() else ""
    sources = []
    if bodies:
        try:
            for node in ast.walk(ast.parse(bodies)):
                if isinstance(node, ast.keyword) and node.arg == "sources":
                    sources = [e.value for e in getattr(node.value, "elts", [])]
        except SyntaxError as exc:
            REFUSE.append(f"--bridge --generate-setup 生成的 setup.py 语法不过：{exc}")
    return record("--generate-setup（bridge 模式）同样写出 setup.py",
                  "cypyc transpile setup_br.cypy --bridge --generate-setup",
                  "rc=0 + setup.py 存在 + sources 非空",
                  {"rc": rc, "exists": setup.exists(), "sources": sources,
                   "tail": text[-160:]},
                  rc == 0 and setup.exists() and len(sources) >= 1)


def c_generic_struct_through_cli():
    src = _src("box.cypy", GENERIC)
    out = WORK / "cs_box"
    rc, text = cli("transpile", str(src), "-o", str(out))
    files = sorted(p.name for p in out.glob("*")) if out.exists() else []
    return record("冻结泛型 struct Box<T> 走真实 transpile 入口能出码（BUG-55 的调用面）",
                  "cypyc transpile box.cypy -o out（SYNTAX/11 冻结形：struct Box<T>）",
                  "rc=0 且产出 box.pyx",
                  {"rc": rc, "files": files, "tail": text[-160:]},
                  rc == 0 and "box.pyx" in files)


def c_union_shapes():
    from cypy_bridge.union import CUnion, union

    a, b, c = CUnion(ctypes.c_int, ctypes.c_double), CUnion("int", "double"), union("int", "double")
    vals = []
    for obj in (a, b, c):
        obj.value = 3.5
        vals.append(obj.value)
    return record("CUnion 两种可运行形状（ctypes 类型 / C 类型名）+ union() 等价",
                  "in-process: CUnion(c_int,c_double) / CUnion('int','double') / union(...)",
                  "三种构造都能赋值回读，size 一致",
                  {"roundtrip": vals, "sizes": [a.size, b.size, c.size]},
                  vals == [3.5, 3.5, 3.5] and a.size == b.size == c.size)


def c_union_builtin_diagnosed():
    from cypy_bridge.union import CUnion, UnionTypeError

    try:
        CUnion(int, float)
        return record("传 Python 内建类型 ⇒ UnionTypeError 且文案给口径",
                      "in-process: CUnion(int, float)",
                      "抛 UnionTypeError，文案含 'Python builtin type'、不含 ctypes 内部文案",
                      {"raised": None}, False)
    except UnionTypeError as exc:
        msg = str(exc)
        return record("传 Python 内建类型 ⇒ UnionTypeError 且文案给口径",
                      "in-process: CUnion(int, float)",
                      "抛 UnionTypeError，文案含 'Python builtin type'、不含 'no size'",
                      {"raised": msg[:160]},
                      "Python builtin type" in msg and "no size" not in msg)
    except Exception as exc:  # noqa: BLE001
        return record("传 Python 内建类型 ⇒ UnionTypeError 且文案给口径",
                      "in-process: CUnion(int, float)",
                      "抛 UnionTypeError", {"raised": f"{type(exc).__name__}: {exc}"[:160]},
                      False)


def c_realloc_annotation_object():
    from cypy_bridge import memory as mem

    hints = typing.get_type_hints(mem.realloc)
    return record("realloc 返回注解与实现同形（对象相等，不是字符串比对）",
                  "in-process: typing.get_type_hints(memory.realloc)",
                  "hints['return'] == typing.Optional[int]",
                  {"return_hint": str(hints.get("return")),
                   "equal": hints.get("return") == typing.Optional[int]},
                  hints.get("return") == typing.Optional[int])


def c_realloc_growth_readback():
    from cypy_bridge import memory as mem

    ptr = mem.malloc(16)
    grown = mem.realloc(ptr, 128)
    ok_type = isinstance(grown, int) and not isinstance(grown, bool)
    filled = None
    try:
        mem.memset(grown, 65, 128)
        filled = ctypes.string_at(grown, 4)
    finally:
        mem.free(grown)
    return record("realloc 扩容返回裸地址(int) 且可直接 memset 回读（注解说的就是这个形状）",
                  "in-process: malloc(16) -> realloc(ptr,128) -> memset -> free",
                  "返回 int、写读一致（b'AAAA'）",
                  {"returned": type(grown).__name__, "is_int": ok_type,
                   "readback": filled.decode("ascii", "replace") if filled else None},
                  ok_type and filled == b"AAAA")


def c_realloc_zero_frees_only():
    from cypy_bridge import memory as mem

    ptr = mem.malloc(32)
    got = mem.realloc(ptr, 0)
    return record("realloc(p, 0) 释放并返回 None（既有形状，本轮没动）",
                  "in-process: malloc(32) -> realloc(ptr, 0)",
                  "返回值 is None",
                  {"returned": repr(got)}, got is None)


_SEED_SNIPPET = (
    "import sys;sys.path.insert(0,%r)\n"
    "from cypyc.project.module_dependency_graph import ModuleDependencyGraph as G\n"
    "g=G()\n"
    "for a,b in (('m2','m1'),('m1','m3'),('m3','m2'),('k','m2'),('q','k'),('p','q')):\n"
    "    g.add_dependency(a,b)\n"
    "print(g.get_compilation_order())\n"
) % str(ROOT)


def c_compilation_order_other_seeds():
    orders = {}
    for seed in ("2", "3", "5", "11", "13", "12345"):
        proc = subprocess.run([PY, "-X", "utf8", "-c", _SEED_SNIPPET], cwd=str(ROOT),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300,
                              env={**os.environ, "PYTHONHASHSEED": seed})
        orders[seed] = proc.stdout.strip() or f"ERR {proc.stderr.strip()[-90:]}"
    uniq = sorted({v for v in orders.values()})
    first = ast.literal_eval(orders["2"]) if orders["2"].startswith("[") else []
    return record("get_compilation_order 在另外 6 个哈希种子上给同一序（BUG-59 调用面）",
                  "子进程 PYTHONHASHSEED ∈ {2,3,5,11,13,12345}，图与修复环不同（双环+链）",
                  "distinct 输出 == 1，且环内 {m1,m2,m3} 按名字排在链后",
                  {"distinct": len(uniq), "order": first},
                  len(uniq) == 1 and first[-3:] == ["m1", "m2", "m3"])


def c_build_block_checker_call_site():
    from cypyc.analyzer.build_block_checker import BuildBlockChecker
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser

    def check(src):
        tree = Parser(Lexer(src).tokenize()).parse()
        ch = BuildBlockChecker()
        ch.check(tree)
        return list(ch.errors)

    ptr_in_func = check("def f() -> int:\n    p: *int = 0\n    return 0\n")
    yield_in_assign = check("def f() -> int:\n    x =:\n        yield 1\n        1\n    return x\n")
    return record("build_block_checker 调用面：函数体内指针声明不报、assign 块内 yield 仍报",
                  "in-process: Lexer+Parser+BuildBlockChecker 两份真实源码",
                  "指针声明 errors==[]；yield 块 errors 非空",
                  {"ptr_in_func": ptr_in_func, "yield_in_assign": yield_in_assign[:2]},
                  ptr_in_func == [] and len(yield_in_assign) >= 1)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    import cypyc  # noqa: F401  确认从仓库树导入（下面记录身份）
    entry = globals()
    names = [k for k in sorted(entry) if k.startswith("c_")]
    for name in names:
        try:
            entry[name]()
        except Exception as exc:  # noqa: BLE001
            REFUSE.append(f"检查 {name} 抛异常（算失败不算跳过）："
                          f"{type(exc).__name__}: {exc}"[:200])
            CHECKS.append({"name": name, "how": "driver", "expected": "不抛",
                           "observed": f"{type(exc).__name__}: {exc}"[:200], "ok": False})
    all_ok = all(c["ok"] for c in CHECKS) and not REFUSE
    doc = {
        "refuse": REFUSE,
        "checks": len(CHECKS),
        "checks_all_true": 1 if all_ok else 0,
        "failed_checks": [c["name"] for c in CHECKS if not c["ok"]],
        "identity": {"cypyc_file": getattr(cypyc, "__file__", None),
                     "inside_repo": str(Path(getattr(cypyc, "__file__", "")).resolve())
                     .startswith(str(ROOT))},
        "detail": CHECKS,
    }
    (HERE / "verify_r3_callsite.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "checks", "checks_all_true",
                                          "failed_checks", "identity")},
                     ensure_ascii=False, indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
