"""`scripts/fist.py` 的协议面回归（上游 0.3.4 / MCP 2026-07-28 无状态握手）。

锁住四件在调用面才暴露、单测「函数返回值」测不到的事：
1. 服务进程必须以 **权威产物 `cmd/cli/cli.js` + `serve` 子命令** 起跑（裸跑只打 help，
   旧入口 `cmd/main/main.js` 已不是发布产物真身）；
2. 每个请求帧都带 `_meta.io.modelcontextprotocol/protocolVersion`，且**不再发 `initialize`**
   （2026-07-28 是无状态握手，`initialize` 现在回 -32601，发了也没人读＝假 handshake）；
3. `list-tools` 不是「有输出就算过」：错误帧 / 空清单 / 缺必需工具三种形态都必须非 0 退出
   （改前的实现这三种形态全部 rc=0，即一条恒绿探针）；
4. 绿色分支要求真清单含本轮依赖的 12 个工具名。

测试用假 Popen（不起 node、不碰任何库文件），所以这三条红/绿对照在任何机器上都会执行。
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "fist.py"


class FakeProc:
    """记录写出的 JSON-RPC 帧，并按预置行回放 stdout。"""

    def __init__(self, argv, out_lines):
        self.argv = list(argv)
        self._out = io.StringIO("".join(ln + "\n" for ln in out_lines))
        self.stdin_writes: list[str] = []
        self.terminations = 0

    @property
    def stdin(self):
        return self

    def write(self, text):
        self.stdin_writes.append(text)

    def flush(self):
        pass

    @property
    def stdout(self):
        return self._out

    @property
    def stderr(self):
        return io.StringIO("")

    def readline(self):
        line = self._out.readline()
        return line

    def poll(self):
        return None

    def terminate(self):
        self.terminations += 1
        raise OSError("terminate disabled in test")

    def kill(self):
        self.terminations += 1

    def wait(self, timeout=None):
        return 0

    def frames(self):
        return [json.loads(w.strip()) for w in self.stdin_writes if w.strip()]


def load_driver(monkeypatch, tmp_path, out_lines=None, green=None):
    """以「产物存在、patch 脚本不存在」的环境重新导入驱动，并替换 Popen。

    `green=True` 表示回放一条含全部必需工具的成功帧；`green=[名字...]` 表示回放缺项清单；
    需要精确帧形（错误帧/空清单）时直接传 `out_lines`。
    """
    artifact = tmp_path / "cli.js"
    artifact.write_text("// stub\n", encoding="utf-8")
    monkeypatch.setenv("FIST_SERVER_JS", str(artifact).replace("\\", "/"))
    monkeypatch.setenv("FIST_PATCH_SCRIPT", str(tmp_path / "__no_such_patch__.py"))
    monkeypatch.setenv("FIST_SERVER_CWD", str(tmp_path).replace("\\", "/"))
    monkeypatch.setenv("FIST_NAMESPACE", "cypy-test-ns")
    spec = importlib.util.spec_from_file_location("fist_driver_under_test", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if out_lines is None:
        names = module.REQUIRED_TOOLS if green is True else list(green or [])
        out_lines = [tools_frame(names)]
    proc = FakeProc(["node", str(artifact), "serve"], out_lines)
    calls: list = []

    def fake_popen(argv, **kwargs):
        calls.append(argv)
        return proc

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    return module, proc, calls


def tools_frame(tool_names, msg_id=1):
    return json.dumps({
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"tools": [{"name": n, "description": ""} for n in tool_names]},
    })


def test_server_argv_uses_authoritative_entry_with_serve(monkeypatch, tmp_path):
    module, _proc, calls = load_driver(monkeypatch, tmp_path, green=True)
    client = module.FistClient(timeout=5)
    client.close()
    argv = calls[0]
    assert argv[0] == "node"
    assert Path(argv[1]).name == "cli.js", "入口必须是 cmd/cli/cli.js（发布产物真身）"
    assert argv[-1] == "serve", "裸跑 cli.js 只打 help，stdio 服务必须显式 serve"


def test_every_request_carries_meta_and_initialize_is_not_sent(monkeypatch, tmp_path):
    module, proc, _calls = load_driver(monkeypatch, tmp_path, green=True)
    monkeypatch.setattr(module.sys, "argv", ["fist.py", "list-tools"])  # argv[0] 是脚本名
    assert module.main() == 0
    frames = proc.frames()
    methods = [f["method"] for f in frames]
    assert methods == ["tools/list"], f"不应再发已被服务端拒绝的 initialize：{methods}"
    for frame in frames:
        meta = frame["params"]["_meta"]
        assert meta["io.modelcontextprotocol/protocolVersion"] == module.PROTOCOL_VERSION


def test_list_tools_red_on_error_frame(monkeypatch, tmp_path, capsys):
    """旧形态在这条上是 rc=0 且零输出（恒绿探针）——现在必须红。"""
    module, _proc, _calls = load_driver(monkeypatch, tmp_path, [
        "[fist] serve — 启动 MCP server (stdio 传输)",
        json.dumps({"jsonrpc": "2.0", "id": 1,
                    "error": {"code": -32602, "message": "Missing required _meta field"}}),
    ])
    monkeypatch.setattr(module.sys, "argv", ["fist.py", "list-tools"])  # argv[0] 是脚本名
    assert module.main() == 1
    assert "handshake FAILED" in capsys.readouterr().err


def test_list_tools_red_on_empty_tool_list(monkeypatch, tmp_path, capsys):
    module, _proc, _calls = load_driver(monkeypatch, tmp_path, green=[])
    monkeypatch.setattr(module.sys, "argv", ["fist.py", "list-tools"])  # argv[0] 是脚本名
    assert module.main() == 1
    assert "handshake FAILED" in capsys.readouterr().err


def test_list_tools_red_when_required_tool_missing(monkeypatch, tmp_path, capsys):
    """缺一个必需工具（本轮要用 omega 强验证）必须红，而不是「128 个也算多」。"""
    module, _proc, _calls = load_driver(monkeypatch, tmp_path, green=[])
    subset = [n for n in module.REQUIRED_TOOLS if n != "omega_verify"]
    module2, _proc2, _c2 = load_driver(monkeypatch, tmp_path, green=subset)
    monkeypatch.setattr(module2.sys, "argv", ["fist.py", "list-tools"])
    assert module2.main() == 1
    err = capsys.readouterr().err
    assert "omega_verify" in err, "拒绝必须点名缺的是哪个工具"

def test_list_tools_green_on_full_surface(monkeypatch, tmp_path, capsys):
    module, _proc, _calls = load_driver(monkeypatch, tmp_path, green=True)
    monkeypatch.setattr(module.sys, "argv", ["fist.py", "list-tools"])  # argv[0] 是脚本名
    assert module.main() == 0
    out = capsys.readouterr().out
    for name in module.REQUIRED_TOOLS:
        assert name in out


def test_project_dir_is_relative_within_server_cwd(monkeypatch, tmp_path):
    """绝对 project_dir 会被服务端「禁越界」拒写；驱动默认必须是 cwd 内的相对路径。"""
    module, proc, _calls = load_driver(monkeypatch, tmp_path, [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "{}"}]}})
    ])
    client = module.FistClient(timeout=5)
    client.call("publish", {"title": "x"})
    client.close()
    frame = proc.frames()[-1]
    args = frame["params"]["arguments"]
    assert args["project_dir"] == "."
    assert not Path(args["project_dir"]).is_absolute()
    assert args["namespace"] == "cypy-test-ns"


def test_defaults_injection_can_be_opted_out(monkeypatch, tmp_path):
    """task_plan_deep/laya_decide/loop_create 不声明 namespace/project_dir，
    服务端按 BUG-23 口径拒收未知键 ⇒ 驱动必须能关掉注入，否则这些工具在调用面根本用不了。"""
    module, proc, _calls = load_driver(monkeypatch, tmp_path, [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "{}"}]}})
    ])
    client = module.FistClient(timeout=5)
    client.call("loop_create", {"name": "x", "_omit_defaults": True})
    client.close()
    args = proc.frames()[-1]["params"]["arguments"]
    assert "namespace" not in args and "project_dir" not in args, args
    assert "_omit_defaults" not in args, "退出键不得发给服务端"


def test_injection_still_applies_by_default(monkeypatch, tmp_path):
    """反向对照：不关注入时 namespace/project_dir 仍要出现，否则上一条只是把注入删了。"""
    module, proc, _calls = load_driver(monkeypatch, tmp_path, [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "{}"}]}})
    ])
    client = module.FistClient(timeout=5)
    client.call("claim", {"task_id": "T0r1"})
    client.close()
    args = proc.frames()[-1]["params"]["arguments"]
    assert args["namespace"] == "cypy-test-ns" and args["project_dir"] == "."


def test_error_reply_is_surfaced_not_swallowed(monkeypatch, tmp_path):
    module, _proc, _calls = load_driver(monkeypatch, tmp_path, [
        json.dumps({"jsonrpc": "2.0", "id": 1,
                    "error": {"code": -32603, "message": "boom"}})
    ])
    client = module.FistClient(timeout=5)
    out = client.call("claim", {"task_id": "T0r1"})
    client.close()
    assert "__error__" in out, "错误帧必须能被调用方看到，不能退化成空结果"


def test_this_file_actually_collects_its_cases():
    """收集数地板：Edit 吃掉换行/重名会让用例静默消失且全绿（本轮新增 8 条，低于 8 即判据坏了）。"""
    import inspect

    collected = [n for n, f in globals().items()
                 if n.startswith("test_") and inspect.isfunction(f)]
    assert len(collected) >= 8, f"本文件只收集到 {len(collected)} 条用例：{sorted(collected)}"

