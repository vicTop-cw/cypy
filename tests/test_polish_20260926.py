"""Polish round 2026-09-26 regressions — one test per confirmed bug in memory/bugs.md.

Each test pins the *loud* behaviour that replaces a silent degradation; none of them
compiles C code, so they stay deterministic. Bug ids refer to this round's ledger
(memory/bugs.md, ns=cypy-polish-20260926).
"""
import ast
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --------------------------------------------------------------------------- BUG-1
def test_bug1_clear_cache_does_not_claim_success_when_remove_fails(tmp_path, monkeypatch):
    from cypy_bridge import compiler as compiler_mod
    from cypy_bridge.compiler import BridgeCacheManager

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    pyd = cache_dir / "mod.cp312-win_amd64.pyd"
    pyd.write_bytes(b"\x00")
    manifest = cache_dir / "bridge_manifest.json"
    mgr = BridgeCacheManager()
    monkeypatch.setattr(mgr, "_get_base_cache_dir", lambda source_path=None: str(cache_dir))
    monkeypatch.setattr(mgr, "_get_manifest_path", lambda source_path=None: str(manifest))
    manifest.write_text(json.dumps({"mod": {"hash": "h", "pyd_path": str(pyd), "timestamp": 0}}),
                        encoding="utf-8")

    def refuse(path, *a, **kw):
        raise OSError(13, "Permission denied", path)

    monkeypatch.setattr(compiler_mod.os, "remove", refuse)
    mgr.clear_cache("mod")

    assert pyd.exists(), "删除失败却被当作已清理"
    assert "mod" in json.loads(manifest.read_text(encoding="utf-8")), \
        "manifest 条目在 .pyd 仍存在时被删掉，缓存状态与磁盘不一致"


# --------------------------------------------------------------------------- BUG-2
def test_bug2_bridge_build_subprocess_run_passes_timeout():
    path = os.path.join(ROOT, "cypy_bridge", "compiler.py")
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    runs = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "run" and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "subprocess"]
    assert runs, "cypy_bridge/compiler.py 里找不到 subprocess.run 调用，判据需同步更新"
    missing = [n.lineno for n in runs if not any(k.arg == "timeout" for k in n.keywords)]
    assert not missing, (
        f"subprocess.run 缺 timeout（行 {missing}）：同仓 cypy_hook/hook.py 与 "
        "cypyc/project/project_compiler.py 的同类调用都传 timeout=120")


def test_bug2_build_timeout_is_shared_with_sibling_callers():
    """三处 build_ext 子进程共用同一超时口径，避免再次各写各的。"""
    with open(os.path.join(ROOT, "cypy_bridge", "compiler.py"), "r", encoding="utf-8") as f:
        bridge = f.read()
    assert "BUILD_TIMEOUT" in bridge, "cypy_bridge 未使用统一的 BUILD_TIMEOUT 常量"


# --------------------------------------------------------------------------- BUG-3
def test_bug3_reparse_failure_is_reported_not_swallowed(capsys):
    from cypyc.project.project_compiler import ProjectCompiler

    class Graph:
        def get_module_by_path(self, path):
            return "mod_a"

        def get_affected_modules(self, names):
            return set(names) | {"mod_b"}

    comp = ProjectCompiler.__new__(ProjectCompiler)
    comp._source_files = {"mod_a": "/tmp/mod_a.cypy"}
    comp._dependency_graph = Graph()
    comp._reparse_module = lambda name: (_ for _ in ()).throw(ValueError("lexer blew up"))

    affected = comp.get_incremental_changes({"/tmp/mod_a.cypy"})

    err = capsys.readouterr().err
    assert "mod_a" in err, "重解析失败后仍按陈旧 AST 继续，且无任何告警"
    assert affected, "该函数仍应返回受影响集合"


