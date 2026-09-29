"""2026-Q3 审计 T0r61.4.2 的永久回归测试：C 后端的异常/错误处理代码生成。

覆盖 cypy_bridge/compiler.py 里被 OMEGA 复现单元证实的缺陷：

1. `_visit_TryStmt` 曾输出**固定**局部量 `_try_result` / `_try_result_obj` /
   `_try_returned`（只有 goto 标签按 buildblock_counter 唯一化）。两个同级
   try/finally 在同一个 C 作用域里重复声明 → MSVC C2374 硬错误，也就是说这种
   函数从来没有编译成功过；嵌套 try 则静默遮蔽外层。
2. try 块头部的无条件 `PyErr_Clear()`、except 子句 if/else **之外**的
   `PyErr_Clear()`，以及非匹配分支 `goto <lbl>_finally` 向前跳进外层处理器尾部
   —— 三者合起来把刚 `PyErr_Restore` 的异常擦掉，异常被静默吞下。
3. `except T as name` 的绑定借用 `_exc_value` 而不 INCREF，且声明的作用域在
   `finally:` 之前就结束（MSVC C2065）。
4. `except ValueError` 经 `_expr_to_str` 输出成裸 C 标识符（缺 `PyExc_` 前缀）。
5. `PyObject*` 返回值的 PyArg 包装器 `Py_INCREF(_result); return _result;`
   没有 NULL 判断 → 被调函数 `return NULL` 时 0xC0000005 崩溃；成功路径还多重
   引用一次（每次调用泄漏一个引用）。

测试分两层：
* 纯源码结构断言（任何机器都能跑）；
* 真实 MSVC 编译/构建并调用（用 `shutil.which("cl")` 守卫，CI 无 MSVC 时跳过）。
"""

import os
import re
import shutil
import subprocess
import sys
import sysconfig
import textwrap

import pytest

from cypy_bridge.compiler import CCodeGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPILER_PY = os.path.join(REPO, "cypy_bridge", "compiler.py")

HAVE_CL = shutil.which("cl") is not None
HAS_PY_HEADERS = os.path.isdir(sysconfig.get_paths()["include"])
needs_msvc = pytest.mark.skipif(
    not (HAVE_CL and HAS_PY_HEADERS),
    reason="需要 MSVC cl.exe 在 PATH 上（vcvars）以及 CPython 开发头文件",
)


def emit(source: str, module_name: str = "regression_mod") -> str:
    """用真实的 Lexer + Parser + CCodeGenerator 生成 C"""
    ast = Parser(Lexer(textwrap.dedent(source)).tokenize()).parse()
    return CCodeGenerator().generate(ast, module_name)


def func_body(c: str, fname: str) -> str:
    """切出一个函数体（到模块尾部注释为止）"""
    start = c.index("%s(" % fname)
    start = c.index("{", start)
    stop = c.index("// Python module:", start)
    return c[start:stop]


SIBLING_SRC = """
def two_sibling_try() -> int:
    try:
        let a: int = 1
    except ValueError as e1:
        let b: int = 2
    finally:
        let c: int = 3

    try:
        let d: int = 4
    except TypeError as e2:
        let f: int = 5
    finally:
        let g: int = 6

    return 0
"""

NESTED_SRC = """
def outer() -> int:
    try:
        raise
    except BaseException as oe:
        try:
            raise
        except ValueError as ie:
            let c: int = 3
        finally:
            let d: int = 4
    finally:
        let e2: int = 5
    return 0
"""

FINALLY_NAME_SRC = """
def outer() -> int:
    try:
        raise
    except ValueError as shown:
        let a: int = 1
    finally:
        let b: int = 2
    return 0
"""


# ---------------------------------------------------------------------------
# 缺陷 1：固定名字的 try 局部量（同级重定义 / 嵌套遮蔽）
# ---------------------------------------------------------------------------

def test_try_block_emits_no_fixed_local_names():
    """三个从未被读过的死局部量应被删除，而不是留着造成重定义"""
    c = emit(SIBLING_SRC)
    for dead in ("_try_result", "_try_result_obj", "_try_returned"):
        assert dead not in c, "%s 仍然被声明（同级 try 会触发 MSVC C2374）" % dead

    src = open(COMPILER_PY, encoding="utf-8").read()
    assert 'self.current_try_result_var = "_try_result"' not in src
    assert "current_try_result_var" not in src


