#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Match-once patch: disclose lifecycle refusals verbatim + make verify_report4 derive its sets.

Two real defects found by `verify_report4.py`:
  1. it hardcoded `intake_map.json..intake_map4.json`, so BUG-13 (intake_map5) was invisible and
     its "all booked tickets are done" expectation could not hold;
  2. `close_fixes.out.json` records two refused root-task calls whose original text was never
     put into the report -- the red line "失败原样上报" was actually violated.

Every `old` must match exactly once or nothing is written. Both files are compiled with warnings
as errors before writing (plain compile() misses invalid-escape SyntaxWarnings).
"""
import re
import sys
import warnings

GR = ".fist-polish-20260926/gen_report.py"
V4 = ".fist-polish-20260926/verify_report4.py"

EDITS = [
    # ---- gen_report.py: build the refusal inventory from the evidence itself
    (GR,
     'diag_summary = "；".join(f"{e[\'tag\'].split(\':\')[1]}：{diag_verdict(e[\'result\'])}" for e in diag)\n',
     'diag_summary = "；".join(f"{e[\'tag\'].split(\':\')[1]}：{diag_verdict(e[\'result\'])}" for e in diag)\n'
     'REFUSALS = [(e["tag"], diag_verdict(e["result"])) for e in close\n'
     '            if isinstance(e.get("result"), dict) and e["result"].get("__error__")]\n'
     'root_refusal_line = ("；".join(f"`{_t}` → `{_m}`" for _t, _m in REFUSALS\n'
     '                           if _t.startswith("T0:"))\n'
     '                      or "无：本轮对根任务 `T0` 的调用没有被拒记录")\n'),

    # ---- gen_report.py: disclose the two root-task refusals next to the orphan-task note
    (GR,
     '3. 诊断期间产生的孤儿任务（{diag_summary}）——归档步骤见 §六，未把诊断噪声留作待办。\n',
     '3. 诊断期间产生的孤儿任务（{diag_summary}）——归档步骤见 §六，未把诊断噪声留作待办。\n'
     '   同一批取证里还有两条对根任务的拒绝（{root_refusal_line}）：{FIXED_TOTAL} 张修复单 `verify`\n'
     '   之后根任务已自动上卷到「待验收」，此时再对它走 `execute`/`submit` 就是非法迁移，直接\n'
     '   `verify` → `archive` 通过。这两条按红线原样留档，不是被吞掉的失败，也不是新缺陷。\n'),

    # ---- gen_report.py: refuse to write a report that hides a recorded refusal
    (GR,
     'with open(os.path.join(out, f"{stamp}.md"), "w", encoding="utf-8") as f:\n    f.write(body)\n',
     '_undisclosed = [f"{_t}：{_m}" for _t, _m in REFUSALS if _m not in body]\n'
     'if _undisclosed:\n'
     '    sys.exit("judge guard: 生命周期被拒的原始文案没逐字进正文（红线「失败原样上报」）："\n'
     '             + "；".join(_undisclosed))\n\n'
     'with open(os.path.join(out, f"{stamp}.md"), "w", encoding="utf-8") as f:\n    f.write(body)\n'),

    # ---- verify_report4.py: derive maps/ledger/closure-sets instead of hardcoding them
    (V4,
     'mapping = []\n'
     'for f in ("intake_map.json", "intake_map2.json", "intake_map3.json", "intake_map4.json"):\n'
     '    mapping += json.load(open(os.path.join(HERE, f), encoding="utf-8"))["mapping"]\n'
     'tids = [r["task_id"] for r in mapping]\n'
     'check(all(tids), f"每单都要有自动发布的任务 id，实得 {tids}")\n'
     'for r in mapping:\n'
     '    check(f"{r[\'bug_id\']}" in text and str(r["task_id"]) in text,\n'
     '          f"闭环表要同时含 {r[\'bug_id\']} 与 {r[\'task_id\']}")\n'
     'check(text.count("| BUG-") >= len(mapping),\n'
     '      f"闭环表行数 {text.count(\'| BUG-\')} 不得少于确诊数 {len(mapping)}")\n'
     '\n'
     'ledger = json.load(open(os.path.join(HERE, "probe_ledger_final.json"), encoding="utf-8"))\n'
     'check(ledger["tickets_total"] == len(mapping) and ledger["tickets_done"] == ledger["tickets_total"],\n'
     '      f"只读查库要与账本一致：done={ledger[\'tickets_done\']}/{ledger[\'tickets_total\']} vs 确诊 {len(mapping)}")\n'
     'close = []\n'
     'for f in ("close_fixes.out.json", "close_fixes2.out.json", "close_fixes3.out.json",\n'
     '          "close_fixes4.out.json"):\n'
     '    close += json.load(open(os.path.join(HERE, f), encoding="utf-8"))\n',
     'map_files = sorted(glob.glob(os.path.join(HERE, "intake_map*.json")))\n'
     'check(len(map_files) >= 1, "驱动目录里要有 intake_map*.json，实得 0 份")\n'
     'mapping = []\n'
     'for f in map_files:\n'
     '    mapping += json.load(open(f, encoding="utf-8"))["mapping"]\n'
     'bugs_in = [r["bug_id"] for r in mapping]\n'
     'check(len(bugs_in) == len(set(bugs_in)),\n'
     '      f"入账映射不许把同一个 bug 登记两次：{sorted(bugs_in)}")\n'
     'tids = [r["task_id"] for r in mapping]\n'
     'check(all(tids), f"每单都要有自动发布的任务 id，实得 {tids}")\n'
     'for r in mapping:\n'
     '    check(f"{r[\'bug_id\']}" in text and str(r["task_id"]) in text,\n'
     '          f"闭环表要同时含 {r[\'bug_id\']} 与 {r[\'task_id\']}")\n'
     'trows = re.findall(r"(?m)^(\\| BUG-\\d+ \\| [^\\n]*T0r\\d+[^\\n]*$)", text)\n'
     'bug_of = lambda ln: ln.split("|")[1].strip()\n'
     'check(sorted(map(bug_of, trows)) == sorted(bugs_in),\n'
     '      f"闭环表逐单一行且仅一行：表内 {sorted(map(bug_of, trows))} vs 入账 {sorted(bugs_in)}")\n'
     '\n'
     'ledger = json.load(open(os.path.join(HERE, "probe_ledger_final.json"), encoding="utf-8"))\n'
     'tk = {t["bug"]: t for t in ledger["tickets"]}\n'
     'check(len(tk) == ledger["tickets_total"] == len(bugs_in),\n'
     '      f"只读查库要与入账映射一一对应：逐行 {len(tk)}/声明 {ledger[\'tickets_total\']} "\n'
     '      f"vs 映射 {len(bugs_in)}，差异 {sorted(set(tk) ^ set(bugs_in))}")\n'
     'pair_bad = sorted(b for b in set(tk) & set(bugs_in)\n'
     '                  if tk[b]["task_id"] != next(r["task_id"] for r in mapping if r["bug_id"] == b))\n'
     'check(not pair_bad, f"bug↔task_id 在库行与入账映射之间不一致：{pair_bad}")\n'
     'done = sorted(b for b, t in tk.items() if t["status"] == "已完成")\n'
     'open_t = sorted(b for b, t in tk.items() if t["status"] != "已完成")\n'
     'check(ledger["tickets_done"] == len(done),\n'
     '      f"tickets_done={ledger[\'tickets_done\']} 要等于逐行数出的 已完成 {len(done)} 张")\n'
     'check(len(open_t) <= 3,\n'
     '      f"转结未修的单最多 3 张（再多就不是「刻意留开」而是没收口）：{open_t}")\n'
     'bugs_md = open(os.path.join(ROOT, "memory", "bugs.md"), encoding="utf-8").read()\n'
     'parts = re.split(r"(?m)^## (BUG-\\d+)\\b", bugs_md)\n'
     'entries = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}\n'
     'check(sorted(entries) == sorted(bugs_in),\n'
     '      f"bugs.md 条目集合要与入账映射同集合：{sorted(entries)} vs {sorted(bugs_in)}")\n'
     'fixed = sorted(b for b, bd in entries.items() if "### FIXED(" in bd)\n'
     'check(fixed == done,\n'
     '      f"bugs.md 里带 ### FIXED 段的条目要等于库里 已完成 的单，差异 "\n'
     '      f"{sorted(set(fixed) ^ set(done))}")\n'
     'undone = sorted(bug_of(ln) for ln in trows if "入账未修" in ln)\n'
     'check(undone == open_t,\n'
     '      f"闭环表标「入账未修」的单要等于库里非 已完成 的单（{undone} vs {open_t}）")\n'
     'close = []\n'
     'for f in sorted(glob.glob(os.path.join(HERE, "close_fixes*.out.json"))):\n'
     '    close += json.load(open(f, encoding="utf-8"))\n'),

    # ---- verify_report4.py: verify-replies keyed on the real done set, no fake closure
    (V4,
     'check(verified >= {r["bug_id"] for r in mapping},\n'
     '      f"每张单都要有 verify→已完成 的原始回复，缺 "\n'
     '      f"{sorted({r[\'bug_id\'] for r in mapping} - verified)}")\n',
     'check(set(done) <= verified,\n'
     '      f"每张 已完成 的单都要有 verify→已完成 的原始回复，缺 {sorted(set(done) - verified)}")\n'
     'check(not (set(open_t) & verified),\n'
     '      f"库里未完成的单不许有 verify→已完成 回复（那是伪造闭环）：{sorted(set(open_t) & verified)}")\n'),

    # ---- verify_report4.py: keep the no-silent-failure rule AND require disclosure
    (V4,
     'errs = [e["tag"] for e in close if isinstance(e["result"], dict) and e["result"].get("__error__")]\n'
     'check(not errs, f"生命周期调用不许带 __error__：{errs}")\n',
     'errs = [(e["tag"], e["result"]["__error__"]) for e in close\n'
     '        if isinstance(e["result"], dict) and e["result"].get("__error__")]\n'
     'bad_bug = [t for t, _ in errs if re.match(r"BUG-\\d+:(claim|execute|submit|verify)$", t)]\n'
     'check(not bad_bug, f"修复单的四步生命周期不许带 __error__：{bad_bug}")\n'
     'hid = [f"{t}：{e.get(\'message\') or \'code=\' + str(e.get(\'code\'))}" for t, e in errs\n'
     '       if not (e.get("message") and e["message"] in text)]\n'
     'check(not hid, f"每一条被服务端拒绝的原始文案都要逐字出现在报告里（红线「失败原样上报」），"\n'
     '      f"缺 {hid}")\n'),
]


def main():
    srcs = {}
    for path, old, new in EDITS:
        srcs.setdefault(path, open(path, encoding="utf-8", newline="").read())
        n = srcs[path].count(old)
        if n != 1:
            sys.exit(f"[patch] 锚点匹配 {n} 次（要求恰 1 次）于 {path}：{old[:70]!r}")
        srcs[path] = srcs[path].replace(old, new)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for path, s in srcs.items():
            try:
                compile(s, path, "exec")
            except SyntaxWarning as w:
                sys.exit(f"[patch] {path} 编译告警：{w}")
            except SyntaxError as e:
                sys.exit(f"[patch] {path} 语法错误：{e}")
    for path, s in srcs.items():
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(s)
    print(f"[patch] applied {len(EDITS)} edits to {sorted(srcs)}")
    print("[patch] crlf_in=" + str({p: s.count('\r\n') for p, s in srcs.items()}))


if __name__ == "__main__":
    main()
