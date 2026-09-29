"""R2-修复（fix）六单的回归锁与成对对照。

判据全部打在**调用面**（CLI 子进程 / 包级 API / 产物全文），不用"源码里出现了某个字样"充当证据：

- BUG-44 struct 里的 `@staticmethod`/`@classmethod` 生成时仍注入 `self`。
- BUG-45 struct 的 `= __implicit_default__` 默认值生成成裸名字，导入即 NameError。
- BUG-39 顶层 `return` 被静默接受并原样写进产物（.pyx 必编译失败）。
- BUG-35 解析/生成期异常被归进「读取文件错误」桶（本单只锁**分桶**，深嵌套守卫另账）。
- BUG-46 `hook install` 报 [OK] 但零持久化，`hook status` 在另一进程里报未装（互相否定）。
- BUG-47 docs 声明的 `cypy_hook` 包级 API 未再导出。

每条锁都配一条"必然不误抓"的正例对照：删掉对照就没有东西能证明判据会红。
"""

import re
import subprocess
import sys
from pathlib import Path

from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

ROOT = Path(__file__).resolve().parent.parent

BUG44_SRC = (
    "struct Point:\n"
    "    x: int\n"
    "\n"
    "    @staticmethod\n"
    "    def origin() -> Point:\n"
    "        return Point(x=0)\n"
    "\n"
    "    @classmethod\n"
    "    def named(n: int) -> Point:\n"
    "        return Point(x=n)\n"
    "\n"
    "    def shifted(self, dx: int) -> int:\n"
    "        return self.x + dx\n"
)

# 注：绑定方法按 SYNTAX/06d 的写法**显式声明 self**（隐式 self 会被类型检查判
# `Undefined name 'self'`，那是另一条既有面，不在本单半径内）。

BUG45_SRC = (
    "struct Config:\n"
    "    timeout: int\n"
    "\n"
    "    @staticmethod\n"
    "    def __implicit_default__() -> Config:\n"
    "        return Config(timeout=30)\n"
    "\n"
    "def process(cfg: Config = __implicit_default__) -> int:\n"
    "    return cfg.timeout\n"
    "\n"
    "def plain(t: int = 5) -> int:\n"
    "    return t\n"
)

BUG45_NO_ANNOT_SRC = "def bad(cfg = __implicit_default__) -> int:\n    return 1\n"

BUG39_TOPLEVEL_SRC = "def ok() -> int:\n    return 1\n\nreturn 0\n"
BUG39_CONTROL_SRC = "def ok() -> int:\n    return 1\n\nprint(ok())\n"
BUG35_DEFER_SRC = 'def f() -> int:\n    return 0\n\ndefer print("x")\n'


def _emit(source: str) -> str:
    """走和 CLI 一样的三段：Lexer → Parser → CythonGenerator，取产物全文。"""
    ast = Parser(list(Lexer(source).tokenize())).parse()
    gen = CythonGenerator()
    gen.generate(ast)
    return "\n".join(gen.output)


def _sig_lines(text: str, name: str) -> list:
    return [ln.strip() for ln in text.splitlines() if re.match(rf"\s*def {name}\b", ln)]


def _write_tmp(tmp: Path, filename: str, source: str) -> Path:
    src = tmp / filename
    src.write_text(source, encoding="utf-8", newline="\n")
    return src


