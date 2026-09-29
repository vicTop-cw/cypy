"""R2-推进 的回归锁：`cypyc watch` 的三件"手册写了、代码没做"。

三件主张各自的**成对对照**（只有正例的判据等于没有判据）：

| 主张 | 正例 | 反例（必须不误抓/必须被抓） |
|------|------|------------------------------|
| `-o` 目录真的收到编译产物 | 设 `artifact_dir` ⇒ .pyx/.pyd 落在里面 | 不设 ⇒ 目录里什么都不出现（默认行为未变） |
| 编译批次串行（锁在**类**上） | 假 hook 在 `compile_to_pyd` 里从别的线程抢锁 ⇒ 抢不到 | 同线程第二次 acquire 必须成功（可重入，不是死锁） |
| `--debounce` 生效 | `start(debounce_delay=1.23)` ⇒ 监控器拿到 1.23 | 不传 ⇒ 沿用默认 0.5（不改变库路径的旧行为） |

外加一条端到端子进程锁：`python -m cypyc watch` 改文件 ⇒ 输出目录出现产物、stdout 出现
`[Watch] Published` 行（这行只有 CLI 真把回调接上才会打出来）。

最后一类锁打的是**构造路径**：老测试用 `__new__` 绕过 `__init__` 造引擎，我加的字段只在
`__init__` 里赋值就会把那条老用例撞红（本轮真的红过一次，见 §五 的自曝）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cypyc.incremental import HotReloadEngine  # noqa: E402
from cypyc.incremental.hot_reload import HotReloadResult  # noqa: E402


class _FakeCompileResult:
    def __init__(self, pyd_path, errors=None):
        self.success = not errors
        self.pyd_path = pyd_path
        self.errors = errors or []


def _fake_hook(temp_out: Path, files: dict, record: dict):
    """只做"往 output_dir 写产物"的假 hook，避免测试依赖 C 编译器。"""

    class Fake:
        def compile_to_pyd(self, source_path, output_dir=None, force_recompile=False):
            dest = Path(output_dir)
            for name, body in files.items():
                (dest / name).write_text(body, encoding="utf-8")
            record["calls"] = record.get("calls", 0) + 1
            record["lock_free_here"] = _lock_free_elsewhere(record["engine"])
            pyd = dest / next(n for n in files if n.endswith(".pyd"))
            return _FakeCompileResult(str(pyd))

    return Fake()


def _lock_free_elsewhere(engine) -> bool:
    """另起线程试着抢锁：抢到 ⇒ 编译时**没有**持锁。"""
    got: list = []

    def try_acquire():
        if engine._compile_lock.acquire(blocking=False):
            try:
                got.append(True)
            finally:
                engine._compile_lock.release()

    t = threading.Thread(target=try_acquire)
    t.start()
    t.join(timeout=2)
    return bool(got)


# ---------------------------------------------------- 主张 1：产物发布到 -o 指定目录
def test_publish_artifacts_copies_pyx_and_pyd_only(tmp_path):
    temp_out = tmp_path / "temp_build"
    temp_out.mkdir()
    art_dir = tmp_path / "artifacts"
    (temp_out / "mod.pyx").write_text("# generated\n", encoding="utf-8")
    (temp_out / "mod.cp99-win_amd64.pyd").write_text("binary-ish", encoding="utf-8")
    (temp_out / "mod.c").write_text("intermediate\n", encoding="utf-8")

    engine = HotReloadEngine.__new__(HotReloadEngine)
    engine._artifact_dir = str(art_dir)
    published = engine._publish_artifacts(str(temp_out), str(temp_out / "mod.cp99-win_amd64.pyd"))

    names = sorted(Path(p).name for p in published)
    assert names == ["mod.cp99-win_amd64.pyd", "mod.pyx"], names
    assert len(published) == len(set(published)), f"同一目标被重复发布：{published}"
    assert not (art_dir / "mod.c").exists(), "中间产物 .c 不该算'编译文件'"


def test_publish_artifacts_is_noop_without_artifact_dir(tmp_path):
    """对照：不设目录时必须是**空操作**——库路径的旧行为不能被我这次改动带偏。"""
    temp_out = tmp_path / "temp_build"
    temp_out.mkdir()
    (temp_out / "mod.pyx").write_text("# generated\n", encoding="utf-8")
    elsewhere = tmp_path / "should_not_exist"

    engine = HotReloadEngine.__new__(HotReloadEngine)
    engine._artifact_dir = None
    published = engine._publish_artifacts(str(temp_out), str(temp_out / "mod.pyx"))

    assert published == []
    assert not elsewhere.exists()


# ---------------------------------------------------- 主张 2：编译批次串行 + 结果里带着产物
def test_compile_is_serialized_and_reports_published_artifacts(tmp_path):
    temp_out = tmp_path / "compile_temp"
    temp_out.mkdir()
    art_dir = tmp_path / "out_dir"
    engine = HotReloadEngine.__new__(HotReloadEngine)
    engine._artifact_dir = str(art_dir)
    engine._compile_lock = threading.RLock()
    engine._save_module_state = lambda name: None
    engine._restore_module_state = lambda name: None
    engine._get_module_name_from_path = lambda p: "fakemod"
    engine._cache_manager = None
    engine._incremental_compiler = None
    engine._module_source_map = {}
    engine._proxy_modules = {}
    record: dict = {"engine": engine}
    engine._hook = _fake_hook(temp_out, {"fakemod.pyx": "# x\n", "fakemod.cp99.pyd": "z"}, record)

    result = engine._compile_and_reload_module(str(tmp_path / "fakemod.cypy"))

    assert record["lock_free_here"] is False, "编译期间锁没被持有 ⇒ 串行形同虚设"
    assert engine._compile_lock.acquire(blocking=False), "同线程应可重入，不能把引擎锁死"
    engine._compile_lock.release()
    # 假 .pyd 不是真 DLL ⇒ 重载必然失败；失败也要如实带上"已经复制出去的产物"
    assert result.success is False
    errs = " ".join(result.errors)
    assert "DLL load failed" in errs or "Failed to reload" in errs, result.errors
    published = sorted(Path(p).name for p in result.published_artifacts)
    assert published == ["fakemod.cp99.pyd", "fakemod.pyx"], result.published_artifacts
    assert (art_dir / "fakemod.pyx").exists()


def test_real_toolchain_publishes_compiled_artifacts(tmp_path):
    """真编译器路径：成功批次的 `published_artifacts` 与产物目录必须双向对得上。

    这一条是 `cypyc watch -o <dir>` 的产品主张本身（前面的假 hook 只测到了复制逻辑）。
    """
    from cypy_hook.hook import CypyHook

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    out_dir = tmp_path / "out"
    source = src_dir / "advaudit_mod.cypy"
    source.write_text("def get_value() -> int:\n    return 42\n", encoding="utf-8")

    hook = CypyHook()
    hook.set_output_dir(str(out_dir))
    engine = HotReloadEngine(hook, artifact_dir=str(out_dir))
    result = engine._compile_and_reload_module(str(source))

    assert result.success, result.errors
    names = sorted(Path(p).name for p in result.published_artifacts)
    assert any(n.startswith("advaudit_mod") and n.endswith(".pyx") for n in names), names
    assert any(n.endswith(".pyd") for n in names), names
    assert all(Path(p).is_file() for p in result.published_artifacts), result.published_artifacts
    assert set(result.published_artifacts) == set(n for n in map(str, [out_dir / x for x in names]))

    # 对照：不设产物目录 ⇒ 同样的编译不往 out 目录放任何东西（默认行为未被改动）
    src_dir2 = tmp_path / "src2"
    src_dir2.mkdir()
    out_dir2 = tmp_path / "out2"
    out_dir2.mkdir()
    source2 = src_dir2 / "advaudit_ctl.cypy"
    source2.write_text("def get_value() -> int:\n    return 42\n", encoding="utf-8")
    hook2 = CypyHook()
    hook2.set_output_dir(str(out_dir2))
    engine2 = HotReloadEngine(hook2)
    result2 = engine2._compile_and_reload_module(str(source2))
    assert result2.success, result2.errors
    assert result2.published_artifacts == []
    assert [p.name for p in out_dir2.iterdir()] == []


def test_publish_survives_copy_failure(tmp_path, capsys):
    """产物被锁住（Windows 上 .pyd 已加载）时：失败必须**可见**，但不能把整次热重载判死。"""
    temp_out = tmp_path / "temp_build"
    temp_out.mkdir()
    (temp_out / "mod.pyx").write_text("x", encoding="utf-8")
    art_dir = tmp_path / "art"
    art_dir.mkdir()
    blocker = art_dir / "mod.pyx"
    blocker.write_text("old", encoding="utf-8")

    engine = HotReloadEngine.__new__(HotReloadEngine)
    engine._artifact_dir = str(art_dir)

    import shutil as _shutil

    real_copy2 = _shutil.copy2

    def boom(src, dst, *a, **k):
        raise OSError(13, "模拟 Windows 文件锁")

    _shutil.copy2 = boom
    try:
        published = engine._publish_artifacts(str(temp_out), str(temp_out / "mod.pyx"))
    finally:
        _shutil.copy2 = real_copy2

    assert published == []
    out = capsys.readouterr().out
    assert "产物发布失败" in out, out


# ---------------------------------------------------- 主张 3：--debounce 真的接进监控器
def test_debounce_delay_is_passed_through_and_defaults_keep_old_behaviour(tmp_path):
    watched = tmp_path / "src"
    watched.mkdir()
    engine = HotReloadEngine(None)

    engine.start([str(watched)], debounce_delay=1.23)
    try:
        assert engine._monitor._debounce_delay == pytest.approx(1.23)
    finally:
        engine.stop()

    engine2 = HotReloadEngine(None)
    engine2.start([str(watched)])
    try:
        assert engine2._monitor._debounce_delay == pytest.approx(0.5), "不传时不能改变库路径默认"
    finally:
        engine2.stop()


def test_cli_watch_wires_callback_and_output(tmp_path, monkeypatch):
    """CLI 面：run_watch 必须把 -o 当产物目录、把 --debounce 传下去、并挂上 on_reload 回调。"""
    import cypyc.cli as cli

    captured: dict = {}

    class SpyEngine:
        def __init__(self, hook, incremental_compiler=None, artifact_dir=None):
            captured["artifact_dir"] = artifact_dir

        def start(self, watch_dirs, on_reload=None, debounce_delay=None):
            captured["watch_dirs"] = list(watch_dirs)
            captured["on_reload_set"] = callable(on_reload)
            captured["debounce_delay"] = debounce_delay
            # 直接调一次回调：如果 run_watch 的回调里引用了不存在的名字，这里就会炸
            on_reload(HotReloadResult(
                success=True, recompiled_modules=["m"], updated_modules=["m"],
                published_artifacts=[str(Path("out") / "m.pyx")],
            ))

        def stop(self):
            captured["stopped"] = True

    class SpyHook:
        def set_output_dir(self, d):
            captured["hook_output"] = d

        def set_verbose(self, v):
            captured["hook_verbose"] = v

    monkeypatch.setattr("cypy_hook.hook.CypyHook", SpyHook)
    monkeypatch.setattr("cypyc.incremental.HotReloadEngine", SpyEngine)
    # run_watch 末尾是 `while True: sleep(1)`，用 KeyboardInterrupt 把它从循环里请出来
    sleeps: list = []

    def fake_sleep(_s):
        sleeps.append(_s)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)

    out_dir = tmp_path / "out"
    args = SimpleNamespace(source=str(tmp_path), output=str(out_dir),
                           debounce=0.7, verbose=False)
    rc = cli.run_watch(args)

    assert rc == 0, "Ctrl+C 正常退出应回 0"
    assert captured["artifact_dir"] == str(out_dir)
    assert captured["on_reload_set"] is True
    assert captured["debounce_delay"] == 0.7
    assert captured["watch_dirs"] == [str(tmp_path)]
    assert captured["stopped"] is True


def test_hot_reload_result_field_is_backward_compatible():
    """新字段必须带默认值：库里已有 5 处按位置构造 HotReloadResult，不能被我加爆。"""
    r = HotReloadResult(success=True, recompiled_modules=["a"], updated_modules=["a"])
    assert r.published_artifacts == []
    positional = HotReloadResult(True, ["a"], ["a"], {"x"}, ["e"], False)
    assert positional.published_artifacts == []
    assert positional.errors == ["e"]


def test_engine_attributes_survive_construction_without_init():
    """新增的 `_compile_lock` / `_artifact_dir` 必须是**类**属性。

    既有测试（`tests/test_polish_20260926.py::test_bug10_cache_update_parse_failure_warns`）
    用 `HotReloadEngine.__new__` 绕过 `__init__` 造引擎；把这两个属性只写在 `__init__`
    里会让那条老用例以 `AttributeError` 变红——我在推进环里真的踩过一次。
    """
    from cypyc.incremental.hot_reload import HotReloadEngine

    compiled: list = []

    class _Hook:
        def compile_to_pyd(self, source_path, output_dir=None, force_recompile=False):
            compiled.append((source_path, output_dir, force_recompile))
            return SimpleNamespace(success=False, pyd_path=None, errors=["hook says no"])

    engine = HotReloadEngine.__new__(HotReloadEngine)
    engine._hook = _Hook()
    engine._cache_manager = None
    engine._incremental_compiler = None
    engine._module_state = {}
    engine._proxy_modules = {}
    engine._module_source_map = {}
    engine._module_dependencies = {}

    result = engine._compile_and_reload_module("mod_b.cypy")

    assert compiled == [("mod_b.cypy", compiled[0][1], True)], "绕过 __init__ 就没走到编译"
    assert result.success is False
    assert result.published_artifacts == [], "没给 artifact_dir 时不该凭空报发布"
