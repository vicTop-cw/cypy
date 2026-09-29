"""R4-推进 的第二半：把量表与后果件里钉住的缺陷**真入账**，并自证号与文都落了盘。

只数不报＝把已知缺陷留在我的会话记忆里，下一环就没了。所以这张件做四件事：
① 号从账本现读（`max+1`），不抄计划；② 逐卡拉 `report_bug`，回执与账本双向对齐；
③ 卡里的数字全部从判据件反解（`advance_r4_scope_face.json` 的量表行 /
   `advance_r4_dormant.json` 的形状行与守卫行），不是我另打一遍——重打必造出第二套事实；
④ 判据件里预先点名的卡号（`^=`→BUG-74、`^`/`~`→BUG-75、defer 出口→BUG-76）要与实际落账
   的号一致，不一致就是判据件在指一张不存在的卡。

幂等守卫：账本里已有同 summary 就跳过（本环重跑不许生两张同 id 的卡）。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402
from loop_kit import record  # noqa: E402

LEDGER = ROOT / "memory" / "bugs.md"
DB = (ROOT / "fist-mbt.db").as_posix()
SCALE = HERE / "advance_r4_scope_face.json"
DORMANT = HERE / "advance_r4_dormant.json"
OUT = HERE / "advance_r4_filed.json"
REPRO_SCALE = "python -X utf8 .fist-loop-20260927/advance_r4_scope_face.py"
REPRO_DORM = "python -X utf8 .fist-loop-20260927/advance_r4_dormant.py"
DEFER_KEY = "DEFER_nested_return_exit_skips_cleanup"
GUARD_KEY = "TEST_vacuous_success_guard_hides_assertions"
NOT_PROOF_XOR = ("只测了 int 字面量与常量右值，没测变量右值、非 int 左操作数与 `with`/循环里的"
                 "形状；产物层面未编译成 .pyd，因此不主张运行期数值。")
CARDS = [
    {"key": "CODEGEN_augmented_xor_drops_left_operand", "src": "scale", "op": "^=",
     "title": "复合赋值 `^=` 静默产出 `x = <右值>`，左操作数与运算符一起丢了",
     "severity": "high", "owner": "codegen/parser",
     "mechanism": "cypyc/parser/lexer.py:955-973 把裸 `^` 恒判为 BUILD_VALUE 词位"
                  "（后缀构建值运算符），cypyc/parser/parser.py:3796-3800 的 "
                  "`_parse_power_expr` 在 BUILD_VALUE 分支里把它吞掉；于是 `x ^= 5` 的语句右侧"
                  "只剩 `= 5`，产物写 `x = 5` 且 rc=0（不报错）",
     "why": "同一张运算符表里 12 条复合赋值有 11 条行为正确（产物逐字等于文档自己写的等价式），"
            "被响亮拒绝的运算符至少报错——本卡形状是 rc=0 且产物与文档声明不等，属于静默产错码。",
     "not_proof": NOT_PROOF_XOR, "repro": REPRO_SCALE,
     "repro_note": "本卡的形状钉在 `silent_wrong` / `declared_rejected` 两个集合里，"
                   "修好后那两格会红，逼来人关账",
     "extra": "夹具：.fist-loop-20260927/advance_r4_probe/（另含量表内联生成的 "
              "aug00..aug11 / bin00..bin09）"},
    {"key": "LEXER_bitwise_xor_and_invert_unreachable", "src": "scale", "op": ["^", "~"],
     "title": "文档声明的二元 `a ^ b` 与一元 `~a` 在 CLI 上不可达（与 `^:`/`~:` 构建块共用词位）",
     "severity": "medium", "owner": "lexer/parser",
     "mechanism": "同一条词位判定：`^` 只作 BUILD_VALUE、`~` 只作 BUILD_VALUE/构建块前缀，"
                  "二元/一元用法在 `_parse_power_expr` 之后没有优先级位 ⇒ 二元 `^` 报 "
                  "「Expected RPAREN, got IDENTIFIER」、一元 `~` 报「Unexpected token TILDE」。"
                  "修法要给 `^`/`~` 加上下文消歧，而 `^:`（索引构建块，"
                  "SYNTAX/13-build-blocks.md）与 `~:` 是冻结语义 ⇒ 不能只放开词位了事",
     "why": "文档把 `^`/`~` 列为运算符（声明面存在），而 CLI 调用面上两个形状都被拒绝；"
            "本环按裁定不动解析器，只把形状钉进账，等语义裁决给消歧规则。",
     "not_proof": "没有穷举 `^`/`~` 在构建块之外的所有上下文（宏体、块内表达式），只测了顶层"
                  "表达式位；消歧方案未评估，不主张「加个向前看就能修」。",
     "repro": REPRO_SCALE,
     "repro_note": "二元/一元两档钉在 `declared_rejected` 集合里，放开词位后那格会红",
     "extra": "另见 .fist-loop-20260927/advance_r4_scope_face.json 的 `adjudication` 栏"},
    {"key": DEFER_KEY, "src": "dorm", "shape": "defer_two_exits",
     "title": "`defer` 的清理只注入函数体顶层出口，`if`/`for` 里的 return 静默跳过清理",
     "severity": "high", "owner": "codegen",
     "mechanism": "cypyc/codegen/cython_generator.py:979-1000：分离出 defer 之后只遍历**顶层** "
                  "normal_stmts，遇到顶层 ReturnStmt 才在其前面注入清理并置 emitted_at_return；"
                  "嵌套在 if/for 里的 return 不是顶层语句 ⇒ 那条出口没有清理，而函数末尾的兜底"
                  "注入又被 emitted_at_return 关掉。实测：2 个出口只发 1 次清理，rc=0 且零诊断。",
     "why": "声明面（`SYNTAX/14-syntax-sugar.md:167-190`、`SYNTAX/04-pointer-types.md:59-63`）"
            "承诺「函数退出时自动执行」，`SYNTAX/04-pointer-types.md:133` 还把「指针必须用 defer "
            "清理」列为规则；带条件返回的函数在最常用的形状上静默漏清理。",
     "not_proof": "只测了 `if` 内单条 return 与顶层 return 并存的最小形状，没测 for/while/match "
                  "里的出口，也没测异常路径——文档从未承诺 try/finally，本卡不主张异常安全；"
                  "未编译成 .pyd 跑运行期句柄计数。",
     "repro": REPRO_DORM,
     "repro_note": "本卡的出口数/清理次数钉在件的 `pinned_defect` 与「钉住的缺陷」那格自证里，"
                   "修好后 [2, 1] 会红，和关账一起走",
     "extra": "同件另测得 `defer_before_return`（清理搬到 return 之前，这条路可达）与 "
              "`two_defers_lifo`（逆序成立）两档今天是对的，本卡只在多出口形状上成立"},
    {"key": GUARD_KEY, "src": "dorm", "shape": "guards",
     "title": "`if result.success` 型守卫让代码生成断言在编译失败时静默空过（余 7 处）",
     "severity": "medium", "owner": "tests",
     "mechanism": "tests/test_codegen_verification.py 与 tests/test_unit_test_modes.py 里共 8 处 "
                  "`if result.success [and result.cython_code]:` 把整块断言挂在「编译成功」上："
                  "编译一失败，测试直接 pass。本环放行文档内建名 `open` 之后，"
                  "test_defer_statement 从空过变成真跑并立刻暴露一条超出声明面的期望，"
                  "证明这批守卫的实际覆盖面是 0 而不是「宽松」。",
     "why": "同一模式下「绿」不代表任何事：名称面、语法面、代码生成面任何一处退化都不会红。"
            "本环按指挥官裁决改掉被激活的那一条（期望改成声明面语义 + 去掉守卫），余下 7 处"
            "逐条点名（file:line 见证据），要么改成无条件断言，要么写明它凭什么不断言。",
     "not_proof": "只数了字面形态 `if result.success` 的语句行（注释里提到该字面不算），"
                  "没测 skip/xfail/try-except 之类的其它静默通道，也没逐条判断那 7 处去掉守卫后"
                  "各自会不会红。",
     "repro": REPRO_DORM,
     "repro_note": "守卫清单钉在件的 `vacuous_guards.sites`；条数从 8 掉到 7 是本环改动的直接后果，"
                   "R5 收完应为 0",
     "extra": "改后的 test_defer_statement 函数体逐字在件的 `test_patch.body_after` 里"},
]
CHECKS: list = []
REFUSE: list = []


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def evidence(card: dict) -> tuple:
    """从判据件反解本卡的证据行，返回 (证据行, 件名, 范围说明, 复跑串)。"""
    if card["src"] == "scale":
        data = json.loads(SCALE.read_text(encoding="utf-8"))
        rows = data["augmented_matrix"] + data["binary_matrix"]
        ops = card["op"] if isinstance(card["op"], list) else [card["op"]]
        picked = [r for r in rows if r["op"] in ops]
        if len(picked) != len(ops):
            REFUSE.append(f"量表里找不到 {ops}，只找到 {[r['op'] for r in picked]}")
            return [], SCALE.name, "", card["repro"]
        evi = [{"op": r["op"], "state": r["state"], "rc": r["rc"],
                "declared_at": r.get("declared_at"), "spec": r.get("spec_formula"),
                "generated": r.get("generated") or r.get("error_tail")} for r in picked]
        return (evi, SCALE.name, f"运算符量表共 {len(rows)} 行，本卡取 {len(evi)} 行",
                card["repro"])
    d = json.loads(DORMANT.read_text(encoding="utf-8"))
    act = d["activation"]
    if card["shape"] == "guards":
        g = d["vacuous_guards"]
        evi = [f"{s['file']}:{s['line']} {s['text']}" for s in g["sites"]]
        scope = (f"字面形态 {g['pattern']} 现存 {g['count']} 处（本环去掉 1 处，原 8 处）；"
                 f"激活证明：改前 {act['before']['undefined_open']} ⇒ "
                 f"success={act['before']['success']}（守卫为假，整块断言被跳过）；改后 "
                 f"success={act['after']['success']} 且 try={act['after']['has_try']}、"
                 f"finally={act['after']['has_finally']}")
        return (evi, DORMANT.name, scope, card["repro"])
    row = next((r for r in d["shapes"] if r["shape"] == card["shape"]), None)
    if row is None:
        REFUSE.append(f"后果件里没有 {card['shape']} 这一形状")
        return [], DORMANT.name, "", card["repro"]
    pin = d["pinned_defect"]
    evi = [{"shape": row["shape"], "tested_function": row["tested_function"],
            "exit_paths": row["exit_paths"], "cleanup_count": row["cleanup_count"],
            "product_slice": row["function_slice"],
            "declaration_lines": [r["file"] + ":" + "-".join(map(str, r["lines"]))
                                  for r in d["doc_basis"]]}]
    scope = (f"4 个形状实测（{[r['shape'] for r in d['shapes']]}），本卡取 {card['shape']}："
             f"{pin['exit_paths']} 个出口 / 清理发出 {pin['cleanup_count']} 次")
    return (evi, DORMANT.name, scope, card["repro"])


def main() -> int:
    started = now_iso()
    missing = [p.name for p in (SCALE, DORMANT) if not p.exists()]
    if missing:
        print(json.dumps({"refuse": [f"判据件不在盘上，不派单：{missing}"]}, ensure_ascii=False))
        return 1
    base = LEDGER.read_text(encoding="utf-8")
    nums0 = sorted(int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", base))
    expect = nums0[-1] + 1
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n_bug0 = con.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    con.close()

    filed = []
    for card in CARDS:
        summary = f"[{card['key']}] {card['title']}"
        if summary in base:
            filed.append({"key": card["key"], "skipped": True, "summary": summary,
                          "note": "幂等守卫：账本已有同 summary，不重发"})
            continue
        evi, art_name, scope_note, repro = evidence(card)
        if not evi:
            REFUSE.append(f"{card['key']}：反解不到证据行，不派单")
            continue
        detail = (
            f"实测证据（全部来自 .fist-loop-20260927/{art_name}；{scope_note}）：\n"
            f"  {json.dumps(evi, ensure_ascii=False)}\n\n"
            f"机制（file:line 级，本环未改产品码）：{card['mechanism']}\n\n"
            f"为什么值得入账：{card['why']}\n\n"
            f"复跑：{repro} —— {card['repro_note']}\n{card['extra']}\n\n"
            f"不算证明：{card['not_proof']}\n\n"
            f"来历（推进环只给调用面事实，修属 R5-修复）：[loop:20260927-loop:R4-推进] "
            f"{now_iso()} 实测；severity={card['severity']}；修属={card['owner']}")
        params = {"summary": summary, "detail": detail, "severity": card["severity"],
                  "project_dir": ".", "reported_by": "cypy-advancer",
                  "publish_task": True, "now": lfist_lib.utc_now()}
        try:
            c = lfist_lib.Client(timeout=180)
            resp = c.call("report_bug", params)
            c.close()
        except Exception as exc:  # RPC 失败不许被吞
            REFUSE.append(f"{card['key']}：report_bug 抛 {type(exc).__name__}: {exc}")
            continue
        back = LEDGER.read_text(encoding="utf-8")
        nums = sorted(int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", back))
        got = nums[-1] if nums else None
        entry = {"key": card["key"], "summary": summary, "skipped": False,
                 "rpc": {k: resp.get(k) for k in ("bug_id", "id", "task_id")},
                 "ledger_number": f"BUG-{got}", "expected": f"BUG-{expect}",
                 "summary_on_disk": summary in back,
                 "mechanism_on_disk": card["mechanism"][:40] in back,
                 "repro_on_disk": repro in back, "rows_in_detail": len(evi)}
        expect += 1
        base = back
        if not entry["summary_on_disk"]:
            REFUSE.append(f"{card['key']}：入账后账本搜不到 summary（回执 "
                          f"{json.dumps(resp, ensure_ascii=False)[:200]}）")
        if entry["ledger_number"] != entry["expected"]:
            REFUSE.append(f"{card['key']}：号不连续，实得 {entry['ledger_number']} "
                          f"期望 {entry['expected']}")
        if not entry["repro_on_disk"]:
            REFUSE.append(f"{card['key']}：复跑命令没进账本（活证据缺失）")
        filed.append(entry)
        record(CHECKS, REFUSE, f"{card['key']}：detail 里的行数要与判据件反解到的行数一致",
               entry["rows_in_detail"], len(evi), "不许手打第二套数")

    after = LEDGER.read_text(encoding="utf-8")
    for e in filed:
        if e["skipped"]:
            i = after.find(e["summary"])
            head = re.findall(r"(?m)^## BUG-(\d+) ", after[:i] if i > 0 else "")
            e["ledger_number"] = f"BUG-{head[-1]}" if head else "未反解到"
    by_key = {e["key"]: e.get("ledger_number", "未反解到") for e in filed}
    scale = json.loads(SCALE.read_text(encoding="utf-8"))
    dorm = json.loads(DORMANT.read_text(encoding="utf-8"))
    pinned = {q["key"]: q["bug_card"] for q in scale["adjudication_queue"] if q["bug_card"]}
    by_op = {}
    for card in CARDS:
        if card["src"] != "scale":
            continue
        ops = card["op"] if isinstance(card["op"], list) else [card["op"]]
        for o in ops:
            by_op[o] = by_key[card["key"]]
    mismatch = {o: [pinned[o], by_op.get(o)] for o in pinned if pinned[o] != by_op.get(o)}
    if by_key.get(DEFER_KEY) != dorm["card_expected_id"]:
        mismatch[DEFER_KEY] = [dorm["card_expected_id"], by_key.get(DEFER_KEY)]
    record(CHECKS, REFUSE,
           "判据件点名的卡号要等于实际落账号（不一致就是它在指一张不存在的卡）",
           [len(pinned) + 1, mismatch], [4, {}], json.dumps(mismatch, ensure_ascii=False))
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n_bug1 = con.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    con.close()
    live = sum(1 for f in filed if not f["skipped"])
    record(CHECKS, REFUSE, "未跳过的卡数要与 sqlite bug 任务增量一致（md 与库两栏同判）",
           [live, n_bug1 - n_bug0], [live, live],
           f"md 新增 {len(re.findall(chr(94) + '## BUG-', after)) - len(nums0)} 条，"
           f"sqlite 增量 {n_bug1 - n_bug0}；四张卡的号 {sorted(by_key.values())}")
    doc = {"started": started, "cards": [c["key"] for c in CARDS], "filed": filed,
           "ledger": "memory/bugs.md", "ledger_before_max": nums0[-1],
           "ledger_after_max": sorted(int(m) for m in
                                      re.findall(r"(?m)^## BUG-(\d+) ", after))[-1],
           "sqlite_bug_tasks_before": n_bug0, "sqlite_bug_tasks_after": n_bug1,
           "pinned_card_ids": {**pinned, DEFER_KEY: dorm["card_expected_id"]},
           "measured_artifacts": [SCALE.name, DORMANT.name],
           "repro": [REPRO_SCALE, REPRO_DORM], "decision_quoted": dorm["decision"],
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)), "at_utc": now_iso()}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"],
                      "filed": [(f["key"], f.get("ledger_number"), f["skipped"]) for f in filed],
                      "sqlite_delta": [n_bug0, n_bug1],
                      "pinned": doc["pinned_card_ids"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
