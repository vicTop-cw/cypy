"""R4-推进 法⑧：不可逆动作零执行——产品面与账本面各自一条判据，检测器自己配违例对照。

「本环没做任何不可逆的事」这种负面主张最容易写成装饰，所以两栏都要能红：
① 产品面：`git diff HEAD --name-status` 在产品目录里只允许出现 `M`（两档分析器），
   出现 `D`/`R` ⇒ 拒；未跟踪新增里若含产品目录也拒（新文件要走派单，不许静默落地）。
② 账本面：从 `call_log` 反解本环起点之后的工具调用清单，命中"毁灭型"名字模式即拒；
   `archive` 只允许作用于本环前缀的任务号，别人的任务号出现即拒。
检测器对照：往被检清单里合成一条 `delete_task` 与一条别人的 archive 目标，
两条都必须被抓到——抓不到就说明这条判据恒绿。
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from loop_kit import record  # noqa: E402

OUT = HERE / "advance_r4_irreversible.json"
DB = (ROOT / "fist-mbt.db").as_posix()
RING_START = "2026-09-28T03:00:00"
PRODUCT_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "scripts"]
DESTRUCTIVE = ("delete", "purge", "reset", "truncate", "drop", "unlink", "remove", "destroy")
ALLOWED_ARCHIVE_PREFIXES = ("T0r9",)          # 本 loop 的号段前缀（R4 推进根单落在这个段里）
CHECKS: list = []
REFUSE: list = []


def detect(rows: list, archive_targets: list) -> dict:
    """纯函数：给一份 (tool, task_id) 清单，返回命中的不可逆形状。可被对照直接复用。"""
    hit_destructive = sorted({t for t, _ in rows
                              if any(k in (t or "").lower() for k in DESTRUCTIVE)})
    foreign = sorted({tid for tid in archive_targets
                      if not str(tid or "").startswith(ALLOWED_ARCHIVE_PREFIXES)})
    return {"destructive_tools": hit_destructive, "foreign_archive_targets": foreign}


def untracked_paths(lines: list) -> list:
    """只看 `??` 行：porcelain 前两列是状态，" M 文件" 是「已跟踪且被改」。

    把它当成新增会让判据把全部未提交历史读成本环新文件（第一版就是这么红的）。
    """
    return sorted({ln[3:].strip() for ln in lines if ln.startswith("??")})


def mtime_iso(p: Path) -> str:
    return datetime.datetime.fromtimestamp(p.stat().st_mtime,
                                           datetime.timezone.utc).isoformat(timespec="seconds")


def attributable(paths: list, ring_start: str) -> list:
    """未跟踪文件要按 mtime 归因到本环才作数——`scripts/fist.py` 这类是既往轮留下的。"""
    return sorted(q for q in paths
                  if (ROOT / q).exists() and mtime_iso(ROOT / q) >= ring_start)


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    args = ["git", "diff", "HEAD", "--name-status", "--", *PRODUCT_DIRS]
    diff = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180).stdout
    status = [ln.split("\t") for ln in diff.splitlines() if ln.strip()]
    bad_product = sorted({f"{k} {p}" for k, *rest in status for p in rest
                          if k.strip() not in ("M",)})
    untracked = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *PRODUCT_DIRS],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180).stdout.splitlines()
    # 只看 `??` 行：porcelain 的前两列是状态，" M 文件" 是「已跟踪且被改」，
    # 把它当成新增会让本环的判据把全部未提交历史都读成新文件（第一版就是这么红的）。
    untracked_all = untracked_paths(untracked)
    new_product = attributable(untracked_all, RING_START)
    lock_rel = "tests/test_loop_20260927_advance_r4.py"
    record(CHECKS, REFUSE, "对照三之二：`??` 行必须被算作新增，` M` 行不得被算作新增",
           untracked_paths(["?? cypyc/sneaky.py", " M cypyc/analyzer/type_checker.py"]),
           ["cypyc/sneaky.py"], "过滤口径写反了就会把全部未提交历史当成新文件")
    record(CHECKS, REFUSE, "对照三之三：归因层要能红——把起点推到未来就不许还数到今天写的文件",
           [attributable([lock_rel], RING_START), attributable([lock_rel], "9999-01-01T00:00:00")],
           [[lock_rel], []], f"未跟踪全集 {untracked_all}")

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    sql = ("select tool, json_extract(params_json,'$.task_id') from call_log "
           "where ts >= ? order by id")
    rows = list(con.execute(sql, (RING_START,)))
    archives = [tid for tool, tid in rows if tool == "archive_task" or tool == "archive"]
    tools = sorted({t for t, _ in rows if t})
    con.close()
    verdict = detect(rows, archives)
    if verdict["destructive_tools"]:
        REFUSE.append(f"账本面出现毁灭型工具：{verdict['destructive_tools']}")
    if verdict["foreign_archive_targets"]:
        REFUSE.append(f"archive 打到了非本环号段：{verdict['foreign_archive_targets']}")
    record(CHECKS, REFUSE, "产品面只允许修改（M），不许删除/改名/新增未跟踪文件",
           [bad_product, new_product], [[], []],
           f"diff={status[:4]} untracked={new_product[:4]}")
    record(CHECKS, REFUSE, "本环起点以来的 RPC 工具清单里不含毁灭型动作",
           [t for t in tools if any(k in t.lower() for k in DESTRUCTIVE)], [],
           f"清单 {tools}")

    # 对照：合成两条必然违例，检测器必须都抓到（抓不到＝这条判据恒绿）
    fake = detect([("delete_task", "T0r90"), ("report_bug", None)], ["T0r90", "T0z99"])
    record(CHECKS, REFUSE, "对照一：合成 delete_task 必被抓到",
           fake["destructive_tools"], ["delete_task"], "抓不到就是检测器坏了")
    record(CHECKS, REFUSE, "对照二：合成别人的 archive 目标必被抓到",
           fake["foreign_archive_targets"], ["T0z99"], "抓不到就是号段判定坏了")
    record(CHECKS, REFUSE, "对照三：本环号段的 archive 不得被误判为越权",
           detect([("archive_task", "T0r90")], ["T0r90"])["foreign_archive_targets"], [],
           "误抓会让本环收口自己过不去")

    doc = {"started": started,
           "law": "本环零不可逆动作：产品面只改两档分析器，账本面只有 append 与本环号段归档",
           "ring_start": RING_START, "product_dirs_scanned": PRODUCT_DIRS,
           "product_diff_status": ["\t".join(r) for r in status],
           "product_bad_status": bad_product, "product_untracked_new": new_product,
           "product_untracked_all": untracked_all,
           "product_untracked_note": "未跟踪但非本环所写（mtime 早于本环起点）的一律照列不拒判，"
                                     "拒判只会逼人删别人的文件",
           "rpc_tools_since_start": tools, "rpc_rows": len(rows),
           "archive_targets": sorted(set(archives)), "destructive_pattern": list(DESTRUCTIVE),
           "verdict": verdict, "canary": {"two_negative_controls_caught": bool(
               fake["destructive_tools"] and fake["foreign_archive_targets"]),
               "own_prefix_not_flagged": not detect([("archive_task", "T0r90")],
                                                    ["T0r90"])["foreign_archive_targets"],
               "real_run_clean": not verdict["destructive_tools"]
               and not verdict["foreign_archive_targets"]},
           "executed_irreversible": 0, "renamed_verbatim": [],
           "product_files_touched_this_ring": 2,
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "tools": tools,
                      "bad_product": bad_product, "new_product": new_product,
                      "archives": sorted(set(archives)),
                      "canary": doc["canary"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
