"""第七遍打磨（2026-09-26）的回归锁：BUG-15..BUG-29，每单至少 1 条。

口径与 `tests/test_polish_20260926.py`（BUG-1..12）一致：每条测试先能锁死该缺陷本身
（拿修复前的产品代码跑必然红），必要时再配一条**对照**用例，防止"修到另一处/改坏了判据"
被当成修好。BUG-25/26 两处是编译期外溢到文件系统与平台的形态，本机无法真跑 Linux 构建，
故按该文件既有先例（BUG-2 用 inspect 锁 subprocess 参数）锁源码不变式，并在名字里点明锁的是什么。
"""
from __future__ import annotations

import ctypes
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cypyc.codegen.cython_generator import CythonGenerator          # noqa: E402
from cypyc.parser.lexer import Lexer                                 # noqa: E402
from cypyc.parser.parser import Parser                               # noqa: E402


def _parse(src: str):
    return Parser(Lexer(src).tokenize()).parse()


def _cython(src: str) -> str:
    out = CythonGenerator().generate(_parse(src))
    return out if isinstance(out, str) else getattr(out, "cython_code", "")


# ---------------------------------------------------------------- BUG-15 lexer.py:538
def test_bug15_stray_double_backtick_does_not_swallow_rest_of_file():
    src = 'def a() -> int:\n    return 1\n``\ndef b() -> int:\n    return 2\n'
    ast = _parse(src)
    defs = sorted(n.name for n in ast.body if n.kind == "FuncDef")
    # 只查"生成物里有没有 def b 这段文本"是假锁：被吞进 BACKTICK_BLOCK 的内容会原样
    # 出现在产物里，修复前后都绿。必须查 AST 层面 def b 还是不是一个真定义。
    assert defs == ["a", "b"], f"def b 被吞进反引号块，顶层只剩 {defs}（BUG-15）"


def _kinds(src: str):
    return [str(t.type) for t in Lexer(src).tokenize()]


def test_bug15_real_triple_backtick_block_still_lexes_as_macro_block():
    assert "BACKTICK_BLOCK" in _kinds("let x = ```\nraw code\n```\n"), \
        "真三反引号宏捕获被改坏（BUG-15 对照）"


# ---------------------------------------------------------------- BUG-16 parser.py:1375
_PLAIN_VALUE_STRUCT = '@value struct Config:\n    let w: int\n'
_DECORATED_MEMBER_STRUCT = ('@value struct Config:\n    let w: int\n'
                            '    @python def label() -> str:\n        return "x"\n')


def test_bug16_value_struct_keeps_decorators_when_a_member_is_decorated():
    assert "__eq__" in _cython(_PLAIN_VALUE_STRUCT), "对照组本身失效了"
    code = _cython(_DECORATED_MEMBER_STRUCT)
    assert "__eq__" in code, "成员装饰器覆写了 struct 自己的 @value（BUG-16）"


def test_bug16_struct_def_does_not_inherit_a_member_decorator():
    node = next(n for n in _parse(_DECORATED_MEMBER_STRUCT).body if n.kind == "StructDef")
    names = [getattr(getattr(d, "name", None), "value", None) or getattr(d, "name", None)
             for d in node.decorators]
    assert "python" not in [str(x) for x in names], f"struct 挂上了成员的装饰器 {names}（BUG-16）"


# ---------------------------------------------------------------- BUG-17 project_compiler.py:666
def test_bug17_pick_extension_returns_none_for_unrelated_artifacts(tmp_path):
    from cypyc.project.project_compiler import ProjectCompiler
    foreign = str(tmp_path / "other_module.cp313-win_amd64.pyd")
    assert ProjectCompiler._pick_extension([foreign], "mymod", str(tmp_path)) is None


def test_bug17_pick_extension_still_prefers_the_matching_artifact(tmp_path):
    from cypyc.project.project_compiler import ProjectCompiler
    import sysconfig
    suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".pyd"
    mine = str(tmp_path / f"mymod{suffix}")
    other = str(tmp_path / f"zzz{suffix}")
    assert ProjectCompiler._pick_extension([other, mine], "mymod", str(tmp_path)) == mine


# ---------------------------------------------------------------- BUG-18 incremental_manager.py:311
def _inc_with_dep(tmp_path, dep, recorded_hash):
    from cypyc.incremental.incremental_manager import CompilationCacheEntry, IncrementalCompiler
    inc = IncrementalCompiler(cache_dir=str(tmp_path / "cache"))
    inc._compilation_cache[inc._compute_file_key(str(dep))] = CompilationCacheEntry(
        file_hash=recorded_hash, timestamp=9e18)
    inc._find_module_file = lambda name: str(dep) if name == dep.stem else None
    return inc


