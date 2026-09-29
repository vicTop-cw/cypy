"""R1-打磨：进程负载探针（给"墙钟判据被同机别的项目打断"这类归因留证据）。

两条实测教训决定了它的形状：
 1. 本机我自己的解释器常以 **python3.13.exe**（Windows Store 别名）出现，`tasklist` 按
    `IMAGENAME eq python.exe` 过滤会把自己的整棵子树漏掉 ⇒ 恒报"无负载"；
 2. 光看命令行里的项目根也不够：`pytest tests/ -q` 是相对路径跑的，命令行里根本没有
    `Cypy` 字样 ⇒ 会被误算成"外来进程"。
所以：命令行含 Cypy 根的进程作为 lane 种子，再沿 ParentProcessId 把种子/自己的子孙一起收进
本 lane；剩下的才是"外来"。原始命令行样本一并落盘，便于人工复核分类对不对。
"""

from __future__ import annotations

import csv
import io
import os
import subprocess

ROOT_MARK = "cypy"


def python_procs() -> list:
    """返回 [{'pid','name','cmd','ppid'}]；取不到时返回 []（调用方须把空当"测不到"而非"无负载"）。"""
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
            "Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
            "ConvertTo-Csv -NoTypeInformation",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    txt = (r.stdout or "").strip()
    if not txt:
        return []
    out = []
    for row in csv.DictReader(io.StringIO(txt.replace("\0", ""))):
        pid = (row.get("ProcessId") or "").strip()
        if not pid.isdigit():
            continue
        ppid = (row.get("ParentProcessId") or "").strip()
        out.append(
            {
                "pid": int(pid),
                "ppid": int(ppid) if ppid.isdigit() else 0,
                "name": (row.get("Name") or "").strip(),
                "cmd": (row.get("CommandLine") or "").strip(),
            }
        )
    return out


def snapshot(own_pid: int | None = None) -> dict:
    own_pid = own_pid or os.getpid()
    procs = python_procs()
    if not procs:
        return {
            "measured": False,
            "reason": "Get-CimInstance 没返回任何行：可能是 PowerShell 不可用，也可能是真没有 python 在跑——"
            "这两种情况分不开，故本次快照不能用来做归因",
            "total_python": 0,
            "cypy_lane": 0,
            "foreign_lane": 0,
            "foreign_sample": [],
        }
    # 种子只取「命令行含 Cypy 根」+ 探针自己；祖先链不作种子（两条实测教训：
    # 用祖先链会把同一 IDE/资源管理器祖先下的**别的项目**进程一起吸进来，虚报成 0 负载）。
    seeds = {p["pid"] for p in procs if ROOT_MARK in p["cmd"].lower()} | {own_pid}
    kids = {}
    for p in procs_all_children():
        kids.setdefault(p["ppid"], []).append(p["pid"])
    mine, stack = set(), list(seeds)
    while stack:
        cur = stack.pop()
        if cur in mine:
            continue
        mine.add(cur)
        stack.extend(kids.get(cur, []))
    foreign = [p for p in procs if p["pid"] not in mine and p["cmd"]]
    unattr = [p for p in procs if p["pid"] not in mine and not p["cmd"]]
    return {
        "measured": True,
        "unattributable": len(unattr),
        "unattributable_pids": [p["pid"] for p in unattr],
        "total_python": len(procs),
        "cypy_lane": len([p for p in procs if p["pid"] in mine]),
        "foreign_lane": len(foreign),
        "foreign_names": sorted({p["name"] for p in foreign}),
        "foreign_sample": [p["cmd"][:160] for p in foreign[:5]],
        "mine_sample": [p["cmd"][:160] for p in procs if p["pid"] in mine][:5],
    }


def procs_all_children() -> list:
    """全部进程（不只 python）——为了沿父链收子孙。同一快照内缓存，避免重复调 PowerShell。"""
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId | "
            "ConvertTo-Csv -NoTypeInformation",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = []
    for row in csv.DictReader(io.StringIO((r.stdout or "").replace("\0", ""))):
        pid = (row.get("ProcessId") or "").strip()
        ppid = (row.get("ParentProcessId") or "").strip()
        if pid.isdigit() and ppid.isdigit():
            out.append({"pid": int(pid), "ppid": int(ppid)})
    return out


if __name__ == "__main__":
    import json
    import sys

    only = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(json.dumps(snapshot(only), ensure_ascii=False, indent=1))
