"""寻虫探针：位置模式按 `_class_fields[i]` 取值，而那张表把**方法名**也算成字段。

现场：`cypyc/codegen/cython_generator.py:436-450`（StructDef）与 `:454-468`（ClassDef）
把 body 里任何带 `name` 的成员都 append 进 `fields`，只排除 `__unapply__` 等四个提取器名；
`def __init__` / `def area` 这类方法照样进表。消费侧 `:1766-1793` 直接 `fields[i]` 按位置取，
于是「方法声明在字段之前」的 struct，位置模式比的是**方法的绑定方法对象**：

  struct Rect:
      def area(self) -> int: ...   # <- fields[0]
      w: int                       # <- fields[1]
      h: int                       # <- fields[2]
  match r: case Rect(3, 4): ...    # 生成 `r.area == 3` —— 恒 False，且没有任何诊断

这是 Find_BUG 账本里「未证实转结」那一条（cython_generator 的 `__init__`/`__match_args__`
分支）：前两轮的最小复现都没落进这条分支。本探针先证明**分支可达**，再分三格取证：
  G1 基线（字段在前、方法在后）—— 期望位置比对落在 w/h 上（现网正确形态）
  B1 方法在前 —— 期望暴露错位（落在 area 上）
  B2 绑定形态 —— 期望把方法对象绑给用户变量（不是比较，是静默错值）
不落盘、不改产品代码，只打印生成片段。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

MATCH_TAIL = """
def classify(r: Rect) -> str:
    match r:
        case Rect(3, 4):
            return "hit-const"
        case Rect(a, b):
            return "hit-bind"
        case _:
            return "miss"
"""

BASELINE = """struct Rect:
    w: int
    h: int

    def area(self) -> int:
        return self.w * self.h
"""

METHOD_FIRST = """struct Rect:
    def area(self) -> int:
        return self.w * self.h

    w: int
    h: int
"""

INIT_FIRST = """struct Rect:
    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h

    w: int
    h: int
"""


def gen_fields(source: str):
    """返回 (生成的 pyx 文本, 生成器内部算出的 _class_fields/_extractor_types)。"""
    ast = Parser(list(Lexer(source + MATCH_TAIL).tokenize())).parse()
    generator = CythonGenerator()
    text = generator.generate(ast)
    return text, dict(getattr(generator, "_class_fields", {})), sorted(
        getattr(generator, "_extractor_types", set())
    )


# 按形状取数：位置模式生成的比对行形如 `<subject>.<attr> == <const>`，绑定行形如
# `<var> = <subject>.<attr>`。数符号会造假，这里只认这两种形状并留下逐字原行。
COND_RE = re.compile(r"^[^\s]*\.(\w+)\s*==\s*.+$")
BIND_RE = re.compile(r"^[A-Za-z_]\w*\s*=\s*[^\s]*\.(\w+)$")


def extract_shapes(text: str):
    conds, binds, cond_lines = [], [], []
    for raw in text.splitlines():
        ln = raw.strip()
        m = COND_RE.match(ln)
        if m:
            conds.append(m.group(1))
            cond_lines.append(ln)
        b = BIND_RE.match(ln)
        if b:
            binds.append(b.group(1))
    return conds, binds, cond_lines


def main() -> int:
    report: dict = {"cases": {}, "refuse": []}
    for label, src in (("G1_baseline_fields_first", BASELINE),
                       ("B1_method_first", METHOD_FIRST),
                       ("B2_init_first", INIT_FIRST)):
        source = src + MATCH_TAIL
        try:
            text, fields, extractors = gen_fields(source)
        except Exception as exc:  # 解析/生成阶段就炸也是结论，但要写明形态
            report["cases"][label] = {"crashed": f"{type(exc).__name__}: {exc}"}
            continue
        conds, binds, cond_lines = extract_shapes(text)
        report["cases"][label] = {
            "class_fields": fields,
            "extractor_types": extractors,
            "compared_attrs": conds,
            "bound_attrs": binds,
            "verbatim_condition_lines": cond_lines[:8],
        }
    # 分支可达性自证：三格都必须真的产出过 case 比对行，否则本探针什么都没测到
    for label, case in report["cases"].items():
        if not case.get("compared_attrs"):
            report["refuse"].append(f"{label} 没有生成任何比对行 ⇒ 分支不可达，结论不作数")
    out = Path(__file__).resolve().parent / "hunt_r6_class_fields.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if report["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