def test_bug18_changed_dependency_invalidates_the_importer(tmp_path):
    dep = tmp_path / "dep.cypy"
    dep.write_text("let a = 1\n", encoding="utf-8")
    inc = _inc_with_dep(tmp_path, dep, "deadbeefdeadbeef")          # 缓存里记的是旧摘要
    assert inc._check_imported_modules_changed(["dep"]) is True


def test_bug18_unchanged_dependency_stays_a_cache_hit(tmp_path):
    dep = tmp_path / "dep.cypy"
    dep.write_text("let a = 1\n", encoding="utf-8")
    from cypyc.incremental.incremental_manager import IncrementalCompiler
    real = IncrementalCompiler(cache_dir=str(tmp_path / "c2"))._compute_file_hash(str(dep))
    inc = _inc_with_dep(tmp_path, dep, real)
    assert inc._check_imported_modules_changed(["dep"]) is False


def test_bug18_dependency_without_any_cache_entry_is_still_changed(tmp_path):
    dep = tmp_path / "dep.cypy"
    dep.write_text("let a = 1\n", encoding="utf-8")
    inc = _inc_with_dep(tmp_path, dep, "deadbeefdeadbeef")
    inc._compilation_cache.clear()
    assert inc._check_imported_modules_changed(["dep"]) is True


# ---------------------------------------------------------------- BUG-19 cython_generator.py:1287
def test_bug19_owned_import_is_inserted_below_cython_directives():
    lines = _cython('def f() -> None:\n    owned p = malloc(8)\n    return\n').splitlines()
    first_code = next(i for i, ln in enumerate(lines) if ln.strip() and not ln.lstrip().startswith("#"))
    assert lines[0].startswith("# cython:"), f"指令不再位于首行：{lines[:2]}"
    assert "cypy_bridge.pointer" in "".join(lines[first_code:first_code + 2])


# ---------------------------------------------------------------- BUG-20 comptime_evaluator.py:158
def _call_node(recv, attr):
    from cypyc.parser import parser as P
    holder = {"Attribute": getattr(P, "Attribute", None), "Constant": getattr(P, "Constant", None),
              "Call": getattr(P, "Call", None)}
    assert all(holder.values()), f"parser 缺少节点类: {list(holder)}"
    a = holder["Attribute"].__new__(holder["Attribute"])
    a.value = holder["Constant"].__new__(holder["Constant"])
    a.value.value = recv
    a.value.kind = "Constant"
    a.attr = attr
    a.kind = "Attribute"
    c = holder["Call"].__new__(holder["Call"])
    c.func = a
    c.args = []
    c.kind = "Call"
    return c


def test_bug20_comptime_can_evaluate_attribute_method_calls():
    from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator
    got = ComptimeEvaluator().evaluate(_call_node("abc", "upper"))
    assert got == "ABC", f"字符串方法表仍不可达，得到 {got!r}（BUG-20）"


def test_bug20_builtin_name_calls_are_untouched():
    from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator
    from cypyc.parser import parser as P
    fn = P.Name.__new__(P.Name)
    fn.id, fn.kind = "int", "Name"
    arg = P.Constant.__new__(P.Constant)
    arg.value, arg.kind = "42", "Constant"
    call = P.Call.__new__(P.Call)
    call.func, call.args, call.kind = fn, [arg], "Call"
    assert ComptimeEvaluator().evaluate(call) == 42, "Name 分支被 Attribute 路由打坏（BUG-20 对照）"


def test_bug20_unknown_attribute_method_degrades_to_none_without_raising():
    from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator
    assert ComptimeEvaluator().evaluate(_call_node("abc", "no_such_method")) is None


# ---------------------------------------------------------------- BUG-21 type_checker.py:432
def test_bug21_generic_impl_registers_the_base_type_name():
    from cypyc.analyzer.type_checker import TypeChecker
    src = ('trait Show:\n    def show(self) -> str\n'
           'struct Box:\n    let v: int\n'
           'impl Show for Box<T>:\n    def show(self) -> str:\n        return "b"\n')
    tc = TypeChecker()
    tc.check(_parse(src))
    vals = [str(v) for v in tc.trait_impls.get("Show", [])]
    assert vals == ["Box"], f"trait 登记表里是节点 repr：{vals}（BUG-21）"
    assert not any("(" in v for v in vals)