def test_sibling_try_blocks_get_distinct_labels_and_scopes():
    c = emit(SIBLING_SRC)
    body = func_body(c, "two_sibling_try")
    assert "_try_0_except_check:" in body
    assert "_try_1_except_check:" in body

    # `_exc_type` 这类局部量各声明两次，但必须分属两个不同的 {} 作用域：
    # 同一函数同一作用域里的重复声明正是旧的 MSVC C2374。
    assert body.count("PyObject* _exc_type = NULL;") == 2
    blocks = [s for s in body.split("// try/except/finally block")[1:]
              if "PyObject* _exc_type = NULL;" in s]
    assert len(blocks) == 2
    for block in blocks:
        assert block.count("PyObject* _exc_type = NULL;") == 1
    # 每个 try 构造都自带一个块作用域（顶层 `{` 之后紧跟 `{`）
    assert len(re.findall(r"// try/except/finally block\n\s*\{", body)) == 2


@needs_msvc
def test_sibling_try_finally_compiles_with_msvc(tmp_path):
    """两个同级 try/finally 以前从来没被 MSVC 接受过（C2374）"""
    c = emit(SIBLING_SRC, "t61_sibling")
    _cl_compile(tmp_path, "t61_sibling", c)


# ---------------------------------------------------------------------------
# 缺陷 2：PyErr_Clear 吞异常 / 向前 goto 落进外层处理器尾部
# ---------------------------------------------------------------------------

def test_no_pyerr_clear_anywhere_in_try_codegen():
    c = emit(NESTED_SRC)
    body = func_body(c, "outer")
    assert "PyErr_Clear()" not in body
    # _visit_TryStmt 里那两条 PyErr_Clear 输出（try 头部 + 子句尾部）必须已删除；
    # with 语句代码生成里还有同类语句，另行归档（见审计报告“缺口”）
    src = open(COMPILER_PY, encoding="utf-8").read()
    start = src.index("def _visit_TryStmt")
    end = src.index("def _visit_stmts", start)
    assert not re.search(r'self\._write\((?:f)?"[^"]*PyErr_Clear', src[start:end])


def test_no_forward_goto_into_finally_label():
    """非匹配分支靠顺序 fall-through 走到 finally，不再用 goto 跨进外层块尾部"""
    c = emit(NESTED_SRC)
    body = func_body(c, "outer")
    assert not re.search(r"goto\s+_try_\d+_finally\s*;", body)


def test_unmatched_exception_is_restored_and_propagated_after_finally():
    c = emit(NESTED_SRC)
    body = func_body(c, "outer")
    # 内层块：PyErr_Occurred → Fetch → 匹配 → finally → Restore + 传播
    assert "PyErr_Fetch(&_exc_type, &_exc_value, &_exc_tb);" in body
    assert "PyErr_Restore(_exc_type, _exc_value, _exc_tb);" in body
    assert body.count("PyErr_Restore(") == 2  # 内外各一条，且都在块尾
    assert 'if (_exc_type != NULL) {' in body
    # 每条 PyErr_Restore 都紧跟一条错误返回（异常真的传出去）
    for _m in re.finditer(r"PyErr_Restore\([^;]*\);(.*?)\}", body, re.S):
        assert re.search(r"return (NULL|0);", _m.group(1))


def test_matched_exception_is_consumed_not_cleared():
    c = emit(FINALLY_NAME_SRC)
    body = func_body(c, "outer")
    assert "Py_XDECREF(_exc_type);" in body
    assert "Py_XDECREF(_exc_value);" in body
    assert "Py_XDECREF(_exc_tb);" in body
    assert "_exc_type = NULL; _exc_value = NULL; _exc_tb = NULL;" in body


def test_handler_binding_holds_its_own_reference():
    """`except E as name` 必须 INCREF（否则 _exc_value 被 XDECREF 后就是悬垂引用）"""
    c = emit(FINALLY_NAME_SRC)
    body = func_body(c, "outer")
    assert "PyObject* shown = _exc_value ? _exc_value : Py_None;" not in body
    assert "shown = _exc_value ? _exc_value : Py_None;" in body
    assert "Py_INCREF(shown);" in body
    assert "Py_DECREF(shown);" in body


