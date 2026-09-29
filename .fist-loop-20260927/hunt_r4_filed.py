"""R4-寻虫 法 5：只把**确诊且未与 60 单重合**的根因入账。号从盘上现数，回读三处（RPC/账本/sqlite）。

入账前后各钉一道门：
- 前：dedup 件 refuse 必须为空、duplicates 必须为空、repro 对应 KEY 的退出码必须是 0（现形）；
  任何一条单在没跑过复现的情况下不许落账。
- 后：账本里必须搜到这条 summary、`## BUG-NN` 号必须等于「入账前 max+序号」、
  sqlite `ns=bugs` 行数必须同步增加；三处任一不齐 ⇒ 本脚本红，不写"已入账"。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

import lfist_lib
from hunt_r4_dedup import PLAN

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
DB = ROOT / "fist-mbt.db"
OUT = HERE / "hunt_r4_filed.json"
CONFIRM = json.loads((HERE / "hunt_r4_confirm.json").read_text(encoding="utf-8"))
FACES = json.loads((HERE / "hunt_r4_faces.json").read_text(encoding="utf-8"))
DECLARED = json.loads((HERE / "hunt_r4_declared.json").read_text(encoding="utf-8"))
DEDUP = json.loads((HERE / "hunt_r4_dedup.json").read_text(encoding="utf-8"))
REPRO = json.loads((HERE / "hunt_r4_repro.json").read_text(encoding="utf-8"))
CONF_BY_ID = {r["id"]: r for r in CONFIRM["rows"]}
DECL_BY_ID = {r["id"]: r for r in DECLARED["rows"]}
REPRO_CMD = "python -X utf8 .fist-loop-20260927/hunt_r4_repro.py {key}"

NOT_PROOF = {
    "RC1_func_symbol_typed_as_return":
        "只说『读代码像是这样』不算；必须同时给出「正确调用被判错」与「错误调用被放行」两向实测，"
        "并配一条元数违例确实在报的对照（否则是整条通道空转，另码另说）。",
    "RC2_no_argument_type_check":
        "必须与同族赋值形状（`let x: int = \"s\"` 会报）并排给出，否则分不清是「没有实参检查」"
        "还是「分析器整体不看类型」。",
    "RC3_struct_field_type_unresolved":
        "只测一层 `self.n` 不算，需再测嵌套链 `self.i.n` 与成员被当回调调用的形状；"
        "且必须配一条「同函数里局部变量会报」的对照。",
    "RC4_internal_repr_in_message":
        "文案类主张必须把整条 message 原文打出来；只说『不好看』不算——判据是产物里出现 `tuple[`"
        "而源语法从未这样写。",
    "DOC_status_stale_rows":
        "每一行都要当场重跑它自己宣称的那件事（今天已实现 / 仍未实现）；只抄文档行号不算，"
        "附录里《已实现的限制修复》14 行本轮未逐行复测 ⇒ 不入账。",
    "DOC_cli_face_mismatch":
        "旗标类主张必须拿 `--help` 与 argparse 实读集对照，并配一条「同一 CLI 别的命令可用」的对照，"
        "否则分不清是旗标不存在还是 CLI 整个挂了。",
    "DOC_example_fails":
        "示例类主张不要求真编译：属性是否存在看 dataclass 字段集，`__result__` 看写侧是否产出。"
        "只说『跑起来会炸』而没指出符号不存在，不算。",
    "BRIDGE_cache_side_effect":
        "必须证明目录是**这两个只读调用**建的（调用前后各数一遍），并且探针跑在独立 CWD 里；"
        "只看代码里有个 mkdir 不算。",
    "BRIDGE_c_not_equivalent":
        "必须按花括号净深判定「模块级」，不能只看某行以 `if (` 开头（函数体内的 if 剥掉缩进后长一样）；"
        "真编译验证本轮未跑 ⇒ 本单只主张生成物结构非法这一半。",
    "SPEC_file_size_redline":
        "行数主张必须写明口径（剔注释与字符串后的 token 覆盖行数）；`wc -l` 的数与这个口径不等价，"
        "两者都要落，取哪一个要注明。",
}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def symptom_lines(key: str, ids: list) -> tuple:
    """pos = 现象实测原文；ctl = 今天行为正确的那条对照（代码面取 confirm，文档面取 declared 里的 control）。"""
    pos, ctl = [], []
    for i in ids:
        if i in CONF_BY_ID:
            r = CONF_BY_ID[i]
            pos.append(f"{i} {r['case']} 期望={r['want']} 实测={json.dumps(r['observed_errors'], ensure_ascii=False)}")
            ctl.append(f"对照 {r['ctl']} 实测={json.dumps(r['ctl_observed_errors'], ensure_ascii=False)}")
        elif i in DECL_BY_ID:
            d = DECL_BY_ID[i]
            m = json.dumps(d["measured"], ensure_ascii=False)
            pos.append(f"{i} [{d['verdict']}] {d['doc']['file']}:{d['doc']['line']} "
                       f"原文「{d['doc']['quote'][:90]}」 实测={m[:300]}")
            ctl.append(f"{i} 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词")
    return ("；\n  ".join(pos), "\n  ".join(dict.fromkeys(ctl)))


def main() -> int:
    started = now_iso()
    OUT.write_text(json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    if DEDUP["refuse"]:
        print(json.dumps({"refuse": [f"dedup 件自带拒绝：{DEDUP['refuse'][:2]}"]}, ensure_ascii=False))
        return 1
    if DEDUP["duplicates"]:
        print(json.dumps({"refuse": [f"判重命中却不许占号：{DEDUP['duplicates']}"]}, ensure_ascii=False))
        return 1
    bad_keys = [c["key"] for c in PLAN if REPRO["keys"].get(c["key"], {}).get("exit_code") != 0]
    if bad_keys:
        print(json.dumps({"refuse": [f"这些单对应的复现命令退出码不是 0（没现形就不许入账）：{bad_keys}"]},
                         ensure_ascii=False))
        return 1
    text0 = LEDGER.read_text(encoding="utf-8")
    nums0 = sorted(int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", text0))
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    n_bug0 = db.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    db.close()
    expect_next = nums0[-1] + 1

    filed, refuse = [], []
    for card in PLAN:
        summary = f"[{card['key']}] {card['title']}"
        if summary in text0:
            refuse.append(f"幂等守卫：账本里已有同一条 summary，不重复入账 → {summary[:60]}")
            continue
        pos, ctl = symptom_lines(card["key"], card["symptoms"])
        cmd = REPRO_CMD.format(key=card["key"])
        detail = (f"立单依据（文档声明/自述原文，含 file:line）：\n  {pos}\n\n"
                  f"成对对照（同族里今天行为正确的形状）：\n  {ctl}\n\n"
                  f"机制（file:line 级，本环未改产品码）：{card['mechanism']}\n\n"
                  f"为什么值得入账：一张单一个根因，症状 {len(card['symptoms'])} 条："
                  f"{'、'.join(card['symptoms'])}。\n\n"
                  f"复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：{cmd}\n"
                  f"整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、"
                  f".fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）\n\n"
                  f"不算证明：{NOT_PROOF[card['key']]}\n\n"
                  f"去重结论：与 memory/bugs.md 现有 {DEDUP['ledger_cards']} 单按**机制签名**比对无重合"
                  f"（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。\n\n"
                  f"来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] "
                  f"{now_iso()} 实测；severity={card['severity']}；修属：{card['owner']}")
        resp = {}
        try:
            c = lfist_lib.Client(timeout=180)
            resp = c.call("report_bug", {"summary": summary, "detail": detail,
                                         "severity": card["severity"], "project_dir": ".",
                                         "reported_by": "cypy-hunter", "publish_task": True,
                                         "now": lfist_lib.utc_now()})
            c.close()
        except Exception as exc:  # RPC 失败不许被吞
            refuse.append(f"{card['key']}：report_bug 抛 {type(exc).__name__}: {exc}")
            continue
        back = LEDGER.read_text(encoding="utf-8")
        nums = sorted(int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", back))
        got_num = nums[-1] if nums else None
        entry = {"key": card["key"], "rpc": {k: resp.get(k) for k in ("bug_id", "id", "task_id")},
                 "ledger_number": f"BUG-{got_num}", "expected": f"BUG-{expect_next}",
                 "summary_on_disk": summary in back,
                 "detail_on_disk": card["mechanism"][:40] in back,
                 "repro_cmd_on_disk": cmd in back,
                 "not_proof_on_disk": NOT_PROOF[card["key"]][:20] in back}
        expect_next += 1
        if not entry["summary_on_disk"]:
            refuse.append(f"{card['key']}：入账后账本搜不到这条 summary（RPC 回执 {json.dumps(resp, ensure_ascii=False)[:160]}）")
        if entry["ledger_number"] != entry["expected"]:
            refuse.append(f"{card['key']}：号不连续，实得 {entry['ledger_number']} 期望 {entry['expected']}")
        filed.append(entry)
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    n_bug1 = db.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    recent = db.execute("select id, status, substr(description,1,60) from tasks where ns='bugs' "
                        "order by id desc limit ?", (len(filed),)).fetchall()
    db.close()
    doc = {"started": started, "filed": [f["ledger_number"] for f in filed], "entries": filed,
           "filed_total": len(filed), "plan_total": len(PLAN),
           "numbering_from_disk": {"before_max": nums0[-1], "first_new": nums0[-1] + 1},
           "ledger_before": len(nums0), "ledger_after": len(nums0) + len(filed),
           "sqlite_bug_rows": {"before": n_bug0, "after": n_bug1, "delta": n_bug1 - n_bug0},
           "sqlite_recent": [list(r) for r in recent],
           "withdrawn_design": DECLARED["withdrawn_design"],
           "not_measured": DECLARED["not_measured_or_true"],
           "refuse": sorted(set(refuse)), "at_utc": now_iso()}
    if doc["sqlite_bug_rows"]["delta"] != len(filed):
        doc["refuse"].append(f"sqlite bug 行增量 {doc['sqlite_bug_rows']['delta']} ≠ 入账条数 {len(filed)}")
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "filed": doc["filed"],
                      "numbering": doc["numbering_from_disk"], "sqlite": doc["sqlite_bug_rows"],
                      "recent": doc["sqlite_recent"][:3]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(json.dumps({"refuse": [f"崩在 {type(exc).__name__}: {exc}"]},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
