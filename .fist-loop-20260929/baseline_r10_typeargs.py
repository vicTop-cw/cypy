"""R10 基线：全仓 `.cypy` 里**调用点尖括号**的真实分布，为「类型实参」新规取反例面。

为什么先测再写规范：新规一旦把 `f<X>(...)` 判成类型实参并加元数门，
现存样例里任何" callee 不泛型 / 元数不符"都会从 rc=0 变成报错 ——
必须先知道有几处、分别落在哪个文件，才能定半径与 golden 影响面。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

CALL_KINDS = ("Name", "Attribute", "Subscript")


def walk(node):
    """极简 AST 遍历： yield 所有带 .kind 的节点（含嵌套表达式与语句）。"""
    stack = [node]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if isinstance(cur, (list, tuple)):
            for it in cur:
                stack.append(it)
            continue
        if not hasattr(cur, "__dict__"):
            continue
        if hasattr(cur, "kind"):
            yield cur
        for attr in list(vars(cur).values()):
            stack.append(attr)


def collect_calls(ast):
    """按**当前** AST 形态取调用点类型实参。

    R10 修复前这里叫 `checker`（单个标识符字符串），修复后是 `type_args`（类型表达式表）。
    两个名字都读 ⇒ 同一把尺子能同时量修复前后，不会出现"修完就数到 0、看起来像消失了"。
    """
    out = []
    for n in walk(ast):
        if getattr(n, "kind", None) != "Call":
            continue
        ta = getattr(n, "type_args", None)
        if ta:
            callee = getattr(n.func, "id", None) or getattr(n.func, "attr", None) or n.func.__class__.__name__
            rendered = ", ".join(getattr(a, "id", None) or getattr(a, "name", None)
                                 or type(a).__name__ for a in ta)
            out.append((callee, rendered, getattr(n, "line", 0)))
        legacy = getattr(n, "checker", None)
        if legacy:
            callee = getattr(n.func, "id", None) or getattr(n.func, "attr", None) or n.func.__class__.__name__
            out.append((callee, legacy, getattr(n, "line", 0)))
    return out


def main() -> int:
    files = sorted(ROOT.glob("examples/**/*.cypy")) + sorted(ROOT.glob("tests/**/*.cypy"))
    rep = {"files": len(files), "parse_fail": [], "callsites": [], "shape": {}}
    for p in files:
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            ast = Parser(list(Lexer(src).tokenize())).parse()
        except Exception as exc:  # noqa: BLE001
            rep["parse_fail"].append({"file": p.as_posix(), "err": f"{type(exc).__name__}: {str(exc)[:90]}"})
            continue
        tc = TypeChecker()
        try:
            tc.check(ast)
        except Exception:  # noqa: BLE001
            pass
        for callee, checker, line in collect_calls(ast):
            fd = tc.func_defs.get(callee)
            sd = tc.struct_defs.get(callee)
            kind = ("generic_func" if fd is not None and getattr(fd, "generic_params", []) else
                    "generic_struct" if sd is not None and getattr(sd, "generic_params", []) else
                    "non_generic_func" if fd is not None else
                    "non_generic_struct" if sd is not None else
                    "unknown_callee")
            n_decl = len(getattr(fd or sd, "generic_params", []) or []) if (fd or sd) else 0
            rec = {"file": p.as_posix().replace(ROOT.as_posix() + "/", ""), "callee": callee,
                   "type_arg": checker, "kind": kind, "declared_params": n_decl, "line": line}
            rep["callsites"].append(rec)
            rep["shape"][kind] = rep["shape"].get(kind, 0) + 1
    rep["parse_fail_n"] = len(rep["parse_fail"])
    rep["callsite_n"] = len(rep["callsites"])
    out = Path(__file__).with_name("baseline_r10_typeargs.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SHAPE", json.dumps(rep["shape"], ensure_ascii=False))
    print("BY_FILE", json.dumps({f: sum(1 for c in rep["callsites"]
                                        if c["file"].endswith(f)) for f in
                                 sorted({c["file"] for c in rep["callsites"]})}, ensure_ascii=False))
    for c in rep["callsites"]:
        if c["kind"] in ("non_generic_func", "non_generic_struct", "unknown_callee"):
            print("  RISK", c["file"], c["callee"], f"<{c['type_arg']}>", c["kind"], "declared=", c["declared_params"])
    print(f"CONCLUSION files={rep['files']} parse_fail={rep['parse_fail_n']} "
          f"callsites={rep['callsite_n']} risk_n="
          f"{sum(1 for c in rep['callsites'] if c['kind'] not in ('generic_func', 'generic_struct'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