def test_handler_name_is_declared_at_block_scope_so_finally_can_see_it():
    c = emit(FINALLY_NAME_SRC)
    body = func_body(c, "outer")
    decl = body.index("PyObject* shown = NULL;")
    handler_open = body.index("PyErr_GivenExceptionMatches")
    finally_label = body.index("_try_0_finally:")
    assert decl < handler_open < finally_label


@needs_msvc
def test_finally_can_reference_handler_name(tmp_path):
    """`finally:` 引用处理器变量以前是 C2065（未声明标识符）"""
    c = emit(FINALLY_NAME_SRC, "t61_namescope")
    _cl_compile(tmp_path, "t61_namescope", c)


# ---------------------------------------------------------------------------
# 缺陷 3（blocker）：内置异常名缺少 PyExc_ 前缀
# ---------------------------------------------------------------------------

def test_builtin_exception_names_get_the_pyeexc_prefix():
    c = emit(NESTED_SRC)
    body = func_body(c, "outer")
    assert "PyErr_GivenExceptionMatches(_exc_type, PyExc_BaseException)" in body
    assert "PyErr_GivenExceptionMatches(_exc_type, PyExc_ValueError)" in body
    # 裸 C 标识符形式绝不能再出现
    assert not re.search(
        r"PyErr_GivenExceptionMatches\(_exc_type, (?:ValueError|BaseException|TypeError|RuntimeError)\)",
        body)


def test_except_types_of_every_builtin_clause_are_prefixed():
    src = """
def multi() -> int:
    try:
        let a: int = 1
    except ValueError as e:
        let b: int = 2
    except TypeError:
        let c: int = 3
    except KeyError as k:
        let d: int = 4
    return 0
"""
    body = func_body(emit(src), "multi")
    for name in ("PyExc_ValueError", "PyExc_TypeError", "PyExc_KeyError"):
        assert name in body
    # if / else-if 链，只匹配一个子句：一个 `if`，其余子句都是 `} else if`
    assert len(re.findall(r"\n\s*if \(PyErr_GivenExceptionMatches", body)) == 1
    assert body.count("} else if (PyErr_GivenExceptionMatches") == 2
    assert len(re.findall(r"\{", body)) == len(re.findall(r"\}", body))


def test_raise_of_builtin_exception_uses_pyeexc_symbol():
    src = """
def boom() -> int:
    raise ValueError
"""
    body = func_body(emit(src), "boom")
    assert "PyErr_SetNone(PyExc_ValueError);" in body
    assert "PyObject_Type(ValueError)" not in body


def test_raise_builtin_exception_with_message():
    src = """
def boom() -> int:
    raise ValueError("bad input")
"""
    body = func_body(emit(src), "boom")
    assert 'PyErr_SetString(PyExc_ValueError, "bad input");' in body


def test_module_local_exception_like_name_is_not_prefixed():
    """用户自己定义的同名类型不能被改写成 PyExc_*"""
    src = """
class ValueError:
    x: int

def boom() -> int:
    try:
        let a: int = 1
    except ValueError as e:
        let b: int = 2
    return 0
"""
    body = func_body(emit(src, "local_exc"), "boom")
    assert "PyErr_GivenExceptionMatches(_exc_type, PyExc_ValueError)" not in body


@needs_msvc
def test_except_valueerror_compiles_with_msvc(tmp_path):
    """带 `except ValueError` 的函数在补前缀之前不可能通过 MSVC（C2065）"""
    src = """
def guarded(flag: int) -> int:
    let out: int = 0
    try:
        out = flag
    except ValueError as e:
        out = 1
    finally:
        out = out + 1
    return out
"""
    c = emit(src, "t61_exc_prefix")
    _cl_compile(tmp_path, "t61_exc_prefix", c)


# ---------------------------------------------------------------------------
# 缺陷 4：PyObject* 包装器没有 NULL 判断，并且重复 INCREF
# ---------------------------------------------------------------------------

def test_pyobject_wrapper_guards_null_and_does_not_incref_again():
    src = """
def failing() -> PyObject*:
    return NULL
"""
    c = emit(src)
    wrapper = c[c.index("_wrapper"):]
    assert re.search(r"if\s*\(\s*!?_result", wrapper), "缺少 NULL 守卫"
    assert "Py_INCREF(_result);" not in wrapper
    assert "return _result;" in wrapper
    assert "PyExc_SystemError" in wrapper  # NULL 且未置异常时给一个可诊断的错误