# --------------------------------------------------------------------------- BUG-4
def _silent_handlers(tree):
    """Yield Try nodes whose body ends up swallowing every sub-node error."""
    def is_silent(handler):
        if not all(isinstance(stmt, (ast.Pass, ast.Continue)) for stmt in handler.body):
            return False
        if handler.type is None:
            return True
        if isinstance(handler.type, ast.Name):
            names = [handler.type.id]
        elif isinstance(handler.type, ast.Tuple):
            names = [e.id for e in handler.type.elts if isinstance(e, ast.Name)]
        else:
            names = []
        return any(n in {"Exception", "BaseException", "AttributeError", "TypeError",
                         "ValueError", "RuntimeError", "OSError"} for n in names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(is_silent(h) for h in node.handlers):
            yield node


@pytest.mark.parametrize("module", ["defer", "enum", "generic", "struct", "trait"])
def test_bug4_transformer_recursion_is_outside_broad_try(module):
    """getattr 可以容错，遍历本身不行：递归落在静默 try 体内时，子节点报错会被
    当成『正常结束』，defer/struct/trait 因此静默漏收集。"""
    path = os.path.join(ROOT, "cypyc", "transformer", f"{module}_transformer.py")
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    offenders = []
    for try_node in _silent_handlers(tree):
        for call in (c for c in ast.walk(try_node) if isinstance(c, ast.Call)):
            if (isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "self"
                    and call.func.attr.startswith("_collect")):
                offenders.append(f"{call.func.attr}@{call.lineno}")
    assert not offenders, (
        f"{module}_transformer 的递归收集被静默 try 包住: {offenders}")


# --------------------------------------------------------------------------- BUG-5
def test_bug5_state_snapshot_reports_getattr_failure(capsys):
    from cypyc.incremental.hot_reload import CypyProxyModule

    class Exploding:
        """模块对象的 __dir__ 只列 __dict__，类属性进不去，所以这里用普通对象。"""

        @property
        def counter(self):
            raise RuntimeError("broken descriptor")

    proxy = CypyProxyModule.__new__(CypyProxyModule)
    proxy._actual_module = Exploding()
    proxy._state_cache = {}
    proxy._attr_cache = {}
    proxy._cache_enabled = True

    proxy._save_state()

    assert "counter" in capsys.readouterr().err, \
        "_save_state 静默丢掉了一个取不到的状态名"


def test_bug5_state_restore_reports_setattr_failure(capsys):
    from cypyc.incremental.hot_reload import CypyProxyModule

    class ReadOnly(types.ModuleType):
        counter = 0

        @property
        def locked(self):
            return 1

    mod = ReadOnly("polish_mod")
    proxy = CypyProxyModule.__new__(CypyProxyModule)
    proxy._actual_module = mod
    proxy._state_cache = {"locked": 5}
    proxy._attr_cache = {}
    proxy._cache_enabled = True

    proxy._restore_state()

    err = capsys.readouterr().err
    if "AttributeError" in str(type(mod.locked)):
        pytest.skip("平台允许写 property，回滚未失败")
    assert "locked" in err, "_restore_state 静默跳过了回滚失败的状态名"


# --------------------------------------------------------------------------- BUG-6
def test_bug6_cypy_file_with_bom_is_still_detected(tmp_path):
    from cypyc.incremental.file_monitor import CypyFileMonitor

    target = tmp_path / "boot.py"
    target.write_bytes("﻿#!bin cypy\nprint(1)\n".encode("utf-8"))
    monitor = CypyFileMonitor([str(tmp_path)], callback=lambda events: None)
    assert monitor._is_cypy_file(str(target)), \
        "带 BOM 的 #!bin cypy 入口被判定为普通 Python 文件，热重载静默漏编译"


def test_bug6_unreadable_cypy_candidate_warns(tmp_path, capsys):
    from cypyc.incremental.file_monitor import CypyFileMonitor

    directory = tmp_path / "weird.py"
    directory.mkdir()
    monitor = CypyFileMonitor([str(tmp_path)], callback=lambda events: None)
    assert monitor._is_cypy_file(str(directory)) is False
    assert "weird.py" in capsys.readouterr().err, \
        "读不到的 .py 候选被静默归类为『不是 Cypy 文件』"


# --------------------------------------------------------------------------- BUG-7
def test_bug7_corrupt_manifest_warns(capsys, tmp_path):
    from cypy_hook.hook import CypyCacheManager

    mgr = CypyCacheManager.__new__(CypyCacheManager)
    manifest = tmp_path / "mod.cython.json"
    manifest.write_text("{ this is not json", encoding="utf-8")
    mgr._get_manifest_path = lambda source_path: str(manifest)

    assert mgr._load_manifest(str(tmp_path / "mod.py")) == {}
    assert "mod.cython.json" in capsys.readouterr().err, \
        "manifest 损坏被当成『无缓存』，重新编译原因不可见"


def test_bug7_corrupt_bridge_manifest_warns(capsys, tmp_path, monkeypatch):
    from cypy_bridge.compiler import BridgeCacheManager

    manifest = tmp_path / "bridge_manifest.json"
    manifest.write_text("{ nope", encoding="utf-8")
    mgr = BridgeCacheManager()
    monkeypatch.setattr(mgr, "_get_manifest_path", lambda source_path=None: str(manifest))

    assert mgr._load_manifest() == {}
    assert "bridge_manifest.json" in capsys.readouterr().err


# --------------------------------------------------------------------------- BUG-8
def test_bug8_macro_reparse_degradation_is_reported(capsys):
    from cypyc.parser.macro_expander import MacroExpander, BacktickBlock

    expander = MacroExpander.__new__(MacroExpander)
    node = expander._reparse_code("def (", 7, 3)

    assert isinstance(node, BacktickBlock), "降级分支仍应返回原始代码块（语义不变）"
    err = capsys.readouterr().err
    assert "7" in err, "整条宏语句消失却无任何告警"
    assert "def (" in err, "告警要点名被丢弃的代码"


# ---------------------------------------------------------------------------
# Second sweep (2026-09-26): the remaining `except Exception: pass` sites that
# the first round's BUG-5 / BUG-3 fixes did not reach.
# ---------------------------------------------------------------------------

class _BrokenDescriptorModule:
    visible = 1

    @property
    def broken(self):
        raise RuntimeError("broken descriptor")


class _ReadOnlyModule:
    def __setattr__(self, name, value):
        raise AttributeError("read-only module")


class _RecordingIncrementalCompiler:
    """Records cache/dependency writes so a test can prove the parse really failed."""

    def __init__(self):
        self.calls = []

    def analyze_changes(self, source_path, ast):
        self.calls.append(("analyze_changes", source_path))

    def get_dependency_graph(self):
        return None

    def update_cache(self, source_path, ast):
        self.calls.append(("update_cache", source_path))


def test_bug9_module_state_snapshot_warns(capsys):
    import sys
    from cypyc.incremental.hot_reload import HotReloadEngine

    sys.modules["cypy_polish_bug9a"] = _BrokenDescriptorModule()
    try:
        reloader = HotReloadEngine.__new__(HotReloadEngine)
        reloader._module_state = {}
        reloader._save_module_state("cypy_polish_bug9a")
    finally:
        sys.modules.pop("cypy_polish_bug9a", None)

    err = capsys.readouterr().err
    assert "broken" in err, f"_save_module_state 静默丢掉了取不到的状态: {err!r}"
    assert reloader._module_state["cypy_polish_bug9a"] == {"visible": 1}


def test_bug9_module_state_restore_warns(capsys):
    import sys
    from cypyc.incremental.hot_reload import HotReloadEngine

    sys.modules["cypy_polish_bug9b"] = _ReadOnlyModule()
    try:
        reloader = HotReloadEngine.__new__(HotReloadEngine)
        reloader._module_state = {"cypy_polish_bug9b": {"counter": 7}}
        reloader._restore_module_state("cypy_polish_bug9b")
    finally:
        sys.modules.pop("cypy_polish_bug9b", None)

    err = capsys.readouterr().err
    assert "counter" in err, f"_restore_module_state 静默跳过了写不回去的状态: {err!r}"


def test_bug10_dependency_analysis_parse_failure_warns(capsys, tmp_path):
    from cypyc.incremental.hot_reload import HotReloadEngine

    missing = tmp_path / "mod_a.cypy"
    compiler = _RecordingIncrementalCompiler()
    reloader = HotReloadEngine.__new__(HotReloadEngine)
    reloader._incremental_compiler = compiler
    reloader._module_source_map = {}
    reloader._module_dependencies = {}
    reloader._analyze_module_dependencies(str(missing), "mod_a")

    err = capsys.readouterr().err
    assert compiler.calls == [], "源文件读取失败却没走进该告警站点，判据未绑定"
    assert "mod_a" in err, f"依赖分析失败被完全吞掉: {err!r}"
    assert "No such file" in err or "FileNotFound" in err, \
        f"告警应带上根因，方便定位: {err!r}"


def test_bug10_cache_update_parse_failure_warns(capsys, tmp_path):
    from cypyc.incremental.hot_reload import HotReloadEngine
    from types import SimpleNamespace

    missing = tmp_path / "mod_b.cypy"

    class _Hook:
        def compile_to_pyd(self, *args, **kwargs):
            # 走到「更新增量编译缓存」那段必须让编译先“成功”，否则测的是失败分支
            return SimpleNamespace(success=True,
                                   pyd_path=str(tmp_path / "mod_b.cp312-win_amd64.pyd"),
                                   errors=[])

    compiler = _RecordingIncrementalCompiler()
    reloader = HotReloadEngine.__new__(HotReloadEngine)
    reloader._hook = _Hook()
    reloader._cache_manager = None
    reloader._incremental_compiler = compiler
    reloader._module_state = {}
    reloader._proxy_modules = {}
    reloader._module_source_map = {}
    reloader._module_dependencies = {}
    result = reloader._compile_and_reload_module(str(missing))

    err = capsys.readouterr().err
    assert compiler.calls == [], "缓存更新失败却没走进该告警站点，判据未绑定"
    assert "mod_b" in err, f"增量缓存更新失败被静默跳过: {err!r}, result={result!r}"


def _project_compiler(tmp_path, name, source):
    """Build a real one-module project and return (ProjectCompiler, module_name)."""
    from cypyc.project.project_compiler import ProjectCompiler

    (tmp_path / f"{name}.cypy").write_text(source, encoding="utf-8")
    compiler = ProjectCompiler(project_root=str(tmp_path),
                               output_dir=str(tmp_path / "_out"))
    compiler.discover_modules()
    compiler.parse_all_modules()
    compiler.build_dependency_graph()
    compiler.collect_type_exports()
    return compiler, name


def test_bug11_project_type_check_reports_scope_errors(tmp_path):
    """项目模式不许丢掉 ScopeAnalyzer 已报出的诊断（同一源文件在单文件模式会报错）。"""
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer

    source = "def f() -> int:\n    return 1\n\n\ndef f() -> int:\n    return 2\n"

    scope = ScopeAnalyzer()
    scope.analyze(Parser(Lexer(source).tokenize()).parse())
    assert any("already declared" in e for e in scope.errors), \
        f"前提不成立：作用域分析器本身没报出重名，本用例就没在测目标缺陷: {scope.errors!r}"

    compiler, name = _project_compiler(tmp_path, "dup_func", source)
    assert list(compiler._ast_cache) == [name], \
        f"模块未进入解析缓存，测的不是 type_check_module: {list(compiler._ast_cache)}"

    ok, errors = compiler.type_check_module(name)
    assert ok is False, f"重名定义在项目模式被判为通过: ok={ok} errors={errors!r}"
    assert any("already declared" in e for e in errors), \
        f"type_check_module 丢弃了 ScopeAnalyzer 的诊断: {errors!r}"


def test_bug11_type_level_name_collision_is_reported(tmp_path):
    """SYNTAX/33 C-3.1 的类型级重名（subtype 撞 class 名）同样不许在项目模式静默。"""
    compiler, name = _project_compiler(
        tmp_path, "dup_subtype_class",
        "subtype Money <: int\n\n\nclass Money:\n    x: int\n")

    ok, errors = compiler.type_check_module(name)
    assert ok is False, f"类型级重名被判为通过: ok={ok} errors={errors!r}"
    assert any("redefinition of 'Money'" in e for e in errors), \
        f"类型级重名诊断没有上达到调用面: {errors!r}"


# --------------------------------------------------------------------------- BUG-12
def test_bug12_gilstate_exit_does_not_replace_user_exception():
    """with GilState() 体内提前 acquire 后，用户异常不许被 __exit__ 的 NoGilError 顶掉。"""
    from cypy_bridge.nogil import GilState, NoGilError

    escaped = None
    try:
        with GilState() as state:
            state.acquire()
            raise ValueError("user error")
    except Exception as exc:  # noqa: BLE001 - 断言的就是逃逸出来的类型
        escaped = exc

    assert not isinstance(escaped, NoGilError), \
        f"GIL 退出路径把用户的 ValueError 换成了 NoGilError: {escaped!r}"
    assert isinstance(escaped, ValueError), \
        f"用户异常没有原样上抛: {escaped!r}"


def test_bug12_gilstate_exit_still_restores_state():
    """修 __exit__ 不许把「退出时重新获取 GIL」这条本职行为一起削掉。"""
    from cypy_bridge.nogil import GilState

    with GilState() as state:
        assert state.released is True, "进入 nogil 区域后状态没被置为已释放，测不到退出恢复"
    assert state.released is False, f"退出 nogil 区域后 GIL 状态没有恢复: {state.released}"