def _cli(*argv, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc", *argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def _all_text(proc: subprocess.CompletedProcess) -> str:
    """CLI 的诊断走 stderr，只看 stdout 会把异常读成「没有输出」。"""
    return (proc.stdout or "") + (proc.stderr or "")


# ------------------------------------------------------------------ BUG-44
def test_bug44_struct_selfless_methods_drop_injected_self():
    emit = _emit(BUG44_SRC)
    origin = _sig_lines(emit, "origin")
    named = _sig_lines(emit, "named")
    assert origin == ["def origin():"], f"@staticmethod 签名里仍有注入的 self：{origin}"
    assert named == ["def named(n):"], f"@classmethod 签名里仍有注入的 self：{named}"
    lines = [ln.strip() for ln in emit.splitlines()]
    for deco in ("@staticmethod", "@classmethod"):
        at = lines.index(deco)
        assert (
            lines[at - 1] != "@cython.binding(False)"
        ), f"{deco} 前仍挂着 binding(False)：{lines[at-2:at+2]}"
    # 全类只有 1 个绑定方法 ⇒ binding(False) 恰好 1 条（回退修复后会变成 3 条）
    assert emit.count("@cython.binding(False)") == 1, emit.count("@cython.binding(False)")


def test_bug44_control_bound_struct_method_keeps_self_and_binding():
    """对照：普通 struct 方法必须照旧带 self 与 binding(False)，否则上一条只是"全都不注入"。

    这条对照**只断言绑定方法那半边**：它在回退修复后仍须为绿（binding 总数会被带回 3，
    那是上面那条锁的判据，不能混进对照）。
    """
    emit = _emit(BUG44_SRC)
    shifted = _sig_lines(emit, "shifted")
    assert shifted == ["def shifted(self, dx):"], f"绑定方法签名被改了：{shifted}"
    lines = [ln.strip() for ln in emit.splitlines()]
    assert lines[lines.index("def shifted(self, dx):") - 1] == "@cython.binding(False)", lines


def test_bug44_at_cli_product_is_transpiled_without_self():
    """打到 `cypyc transpile` 调用面：落盘产物里也得是空参形状。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = _write_tmp(tmp, "b44.cypy", BUG44_SRC)
        r = _cli("transpile", str(src), "-o", str(tmp / "out"), "--emit-cython")
        assert r.returncode == 0, _all_text(r)
        pyx = (tmp / "out" / "b44.pyx").read_text(encoding="utf-8")
        assert "def origin():" in pyx, [ln for ln in pyx.splitlines() if "def " in ln]
        assert "def origin(self" not in pyx, "产物仍是修复前的 self 形状"


# ------------------------------------------------------------------ BUG-45
def test_bug45_implicit_default_desugars_to_typed_call():
    emit = _emit(BUG45_SRC)
    proc = _sig_lines(emit, "process")
    assert proc == ["def process(cfg=Config.__implicit_default__()):"], proc
    assert "cfg=__implicit_default__)" not in emit, "裸名形状仍在（导入即 NameError）"


def test_bug45_control_ordinary_default_untouched():
    """对照：普通默认值不得被脱糖逻辑改写。"""
    emit = _emit(BUG45_SRC)
    assert _sig_lines(emit, "plain") == ["def plain(t=5):"], _sig_lines(emit, "plain")


def test_bug45_implicit_default_without_annotation_is_diagnosed():
    """无类型注解时无法确定该调谁的 `__implicit_default__` ⇒ 必须诊断而不是静默出废码。"""
    try:
        Parser(list(Lexer(BUG45_NO_ANNOT_SRC).tokenize())).parse()
    except ValueError as exc:
        assert "needs a parameter type" in str(exc), str(exc)
        assert re.search(r"at \d+:\d+", str(exc)), f"诊断没带行列：{exc}"
    else:
        raise AssertionError("无注解的 __implicit_default__ 仍被静默接受")


# ------------------------------------------------------------------ BUG-39
def test_bug39_toplevel_return_is_diagnosed_at_cli():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = _write_tmp(tmp, "b39.cypy", BUG39_TOPLEVEL_SRC)
        r = _cli("transpile", str(src), "-o", str(tmp / "out"))
        text = _all_text(r)
        assert r.returncode != 0, f"顶层 return 仍被静默接受：{text}"
        assert "must be used inside a function" in text, text
        assert re.search(r"at 4:1\b", text), f"诊断没指向 return 所在行：{text}"


def test_bug39_control_return_inside_function_still_builds():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = _write_tmp(tmp, "b39ok.cypy", BUG39_CONTROL_SRC)
        r = _cli("transpile", str(src), "-o", str(tmp / "out"), "--emit-cython")
        text = _all_text(r)
        assert r.returncode == 0, text
        assert "def ok():" in (tmp / "out" / "b39ok.pyx").read_text(encoding="utf-8")


# -------------------------------------------------------- BUG-39 的反过收窄面
MACRO_DEF_SRC = "macro my_macro(ts: Tokens) -> Tokens =\n    return ts\n"
MACRO_FRAG_SRC = 'print("value: ", (x + y))\nreturn (x + y)\n'


def test_bug39_macro_body_return_stays_legal():
    """`macro … = return ts` 里的 return 是宏的返回语义，守卫不得吃掉它（全量套件抓到的真回归）。"""
    ast = Parser(list(Lexer(MACRO_DEF_SRC).tokenize())).parse()
    kinds = [type(n).__name__ for n in ast.body]
    assert kinds == ["MacroDef"], kinds


def test_bug39_expanded_fragment_return_stays_legal():
    """宏展开出来的是**函数体片段**：`Parser(body_scope=True)` 下 return 必须合法。"""
    ast = Parser(list(Lexer(MACRO_FRAG_SRC).tokenize()), body_scope=True).parse()
    kinds = [type(n).__name__ for n in ast.body]
    assert kinds == ["ExprStmt", "ReturnStmt"], kinds


def test_bug39_control_fragment_without_body_scope_still_rejected():
    """对照：同一形状在 body_scope=False 下仍必须被拒 —— 否则上一条只是"return 无人管"。"""
    try:
        Parser(list(Lexer(MACRO_FRAG_SRC).tokenize())).parse()
    except ValueError as exc:
        assert "must be used inside a function" in str(exc), str(exc)
    else:
        raise AssertionError("未开 body_scope 的片段也放行了顶层 return ⇒ 守卫根本没生效")


# ------------------------------------------------------------------ BUG-35
def test_bug35_parse_diagnosis_is_not_bucketed_as_read_error():
    """解析期诊断不得再写「读取文件错误」；行列信息本来就有，桶名不能撒谎。

    夹具用**顶层 defer**而不是顶层 return：`defer` 的越域诊断是本轮之前就存在的路径，
    这样回退 BUG-39（return 守卫）不会把这条锁一起带红，两单的归因才是分开的。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = _write_tmp(tmp, "b35.cypy", BUG35_DEFER_SRC)
        text = _all_text(_cli("transpile", str(src), "-o", str(tmp / "out")))
        assert "读取文件错误" not in text, text
        assert "编译错误" in text, f"解析诊断丢了桶：{text}"
        assert re.search(r"at 4:7\b", text), f"行列没保住：{text}"


def test_bug35_control_missing_file_still_reports_read_error():
    """对照：真正的 I/O 失败必须留在「读取文件错误」桶里（否则只是把桶改名了）。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        text = _all_text(_cli("transpile", str(tmp / "nope.cypy"), "-o", str(tmp / "out")))
        assert "读取文件错误" in text, text


# ------------------------------------------------------------------ BUG-46
def test_bug46_install_and_status_agree_on_process_scope():
    """两个命令不得互相否定：install 不许声称装好了，status 不许报 [FAIL]。"""
    ins = _cli("hook", "install")
    st = _cli("hook", "status")
    ins_text, st_text = _all_text(ins), _all_text(st)
    assert ins.returncode == 0 and st.returncode == 0, f"{ins_text}\n{st_text}"
    assert "installed successfully" not in ins_text, f"install 仍在声称持久化：{ins_text}"
    assert "[FAIL]" not in st_text, f"status 仍在报 [FAIL]：{st_text}"
    assert "current process" in ins_text, ins_text
    assert "current process" in st_text, st_text


def test_bug46_fresh_process_reports_not_active():
    """对照：进程内注册是真的，跨进程"已装"是假的——新进程必须报未激活。

    探测走 `cypy_hook.hook` 而非包级 API：包级再导出是 BUG-47 的锁，
    回退 47 不得把这条带红（两单归因要分开）。
    """
    r = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            "from cypy_hook.hook import is_hook_installed; print(is_hook_installed())",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert r.returncode == 0, _all_text(r)
    assert r.stdout.strip() == "False", r.stdout + r.stderr


def test_bug46_usage_doc_matches_the_narrowed_claim():
    doc = (ROOT / "docs" / "USAGE.md").read_text(encoding="utf-8")
    assert "写入用户 sitecustomize" not in doc, "手册仍在承诺写 sitecustomize"
    assert "cypy_hook.install_hook()" in doc, "手册没给出跨进程的正确写法"


# ------------------------------------------------------------------ BUG-47
def test_bug47_package_level_hook_api_exists():
    probe = (
        "import cypy_hook\n"
        "names = ('CypyHook', 'install_hook', 'uninstall_hook', 'is_hook_installed')\n"
        "print(','.join(n for n in names if hasattr(cypy_hook, n)))\n"
        "print(','.join(sorted(cypy_hook.__all__)))\n"
        "print(hasattr(cypy_hook, 'is_hook_installed_v2'))\n"
    )
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", probe],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    text = _all_text(r)
    assert r.returncode == 0, text
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "CypyHook,install_hook,uninstall_hook,is_hook_installed", text
    assert set(lines[1].split(",")) == {
        "CypyHook",
        "install_hook",
        "uninstall_hook",
        "is_hook_installed",
    }
    assert lines[2] == "False", "对照名也被 hasattr 命中 ⇒ 探测本身不承重"


def test_bug47_in_process_install_then_uninstall():
    """包级 API 必须真能改状态（同进程内），这是手册 3.x 承诺的编程接口。"""
    probe = (
        "import cypy_hook\n"
        "cypy_hook.install_hook()\n"
        "print(cypy_hook.is_hook_installed())\n"
        "cypy_hook.uninstall_hook()\n"
        "print(cypy_hook.is_hook_installed())\n"
    )
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", probe],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert r.returncode == 0, _all_text(r)
    assert r.stdout.strip().splitlines() == ["True", "False"], r.stdout + r.stderr
