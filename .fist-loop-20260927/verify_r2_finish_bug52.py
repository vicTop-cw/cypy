#!/usr/bin/env python3
"""BUG-52 的补验件：不重发 report_bug（发一次就是一张新单，不幂等），只做回读与证据落件。

成因记录：`verify_r2_file_bug52.py` 首跑已成功落账（服务端把 `- reported_by` 与
`- task_id: T0r58` 都写进了 `memory/bugs.md`），但脚本在"取下一条条目标题"时对
**文件最后一条**用了 `txt.index(...)`，抛 ValueError ⇒ 证据件没写成。这条把
收尾单独跑，并把那个坑修回原脚本。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
OUT = HERE / "verify_r2_file_bug52.json"
NL = chr(10)
SUMMARY_HEAD = "[构建/规范配置] pyproject 声明了 [tool.black]"


def main() -> int:
    refuse: list = []
    txt = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^## (BUG-\d+) \[[^\]]+\] \[([^\]]+)\] (\w+)", txt)

    def span(n: str) -> tuple:
        head = f"## {n} ["
        i = txt.index(head)
        found = txt.find(NL + "## BUG-", i + len(head))
        return i, (len(txt) if found < 0 else found)

    NL = chr(10)
    matches = [n for n, _sev, _st in ids if SUMMARY_HEAD in txt[span(n)[0] : span(n)[0] + 400]]
    if not matches:
        refuse.append("账本里找不到这条缺陷的条目")
    unmarked = [n for n in matches[1:] if "### DUPLICATE" not in txt[span(n)[0] : span(n)[1]]]
    if unmarked:
        refuse.append(f"summary 命中 {len(matches)} 次且 {unmarked} 未标 DUPLICATE ⇒ 双发未处置")
    dup_marks = len(matches) - 1 - len(unmarked)
    bug_id = matches[0] if matches else None
    entry, task_id, sev = "", "", "?"
    if bug_id:
        i, end = span(bug_id)
        entry = txt[i:end]
        sev = re.search(rf"^## {bug_id} \[[^\]]+\] \[([^\]]+)\]", entry).group(1)
        m = re.search(r"^- task_id: (\S+)", entry, flags=re.M)
        task_id = m.group(1) if m else ""
        if not task_id:
            refuse.append(f"{bug_id} 条目缺 task_id 栏")

    if entry and "publish_task" not in entry:
        pass  # 卡与任务的对应关系由 task_id 栏承担，这里不做文案断言

    con = __import__("sqlite3").connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    row = con.execute("select id, ns, status from tasks where id=?", (task_id,)).fetchone() if task_id else None
    con.close()
    if not row or row[1] != "bugs":
        refuse.append(f"task_id {task_id} 在服务端 ns=bugs 里查不到")
    elif row[2] not in ("待领取", "已领取", "执行中"):
        refuse.append(f"派生任务状态异常：{row[2]}")

    bl_client = lfist_lib.Client(timeout=240)
    bl_client._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    bl_client._recv(1, 60)
    bl = bl_client.call("bug_list", {"project_dir": ".", "limit": 80, "now": lfist_lib.utc_now()})
    rows = bl.get("bugs") or bl.get("items") or bl or []
    hits = [b for b in rows if isinstance(b, dict) and SUMMARY_HEAD in json.dumps(b, ensure_ascii=False)]
    if not hits:
        refuse.append("bug_list 回读不到这条（隐形标题/未入列表）")

    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "black",
            "--line-length",
            "100",
            "--check",
            "cypyc",
            "cypy_bridge",
            "scripts",
            "tests",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    m = re.search(r"(\d+) files? would be reformatted, (\d+) files? would be left unchanged", proc.stdout + proc.stderr)
    counted = subprocess.run(
        ["bash", "-c", "find cypyc cypy_bridge scripts tests -name '*.py' | wc -l"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    measure = {
        "rc": proc.returncode,
        "reformat": int(m.group(1)) if m else -1,
        "unchanged": int(m.group(2)) if m else -1,
        "py_files": int(counted.stdout.strip() or -1),
    }
    if measure["reformat"] < 1:
        refuse.append(f"black 口径复跑没数出违例文件：{measure}")

    noise = json.loads((HERE / "verify_r2_probe.json").read_text(encoding="utf-8"))["probes"][
        "P9.black_noise_split"
    ]
    doc = {
        "refuse": refuse,
        "measure": measure,
        "filed": {"bug_id": bug_id, "task_id": task_id, "severity": sev, "reused": True},
        "matches": matches,
        "dup_marked": dup_marks,
        "task_row": list(row) if row else None,
        "bug_list_hits": len(hits),
        "black_noise_split": noise,
        "detail_head_on_disk": entry[:160],
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    print(json.dumps({"refuse": refuse, "filed": doc["filed"], "measure": measure}, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
