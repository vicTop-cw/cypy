#!/usr/bin/env python3
"""让 §七 的脚本/证据清单从任务库目录实时导出，不再手写（手写那份已经漏掉十来个脚本）。

锚点用「行首唯一前缀」定位，不整段抄正文；两处都要求恰好命中 1 次，否则不写。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

DATA_ANCHOR = 'tul = load("tool_usage_ledger.json")'
DATA_NEW = '''_here = sorted(os.listdir(HERE))
SCRIPTS = [f[:-3] for f in _here if f.endswith(".py")]
SCRIPTS_INV = ",".join(SCRIPTS)
EVID = [f for f in _here if f.endswith((".json", ".log", ".out", ".txt"))]
EVID_N = len(EVID)
''' + DATA_ANCHOR

SCRIPT_PREFIX = "- 驱动脚本："
EVID_PREFIX = "- 终态证据："


def main() -> int:
    src = open(TARGET, encoding="utf-8", newline="").read()
    if "\r\n" in src:
        sys.exit("[patch14] gen_report.py 出现 CRLF")
    if src.count(DATA_ANCHOR) != 1:
        sys.exit(f"[patch14] 数据块锚点命中 {src.count(DATA_ANCHOR)} 次")
    if "SCRIPTS_INV = " in src:
        print("[patch14] 数据块已打过，跳过")
    else:
        src = src.replace(DATA_ANCHOR, DATA_NEW, 1)
        print("[patch14] 数据块：已插入目录导出变量")

    lines = src.split("\n")
    if "{SCRIPTS_INV}" in src:
        print("[patch14] §七 脚本行已是派生形态，跳过（幂等）")
        compile(src, TARGET, "exec")
        return 0
    hits = [i for i, ln in enumerate(lines) if ln.startswith(SCRIPT_PREFIX)]
    if len(hits) != 1:
        sys.exit(f"[patch14] 「{SCRIPT_PREFIX}」行命中 {len(hits)} 次（须 1 次），**未写入**")
    i = hits[0]
    if "{SCRIPTS_INV}" in lines[i]:
        print("[patch14] §七 脚本行已是派生形态")
    else:
        lines[i] = ("- 驱动脚本（**从任务库目录实时导出，不做人工筛选**，故包含被判据推翻的探针与逐轮 "
                    "patcher）：`.fist-polish-20260926/{{{SCRIPTS_INV}}}.py`\n"
                    "- 证据文件全量：任务库目录下另有 {EVID_N} 个 `.json/.log/.out/.txt`，"
                    "下面几行只点名被正文引用的那些，未点名者以目录本身为准")
        print("[patch14] §七 脚本行：改为派生清单 + 证据全量披露")
    eh = [k for k, ln in enumerate(lines) if ln.startswith(EVID_PREFIX)]
    if len(eh) != 1:
        sys.exit(f"[patch14] 「{EVID_PREFIX}」行命中 {len(eh)} 次，无法确认正文结构未变")
    src = "\n".join(lines)
    compile(src, TARGET, "exec")
    open(TARGET, "w", encoding="utf-8", newline="").write(src)
    print(f"[patch14] 写回完成（任务库目录现有 .py "
          f"{len([f for f in os.listdir(HERE) if f.endswith('.py')])} 个）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