# ---------------------------------------------------------------- BUG-22 lexer.py:654
@pytest.mark.parametrize("prefix", ['f', 'F', 'rf', 'fr', 'Rf', 'rF', 'r'])
def test_bug22_string_prefixes_lex_as_one_string_token(prefix):
    toks = [t for t in Lexer(f'let s = {prefix}"x"\n').tokenize()]
    strings = [t for t in toks if str(t.type) == "STRING"]
    idents = [t.value for t in toks if str(t.type) == "IDENTIFIER"]
    assert len(strings) == 1, f'{prefix}"x" 没有被识别成一个字符串 token（BUG-22）'
    assert idents == ["s"], f'前缀被拆成了标识符：{idents}（BUG-22）'
    assert strings[0].prefix == prefix


def test_bug22_two_char_names_are_not_swallowed_as_prefixes():
    # 这些标识符的首两字符正好落在 f/F + r/R 组合上：前缀必须紧跟引号才算前缀。
    # 本条同时锁住 BUG-22 第一版修复自己引入的回归（`free(` 被 lex 成空前缀字符串）。
    for src, want in [("let rr = 1\n", ["rr"]),
                      ("x = free(y)\n", ["x", "free", "y"]),
                      ("x = readfile(y)\n", ["x", "readfile", "y"]),
                      ("x = format(y)\n", ["x", "format", "y"]),
                      ("x = raw(y)\n", ["x", "raw", "y"])]:
        toks = list(Lexer(src).tokenize())
        strs = [t for t in toks if str(t.type) == "STRING"]
        idents = [t.value for t in toks if str(t.type) == "IDENTIFIER"]
        assert not strs, f'{src!r} 里的标识符被吞成了字符串：{[t.value for t in strs]}'
        assert idents == want, f"{src!r} 标识符被改写：{idents}"


# ---------------------------------------------------------------- BUG-23 pointer.py:322
def test_bug23_addr_of_void_p_returns_pointed_value_including_null():
    from cypy_bridge.pointer import addr
    assert addr(ctypes.c_void_p(4096)) == 4096
    assert addr(ctypes.c_void_p(0)) == 0


def test_bug23_addr_of_scalar_still_returns_storage_address():
    from cypy_bridge.pointer import addr
    box = ctypes.c_int(42)
    got = addr(box)
    assert isinstance(got, int) and got == ctypes.addressof(box)


# ---------------------------------------------------------------- BUG-24 hook.py:1020
def test_bug24_clear_all_cache_actually_removes_cached_files(tmp_path, monkeypatch):
    from cypy_hook.hook import CypyCacheManager
    cache = tmp_path / "__pycache__" / "cypy"
    cache.mkdir(parents=True)
    victim = cache / "manifest.json"
    victim.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    CypyCacheManager().clear_cache()
    assert not victim.exists(), "无参 clear_cache() 删了 0 个文件（BUG-24）"


# ---------------------------------------------------------------- BUG-25 compiler.py:3766/3807
def test_bug25_generated_c_and_setup_are_written_as_utf8():
    import cypy_bridge.compiler as comp
    src = inspect.getsource(comp.BridgeCompiler._compile_c_to_shared_lib)
    offenders = [ln.strip() for ln in src.splitlines()
                 if "open(" in ln and "'w'" in ln and "encoding" not in ln]
    assert not offenders, f"仍有按本地编码写盘的站点：{offenders}（BUG-25）"


# ---------------------------------------------------------------- BUG-26 compiler.py:3833
def test_bug26_artifact_scan_accepts_non_windows_extensions():
    import cypy_bridge.compiler as comp
    src = inspect.getsource(comp.BridgeCompiler._compile_c_to_shared_lib)
    scan = [ln for ln in src.splitlines() if "endswith('.pyd')" in ln
            or 'endswith(".pyd")' in ln]
    assert scan and all((".so" in ln or ".dll" in ln) for ln in scan), \
        "产物扫描仍只认 .pyd，Linux/macOS 成功构建会被报成失败（BUG-26）"


# ---------------------------------------------------------------- BUG-27 hot_reload.py:530
def test_bug27_delete_only_batch_does_not_blame_the_user_callback():
    from cypyc.incremental.hot_reload import HotReloadEngine
    src = inspect.getsource(HotReloadEngine._handle_file_changes)
    assert "set().union(" in src, \
        "空 results 仍会让 set.union 抛 TypeError 并被报成回调错误（BUG-27）"


# ---------------------------------------------------------------- BUG-28 indent_detector.py:30
def test_bug28_normalize_preserves_structure_of_two_space_sources():
    from cypyc.utils.indent_detector import IndentDetector
    src = "def f():\n  let a = 1\n  if a:\n    let b = 2\n"
    assert IndentDetector().detect(src) == ("spaces", 2), "宽度推断仍取 4（BUG-28）"
    out = IndentDetector().normalize(src)
    lines = out.splitlines()
    assert lines[1] == "  let a = 1" and lines[3] == "    let b = 2", \
        f"函数体被压平/层数错乱：{out!r}（BUG-28）"
    assert IndentDetector().normalize(out) == out, "normalize 不幂等"


