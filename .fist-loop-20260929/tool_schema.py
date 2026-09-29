"""抓 129 工具的完整 inputSchema 到本地，参数名一律从回执反解（不按记忆写键名）。

用法：
  python .fist-loop-20260929/tool_schema.py dump            # 落 tools_schema.json
  python .fist-loop-20260929/tool_schema.py show publish ... # 打印指定工具的必填/参数名
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SERVER_JS = os.environ.get(
    "FIST_SERVER_JS", r"E:\IDEProjects\AI\FIST-Mbt\_build\js\debug\build\cmd\cli\cli.js")
CACHE = HERE / "tools_schema.json"
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "cypy-schema", "version": "1.0.0"},
}


def fetch_tools():
    proc = subprocess.Popen(
        ["node", SERVER_JS, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, cwd=str(ROOT), encoding="utf-8", errors="replace")
    frame = {"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {"_meta": META}}
    proc.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    tools = None
    for _ in range(200):
        line = proc.stdout.readline()
        if not line:
            break
        try:
            reply = json.loads(line)
        except json.JSONDecodeError:
            continue
        if reply.get("id") == 9:
            tools = (reply.get("result") or {}).get("tools")
            if tools is None:
                print("ERROR frame:", json.dumps(reply.get("error"), ensure_ascii=False))
            break
    proc.kill()
    return tools


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if mode == "dump":
        tools = fetch_tools()
        if not tools:
            print("dump FAILED：拿不到工具清单（不要写空缓存）")
            return 1
        CACHE.write_text(json.dumps(tools, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"dumped {len(tools)} tools -> {CACHE.name}")
        return 0
    tools = json.loads(CACHE.read_text(encoding="utf-8"))
    want = set(sys.argv[2:])
    for tool in tools:
        if tool["name"] not in want:
            continue
        schema = tool.get("inputSchema") or {}
        props = schema.get("properties") or {}
        print(f"== {tool['name']}")
        print("   required:", schema.get("required"))
        print("   params  :", sorted(props))
        for name, spec in props.items():
            enum = spec.get("enum")
            dflt = spec.get("default")
            extra = f" enum={enum}" if enum else ""
            extra += f" default={dflt!r}" if dflt is not None else ""
            print(f"     - {name}: {spec.get('type')}{extra}  {(spec.get('description') or '')[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
