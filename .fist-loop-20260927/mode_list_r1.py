"""查 mode_list 的权威约束（打磨/推进环节要用 publish 与否、必需 spec 键），落盘留证。"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

c = lfist_lib.Client(timeout=180)
c._send(
    "initialize",
    {
        "protocolVersion": lfist_lib.PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": lfist_lib.CLIENT_INFO,
    },
)
res = c.call("mode_list", {})
c.close()
(HERE / "mode_list_r1.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
)
modes = res.get("modes") or res
for m in (modes if isinstance(modes, list) else []):
    if isinstance(m, dict) and m.get("mode") in ("polish", "advance", "verify", "tidy"):
        print(json.dumps(m, ensure_ascii=False))