def test_bug28_four_space_and_six_space_styles_unchanged():
    from cypyc.utils.indent_detector import IndentDetector
    four = "def f():\n    let a = 1\n    if a:\n        let b = 2\n"
    assert IndentDetector().normalize(four) == four
    assert IndentDetector().detect("def f():\n      let a = 1\n") == ("spaces", 6)


# ---------------------------------------------------------------- BUG-29 hook.py:836
def test_bug29_bare_hook_command_reports_usage_not_a_traceback():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-m", "cypyc", "hook"], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=120)
    err = (r.stderr or "") + (r.stdout or "")
    assert "TypeError" not in err, f"裸 TypeError 又回来了：{err[-300:]}"
    assert r.returncode == 1 and "no source file" in err.lower(), err[-300:]


# ---------------------------------------------------------------- BUG-13 tests/test_incremental.py:532
INC_SRC = (ROOT / "tests" / "test_incremental.py").read_text(encoding="utf-8")


def _class_block(name: str) -> str:
    start = INC_SRC.index(f"class {name}:")
    rest = INC_SRC[start + 1:]
    nxt = rest.find("\nclass ")
    return INC_SRC[start:] if nxt < 0 else INC_SRC[start:start + nxt + 1]


def test_bug13_digest_cost_is_judged_on_cpu_time_not_heap_dependent_wall():
    block = _class_block("TestDigestCost")
    dig = block[block.index("differ = ASTDiffer()"):block.index("assert digest_elapsed")]
    assert "time.process_time()" in dig, "摘要代价仍在用墙钟判（BUG-13）"
    assert "time.perf_counter()" not in dig, "摘要计时里仍混着墙钟（BUG-13）"
    assert "assert digest_elapsed < 2.0" in block, "阈值被顺手放宽而不是换量纲"
    linear = block[block.index("def test_digest_cost_scales_linearly"):]
    assert "time.process_time()" in linear and "time.perf_counter()" not in linear, \
        "线性比例判据仍随堆涨落（BUG-13）"


def test_bug13_other_timers_not_silently_loosened():
    # 对照：只换摘要的量纲，parse/compare 两条既有时限不许被顺手放宽或删掉。
    block = _class_block("TestDigestCost")
    assert "assert compare_elapsed < 5.0" in block and "assert parse_elapsed < 60.0" in block
    assert "large_elapsed < small_elapsed * 12 + 0.5" in block


# ---------------------------------------------------------------- BUG-14 codegen/type_mapper.py:8
def test_bug14_one_declared_float_has_one_width_in_both_maps():
    from cypyc.codegen.type_mapper import TypeMapper
    tm = TypeMapper()
    assert tm.to_cython("float") == "double", "cypy_to_cython 仍出 C float（BUG-14）"
    assert tm.to_cython("float") == tm.to_c("float"), "两张表对 float 仍分叉（BUG-14）"
    assert tm.to_cython("double") == "double" and tm.to_c("double") == "double"


def test_bug14_no_single_precision_cast_survives_in_transpile():
    code = _cython((ROOT / "examples" / "subtype_units.cypy").read_text(encoding="utf-8"))
    assert "<float>" not in code, "产物里仍出 C 单精度强转（BUG-14）"
    assert "<double>" in code, "显式 as float 不再产生任何窄化转换，需回看转换路径"


# ---------------------------------------------------------------- BUG-32 codegen/cython_generator.py:3334
def test_bug32_constraint_comment_echoes_declared_member_names():
    code = _cython("constraint Numeric = int | float | double\n"
                   "def f(v: Numeric) -> int:\n    return v\n")
    assert "# constraint Numeric = int | float | double" in code, \
        "约束注释被 type_mapper 改写过（BUG-32：裁决后 float 会打成 double）"
    assert "int | double" not in code.replace("int | float | double", "")


def test_bug32_alias_still_takes_the_ruled_width():
    # 对照：`type` 别名是**真声明**，它必须吃到 BUG-14 裁决的宽度 —— 别把修 BUG-32 变成修掉裁决。
    code = _cython("type N = float\nlet x: N = 1.0\nprint(x)\n")
    assert "ctypedef double N" in code, f"别名没走映射，裁决被顺手中止:\n{code}"


def test_bug32_constraint_comment_resolves_subtype_members_to_base_names():
    # 逐字回显不得越过 S-4.1：子类型名一律不许出现在产物里，要化成基类型名。
    code = _cython("subtype Meter <: float\n"
                   "constraint Length = Meter | float\n"
                   "def f(v: Length) -> float:\n    return v\n")
    assert "# constraint Length = float | float" in code, code
    assert "Meter" not in code
