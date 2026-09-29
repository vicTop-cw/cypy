"""R1-推进（advance）新增的两条「已声明未实现」补口的回归锁与对照。

补口来自 `SYNTAX/` 的声明，判据全部打在 **CLI/codegen 调用面**（不是"模块里有函数+有单测"）：

- ADV-1 `raise X from e`：`SYNTAX/16-exceptions.md:111` 声明异常链；
  修复前 `_visit_RaiseStmt` 只写 `raise {exc}` ⇒ 产物静默丢掉 `from e`。
- ADV-2 `let x =:`：`SYNTAX/13-build-blocks.md:74` 声明变量构建块形；
  修复前 `_parse_let_stmt` 直接 `_expect(NEWLINE)` ⇒ `Expected NEWLINE, got BUILD_ASSIGN`。
  落地方式是把 `let x =:` **脱糖成裸形 `x =:` 的 AST**，故这里成对断言
  "两种写法产物逐行相同"——单看 `let` 那一侧的产物是否有 `result` 字样是不承重的判据
  （第一版就是这么错的：它把 `result = def _bb_0(): ...` 这种废码也判成通过）。

每条锁都配一条**必然不误抓的正例/反例对照**，防止判据恒绿。
"""

import re
import subprocess
import sys
from pathlib import Path

from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Assign, BuildBlockExpr, Name, Parser

ROOT = Path(__file__).resolve().parent.parent

RAISE_FROM_SRC = (
    "def load() -> int:\n"
    "    try:\n"
    '        raise FileNotFoundError("nope")\n'
    "    except FileNotFoundError as e:\n"
    '        raise RuntimeError("Failed to load data") from e\n'
    "    return 0\n"
)
RAISE_NO_CAUSE_SRC = (
    "def load() -> int:\n"
    "    try:\n"
    '        raise FileNotFoundError("nope")\n'
    "    except FileNotFoundError as e:\n"
    '        raise RuntimeError("Failed to load data")\n'
    "    return 0\n"
)
LET_BLOCK_SRC = (
    "let result =:\n    let x: int = 10\n    let y: int = 20\n    x + y\n\nprint(result)\n"
)
BARE_BLOCK_SRC = "result =:\n    let x: int = 10\n    let y: int = 20\n    x + y\n\nprint(result)\n"
PLAIN_LET_SRC = "let q: int = 5\nprint(q)\n"


def _emit(source: str) -> str:
    """走和 CLI 一样的三段：Lexer → Parser → CythonGenerator，取产物全文。"""
    ast = Parser(list(Lexer(source).tokenize())).parse()
    gen = CythonGenerator()
    gen.generate(ast)
    return "\n".join(gen.output)


def _code_lines(text: str) -> list:
    skip_prefix = (
        "#",
        "import ",
        "from libc",
        "cimport",
        "__generated_at__",
        "__module_version__",
        "__name__",
        "__file__",
        "__all__",
    )
    out = []
    for raw in text.splitlines():
        ln = raw.strip()
        if (
            not ln
            or ln.startswith(skip_prefix)
            or ln.startswith('"""')
            or ln.startswith("Source file")
        ):
            continue
        out.append(ln)
    return out


# ---------------------------------------------------------------- ADV-1
def test_bug_adv1_raise_from_keeps_cause_in_emit():
    """声明句：`raise RuntimeError("...") from e` ⇒ 产物必须保留 from 子句。"""
    emit = _emit(RAISE_FROM_SRC)
    hits = re.findall(r"raise\s+RuntimeError\([^)]*\)\s+from\s+\w+", emit)
    raise_lines = [seg for seg in emit.splitlines() if "raise" in seg]
    assert len(hits) == 1, f"from 子句被丢了：{raise_lines}"


def test_bug_adv1_control_no_cause_raise_unchanged():
    """反例对照：不带 from 的 raise 不能被写出 ` from `（否则上一条判据恒绿）。"""
    emit = _emit(RAISE_NO_CAUSE_SRC)
    raise_lines = [seg.strip() for seg in emit.splitlines() if seg.strip().startswith("raise ")]
    assert raise_lines, "产物里连 raise 都没有，判据面不存在"
    assert not any(
        " from " in seg for seg in raise_lines
    ), f"无 cause 的 raise 被多写了 from：{raise_lines}"


def test_bug_adv1_runtime_chain_visible_at_cli():
    """打到 `cypyc run` 调用面：`__cause__` 必须真挂上（修复前这里是 None）。"""
    import tempfile

    prog = (
        "def load() -> int:\n"
        "    try:\n"
        '        raise FileNotFoundError("nope")\n'
        "    except FileNotFoundError as e:\n"
        '        raise RuntimeError("Failed to load data") from e\n'
        "    return 0\n"
        "\n"
        "def main() -> None:\n"
        "    try:\n"
        "        load()\n"
        "    except RuntimeError as r:\n"
        "        print(str(r.__cause__))\n"
    )
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "adv1_chain.cypy"
        src.write_text(prog, encoding="utf-8", newline="\n")
        r = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "cypyc", "run", str(src)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        out = (r.stdout or "") + (r.stderr or "")
        assert r.returncode == 0, f"CLI rc={r.returncode}：{out[-400:]}"
        assert "nope" in out, f"异常链没挂上（__cause__ 为 None）：{out[-400:]}"


# ---------------------------------------------------------------- ADV-2
def test_bug_adv2_let_build_block_form_parses():
    """`let x =:` 必须解析成功并落进与裸形同一个构建块节点。"""
    ast = Parser(list(Lexer(LET_BLOCK_SRC).tokenize())).parse()
    first = ast.body[0]
    assert isinstance(first, Assign), f"没脱糖成裸形的 Assign：{type(first).__name__}"
    assert isinstance(first.target, Name) and first.target.id == "result"
    assert isinstance(first.value, BuildBlockExpr), f"值不是构建块：{type(first.value).__name__}"


def test_bug_adv2_let_and_bare_forms_emit_identically():
    """双向一致性：`let result =:` 与 `result =:` 的产物必须逐行相同。

    这条是承重的那条：只看 `let` 一侧"产物里有没有 result 字样"会放过
    `result = def _bb_0(): ...` 这种一行压平的废码（第一版判据就是这么漏的）。
    """
    assert _code_lines(_emit(LET_BLOCK_SRC)) == _code_lines(_emit(BARE_BLOCK_SRC))
    assert re.search(r"(?m)^result\s*=\s*_bb_\d+\(\)$", _emit(LET_BLOCK_SRC)), "块没被先定义再调用"


def test_bug_adv2_control_plain_let_still_works():
    """正例对照：普通 `let q: int = 5` 不受影响（防止把 let 整条路径改掉）。"""
    emit = _emit(PLAIN_LET_SRC)
    assert re.search(r"(?m)^q\s*=\s*5$", emit), _code_lines(emit)[:6]