def test_every_wrapper_checks_the_error_indicator():
    src = """
def give_int() -> int:
    return 1

def give_obj() -> PyObject*:
    return NULL

def give_void() -> void:
    return
"""
    c = emit(src)
    wrappers = re.findall(r"static PyObject\* _\w+_wrapper\(PyObject\* self, PyObject\* args\)"
                          r" \{(.*?)\n\}", c, re.S)
    assert len(wrappers) >= 3
    for w in wrappers:
        assert "PyErr_Occurred()" in w, "包装器把失败静默转换成 0/None"


def _build_module(tmp_path, name, c):
    """把生成的 C 用真实工具链编成 .pyd（setuptools build_ext --inplace）"""
    cdir = tmp_path / name
    cdir.mkdir()
    (cdir / (name + ".c")).write_text(c, encoding="utf-8", newline="\n")
    (cdir / ("setup_%s.py" % name)).write_text(
        "from setuptools import setup, Extension\n"
        "setup(name=%r, ext_modules=[Extension(%r, [%r])],\n"
        "      script_args=['build_ext', '--inplace'])\n" % (name, name, name + ".c"),
        encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env["VSLANG"] = "1033"
    p = subprocess.run([sys.executable, "setup_%s.py" % name], cwd=str(cdir), env=env,
                       capture_output=True, timeout=580)
    if p.returncode != 0:
        out = (p.stdout or b"") + (p.stderr or b"")
        pytest.fail("MSVC 构建失败:\n" + out.decode("utf-8", "replace")[-4000:])
    return str(cdir)


def _cl_compile(tmp_path, name, c):
    """只做 `cl /c` 编译（不解链接），验证生成的 C 语法/作用域正确"""
    cdir = tmp_path / name
    cdir.mkdir()
    path = cdir / (name + ".c")
    path.write_text(c, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env["VSLANG"] = "1033"
    p = subprocess.run([shutil.which("cl"), "/nologo", "/c",
                        "/I" + sysconfig.get_paths()["include"], name + ".c"],
                       cwd=str(cdir), env=env, capture_output=True, timeout=300)
    diag = ((p.stdout or b"") + (p.stderr or b"")).decode("utf-8", "replace")
    assert p.returncode == 0, "cl /c 失败:\n" + diag[-4000:]
    # 这些正是审计里出现过的硬错误
    for code in ("C2374", "C2086", "C2065", "C2011"):
        assert code not in diag, "%s 出现在 MSVC 诊断里:\n%s" % (code, diag[-4000:])
    return diag


@needs_msvc
def test_real_pyd_propagates_the_unmatched_exception(tmp_path):
    """真实 .pyd：内层只 catch ValueError，RuntimeError 必须逃出 outer()

    修复前实测是 `outer()` 返回 0 且没有任何异常（被 PyErr_Clear 擦掉），
    PyObject* 版本则直接 0xC0000005 崩掉解释器。
    """
    src = NESTED_SRC + """
def failing() -> PyObject*:
    return NULL

def good_obj() -> PyObject*:
    return Py_None
"""
    name = "t61_runtime"
    mod_dir = _build_module(tmp_path, name, emit(src, name))
    code = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "import %s as m\n"
        "import sys\n"
        "try:\n"
        "    rv = m.outer()\n"
        "    print('NO-RAISE', repr(rv))\n"
        "except BaseException as e:\n"
        "    print('RAISED', type(e).__name__)\n"
        "try:\n"
        "    print('OBJ', repr(m.failing()))\n"
        "except BaseException as e:\n"
        "    print('OBJ-ERR', type(e).__name__)\n"
        "print('GOOD', m.good_obj() is None)\n"
        % (mod_dir, name))
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=180)
    out = ((p.stdout or b"") + (p.stderr or b"")).decode("utf-8", "replace")
    assert p.returncode == 0, "子进程异常终止（很可能是访问违例）:\n" + out
    assert "RAISED RuntimeError" in out, out
    assert "OBJ-ERR SystemError" in out, out
    assert "GOOD True" in out, out
