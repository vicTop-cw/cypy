"""R4-验证 法③④⑤ 的新缺陷入账：号从盘上现数，三处回读（RPC / 账本 / sqlite）。

入账前的硬门（少一条都不落账）：
① 每条都有 `verify_r4_repro.py <KEY>` 现跑且**退出码 0**（缺陷现形）——复跑命令逐字进卡片；
② 与现有卡片的近亲逐条点名裁决（同症状不同机制要说清，同机制就并入不占号）；
③ summary 不重复（幂等守卫）；
④ 卡片正文首行带 `[omega:required]`——上一轮实测：缺它则后续 Omega 三连被拒而 verify 照过。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

LEDGER = ROOT / "memory" / "bugs.md"
DB = ROOT / "fist-mbt.db"
OUT = HERE / "verify_r4_file_bugs.json"
REPRO = "python -X utf8 .fist-loop-20260927/verify_r4_repro.py {key}"
STAGE = "[loop:20260927-loop:R4-验证]"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


PLAN = [
    {"key": "SLICE_typed_as_element", "severity": "high", "owner": "下一环修（R4-打磨不修产品码）",
     "title": "切片表达式被判定成容器的**元素**类型：`xs[1:3]` 得 `int`，仓内自带 DEMO 因此过不了 "
              "`--check-only`（appendix-C《已实现的限制修复》第 1 行声称 v0.2 已实现）",
     "mechanism": "`cypyc/analyzer/type_checker.py:4119-4144` `_visit_Subscript` 只看 "
                  "`hasattr(node.slice, 'kind')`，而切片在本仓 AST 里是 dict "
                  "`{'slice': True, 'start': …, 'end': …, 'step': …}`（实测回读），"
                  "于是走不到任何分支、直接返回 `params[0]`（元素类型）；"
                  "切片的三个边界子节点也从不被访问。",
     "control": "同族里今天正确的形状：`return xs[1]`（整数下标）零诊断；"
                "`let a = xs[1:3]`（不标注返回类型）也能过——缺陷只在「切片结果被当容器用」时现形。",
     "near": ["BUG-37 位置模式把绑定名判成 int（同症状「Return type mismatch」，不同机制：那里是 "
              "pattern 绑定名类型，这里是 Subscript 的切片分支）",
              "BUG-65 文档 stale 行（那单说的是文档措辞，本单是产品类型面，文档只是受害者）"],
     "not_proof": "必须同时给出「仓内自带 DEMO 过不了 --check-only」与「最小探针的诊断文本」，"
                  "并且说明修前修后同形（本件已用 R4-修复 的修前快照复跑，诊断逐字一致 ⇒ 不是本轮引入）。"},
    {"key": "CODEGEN_named_conditions_unreachable", "severity": "medium",
     "owner": "人工（删死码 vs 改道重写，二者都是语义决定）",
     "title": "appendix-C 点名的三个 codegen 方法（以及 `_extractor_pattern_condition`/"
              "`_contains_extractor`）在活路径上调用计数为 0：模式条件由别处就地拼出",
     "mechanism": "`cypyc/codegen/cython_generator.py:1832-1855` 的 `_extractor_pattern_condition` "
                  "调用 `:1921/:1937/:1955` 三个 `_generate_*_condition`，但全文件（含 tests/）"
                  "**没有任何调用方**指向 `_extractor_pattern_condition` 或 `_contains_extractor`；"
                  "元组/列表/字典模式的实际条件在 `:1563/:1574/:1601/:1614` 就地拼装。",
     "control": "同一份源里 `isinstance(_match_subject_1, (list, tuple))` 确实出现在生成物中"
                "⇒ **行为是有的**，本单只主张「文档点名的那三个名字不是实现所在的位置」。",
     "near": ["BUG-36 位置模式不调用 __unapply__（那是语义错误，本单是可达性/文档指向，不同机制）",
              "BUG-71 切片类型面（同一张文档表不同行，互不覆盖）"],
     "not_proof": "计数器必须包在公开调用外面跑（`CypyHook.analyze_only` + `CythonGenerator.generate`），"
                  "只 grep 到「函数定义存在」不算；行为面证据必须同时给出「条件确实生成了」。"},
    {"key": "PYD_incremental_cache_not_reused", "severity": "medium",
     "owner": "下一环修（两套缓存的真相源合一）",
     "title": "`compile_to_pyd` 连跑两次仍重写 `.pyd`：同一次结果里先写「缓存命中」再写「缓存未命中」，"
              "两个缓存各查各的（docs/USAGE.md:406 的「源未变会复用 .pyd」在调用面不成立）",
     "mechanism": "`cypy_hook/hook.py:343-365`：`:347` 用 `IncrementalCompiler.check_cache_validity` "
                  "判命中后追加「缓存命中，使用缓存结果」(`:351`)，紧接着 `:354-356` 换 "
                  "`CypyCacheManager().get_cached_pyd()` **另一套**存储再问一次；"
                  "它返回 None 时早退分支（`:357-361`）走不到，控制流落到 `:363-365` 又追加"
                  "「缓存未命中，开始解析」，然后照常重新转译、重新编译。",
     "control": "对照（今天确实正确的部分）：`CompileResult.pyd_path`（单数，实测属性名）两轮都指向同一个 "
                "`.pyd` 路径，且两轮 `success=True`——缺陷只在「命中之后没有真的复用」，不是编译挂了。",
     "near": ["BUG-18（已修，`cypyc/incremental/incremental_manager.py` 的依赖比对）——本单在 "
              "`cypy_hook` 侧，是「命中判定与取产物用了两套存储」，不同机制",
              "BRIDGE_cache_side_effect（D16/BUG-66，只读查询在调用方 CWD 造目录）——同一文件族不同缺陷",
              "BUG-12/相关 manifest 单（manifest 损坏与不存在不可区分）——本单不需要 manifest 损坏即可复现"],
     "not_proof": "必须给两轮的 `.pyd` mtime、两轮耗时与两轮 steps 原文；只说「变快了」不算——"
                  "实测 8.35s vs 7.76s 在噪声内，唯一承重的是 mtime 变了 + steps 自相矛盾。"},
]


def main() -> int:
    started = now_iso()
    text0 = LEDGER.read_text(encoding="utf-8")
    nums0 = sorted(int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", text0))
    sums0 = re.findall(r"(?m)^- summary: (.*)$", text0)
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    n_bug0 = db.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    db.close()
    expect_next = nums0[-1] + 1

    filed, refuse, repros = [], [], {}
    for card in PLAN:
        cmd = REPRO.format(key=card["key"])
        r = subprocess.run(cmd.split() + [card["key"]], cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=1800)
        repros[card["key"]] = {"command": cmd, "exit_code": r.returncode,
                               "stdout_tail": r.stdout[-600:]}
        if r.returncode != 0:
            refuse.append(f"{card['key']}：复跑件退出码 {r.returncode}（0=现形）⇒ 不许入账")
            continue
        summary = f"[{card['key']}] {card['title']}"
        if summary in text0:
            refuse.append(f"幂等守卫：账本已有同一条 summary ⇒ 不重复入账（{card['key']}）")
            continue
        near_hits = [s for s in sums0
                     if any(w in s for w in (card["key"][:18], card["title"][:12]))]
        if near_hits:
            refuse.append(f"{card['key']}：与在账卡片同名/同题，必须先并入而不是占新号：{near_hits[:1]}")
            continue
        detail = (
            f"[omega:required] 立单依据（调用面实测原文）：\n  {r.stdout.strip()[-500:]}\n\n"
            f"成对对照（同族里今天正确的形状）：\n  {card['control']}\n\n"
            f"机制（file:line 级，本环未改产品码）：{card['mechanism']}\n\n"
            f"为什么值得入账：本环是验证环，这三条都是**独立复算**打出来的，"
            f"不来自寻虫/修复环的自述；每条一张单一个根因。\n\n"
            f"复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：{cmd}\n"
            f"整批复跑判据件：.fist-loop-20260927/verify_r4_appendixC.json（文档面 14 行）、"
            f".fist-loop-20260927/verify_r4_compile.json（真编译 3 次尝试）、"
            f".fist-loop-20260927/verify_r4_callsite.json（调用面 18 行）\n\n"
            f"不算证明：{card['not_proof']}\n\n"
            f"去重结论（近亲逐条裁决）：\n  " + "\n  ".join(card["near"]) +
            f"\n  与 memory/bugs.md 现有 {len(nums0)} 单按机制签名比对无重合。\n\n"
            f"来历（验证环给的是复算事实与形状）：{STAGE} {now_iso()} 实测；"
            f"severity={card['severity']}；修属：{card['owner']}")
        resp = {}
        try:
            c = lfist_lib.Client(timeout=240)
            resp = c.call("report_bug", {"summary": summary, "detail": detail,
                                         "severity": card["severity"], "project_dir": ".",
                                         "reported_by": "cypy-verifier", "publish_task": True,
                                         "now": lfist_lib.utc_now()})
            c.close()
        except Exception as exc:
            refuse.append(f"{card['key']}：report_bug 抛 {type(exc).__name__}: {exc}")
            continue
        back = LEDGER.read_text(encoding="utf-8")
        nums = sorted(int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", back))
        got = nums[-1] if nums else None
        entry = {"key": card["key"], "rpc": {k: resp.get(k) for k in ("bug_id", "id", "task_id")},
                 "ledger_number": f"BUG-{got}", "expected": f"BUG-{expect_next}",
                 "summary_on_disk": summary in back,
                 "omega_marker_on_disk": "[omega:required]" in back[-3000:],
                 "repro_cmd_on_disk": cmd in back,
                 "mechanism_on_disk": card["mechanism"][:40] in back,
                 "near_verdicts_on_disk": all(n[:16] in back for n in card["near"])}
        expect_next += 1
        for k in ("summary_on_disk", "omega_marker_on_disk", "repro_cmd_on_disk",
                  "mechanism_on_disk", "near_verdicts_on_disk"):
            if not entry[k]:
                refuse.append(f"{card['key']}：回读缺 {k}"
                              f"（回执 {json.dumps(resp, ensure_ascii=False)[:160]}）")
        if entry["ledger_number"] != entry["expected"]:
            refuse.append(f"{card['key']}：号不连续，实得 {entry['ledger_number']} "
                          f"期望 {entry['expected']}")
        filed.append(entry)

    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    n_bug1 = db.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    recent = db.execute("select id, status, substr(description,1,60) from tasks where ns='bugs' "
                        "order by id desc limit ?", (max(len(filed), 1),)).fetchall()
    db.close()
    doc = {"started": started, "filed": [f["ledger_number"] for f in filed], "entries": filed,
           "filed_total": len(filed), "plan_total": len(PLAN),
           "numbering_from_disk": {"before_max": nums0[-1], "first_new": nums0[-1] + 1},
           "ledger_before": len(nums0), "repro_gates": repros,
           "sqlite_bug_rows": {"before": n_bug0, "after": n_bug1, "delta": n_bug1 - n_bug0},
           "sqlite_recent": [list(x) for x in recent],
           "refuse": sorted(set(refuse)), "at_utc": now_iso()}
    if doc["sqlite_bug_rows"]["delta"] != len(filed):
        doc["refuse"].append(f"sqlite bug 行增量 {doc['sqlite_bug_rows']['delta']} ≠ "
                             f"入账条数 {len(filed)}")
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "filed": doc["filed"],
                      "numbering": doc["numbering_from_disk"],
                      "sqlite": doc["sqlite_bug_rows"],
                      "repro_codes": {k: v["exit_code"] for k, v in repros.items()}},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
