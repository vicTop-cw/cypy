#!/usr/bin/env python3
"""把 BUG-48 的 FIXED 段追加进 `memory/bugs.md`：段内数字全部从证据件反解。

三条纪律（沿用上两环）：
- 幂等守卫：同标记段已存在 ⇒ 拒绝，不重复追加；
- 任一件 `refuse != []` / 缺件 / 是 dry-run 产物 ⇒ 整段不写（账本写出去收不回）；
- 还有一条本环新增的：**原话必须先被逐字引用再反驳**——反驳不了就不配写 FIXED。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LOOP = ROOT / ".fist-loop-20260927"
LEDGER = ROOT / "memory" / "bugs.md"
NOW = "2026-09-27T11:55:00Z"
ROOT_TASK = "T0r61"
MARKER = f"### FIXED(推进=已完成) — {NOW} 追加留档（2026-09-27 R2-推进(循环轮)，本条目正文与标题行 `OPEN` 一字未改）"
REPORT = sys.argv[1] if len(sys.argv) > 1 else "memory/reviews/20260927.19.55.00.md"
PHRASE = "无任何重编译产物与事件日志"


def load(rel: str) -> dict:
    p = LOOP / rel
    if not p.exists():
        raise SystemExit(json.dumps({"refuse": [f"证据件缺失：{rel}"]}, ensure_ascii=False))
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    refuse: list = []
    before = load("advance_r2_watch_probe_before.json")
    after = load("advance_r2_watch_probe.json")
    race = load("advance_r2_race_probe.json")
    wiring = load("advance_r2_wiring.json")
    base = load("advance_r2_baselines.json")
    lint = load("advance_r2_lint.json")
    bug54 = load("advance_r2_bug54.json")
    for name, doc in (("before", before), ("after", after), ("race", race), ("wiring", wiring),
                      ("baselines", base), ("lint", lint), ("bug54", bug54)):
        if doc.get("refuse"):
            refuse.append(f"{name} 件 refuse 非空：{doc['refuse'][:2]}")
    if base["pytest"]["passed"] < base["pytest"]["floor"]:
        refuse.append("pytest 未达下限，不配写 FIXED")
    if not (base["suite"]["green"] and base["e2e"]["green"]):
        refuse.append("另两套体系不绿，不配写 FIXED")
    if before["grep"]["file_changed"] < 1 or before["outputs_in_out_dir"]:
        refuse.append("before 件的形状与本环主张不符（事件日志/空产物目录），反驳链断了")
    if not after["outputs_in_out_dir"]:
        refuse.append("after 件 -o 目录仍为空 ⇒ 主张未成立")
    if not (race.get("lock_off_red_rounds") and wiring.get("cli_wiring", {}).get("on_reload_callable")):
        refuse.append("并发对照或接线对照缺失")
    text = LEDGER.read_text(encoding="utf-8")
    already = MARKER in text
    if already:
        print("[ledger] 幂等守卫：本环 FIXED 段已在账上 ⇒ 不重复追加，只核验终态", file=sys.stderr)
    if refuse:
        print(json.dumps({"refuse": refuse, "written": False}, ensure_ascii=False))
        return 1
    if already:
        return emit(False)

    entry = re.search(r"^## BUG-48 .*$", text, flags=re.M)
    if not entry:
        print(json.dumps({"refuse": ["账本里找不到 ## BUG-48 标题行"], "written": False}, ensure_ascii=False))
        return 1

    g = after["grep"]
    gb = before["grep"]
    section = f"""{MARKER}
- 处置单：根 `{ROOT_TASK}`（ns `cypy-loop-20260927`）的 8 枝 16 叶全链带 `[omega:required]`，逐叶
  `output_validate` pass 后才 verify；报告：`{REPORT}`
- **原话先重测再反驳**（本条是这单的主要内容）：条目正文说『改动或新增被监控文件后 16s 内无任何
  重编译产物与事件日志』。同一夹具改码前实测（`.fist-loop-20260927/advance_r2_watch_probe_before.json`）：
  `[HotReload] File changed` {gb['file_changed']} 条、`Successfully reloaded` {gb['successfully_reloaded']} 次、
  `Failed to reload` {gb['failed_to_reload']} 次、`Traceback` {gb['traceback']} 次 ⇒ **事件日志与重编译都在发生**，
  这半句话是错的。真缺的是三件（下面逐件给判据），其中"产物"那半只成立在
  「`-o` 目录收不到」这个精确形状上：before 件 `outputs_in_out_dir` = `{before['outputs_in_out_dir']}`。
- 补全一 `-o 产物发布`：`cypyc/incremental/hot_reload.py` 新增 `artifact_dir` 与 `_publish_artifacts()`
  （把 `.pyx/.pyd` 从编译用临时目录复制进 -o；`.c` 中间产物按手册字面不算"编译文件"），
  `cypyc/cli.py::run_watch` 传 `artifact_dir=args.output`。调用面实测（`advance_r2_watch_probe.json`）：
  `-o` 目录得到 `{after['outputs_in_out_dir']}`。
  成对对照：不设 `artifact_dir` 时 `_publish_artifacts` 必须返回空且目录里什么都不出现
  （`test_publish_artifacts_is_noop_without_artifact_dir` + `test_real_toolchain_publishes_compiled_artifacts` 第二段）
  ⇒ 库路径默认行为没被这次改动带偏。
- 补全二 `on_reload 接线`：run_watch 内定义 `report_reload()` 打批次结论，哨件
  `advance_r2_wiring.json` 逐项核对实参（`on_reload_callable={wiring['cli_wiring']['on_reload_callable']}`、
  `debounce_delay={wiring['cli_wiring']['debounce_delay']}`、`artifact_dir` 与 -o 同值），并**真调一次**回调
  ⇒ 实测 stdout 出现 `{g['watch_published']}` 行 `[Watch] Published N artifact(s) …`。
- 补全三 `--debounce`：`HotReloadEngine.start()` 新增 `debounce_delay` 透传给监控器
  （实测显式 1.23 ⇒ 监控器存 `{wiring['monitor_debounce_measured']['explicit']}`；不传 ⇒ 仍
  `{wiring['monitor_debounce_measured']['default']}`）。此前 CLI 打印用户输入的时延、引擎却写死 0.5。
- **附带发现并当场定性**：探针有一跑 `-o` 为空、日志出现 `cl.exe failed with exit code 1` /
  `can't copy 'build\\lib.win-amd64-cpython-313…'`。同夹具跑开关两态
  （`advance_r2_race_probe.json`）：去掉引擎锁 3/3 轮出红且成因均为编译类
  （红轮 `{race['lock_off_red_rounds']}`），加锁 3/3 轮双线程全绿。
  ⇒ 成因是 setuptools 的**中间**产物落在进程 CWD 下共享的 `build/`，watchdog 一次保存发多个事件
  即并发互踩。本环把锁加在**类**上（`HotReloadEngine._compile_lock = threading.RLock()`，
   锁住的是进程共享的 `build/`，不是某个引擎实例；同进程内已足够），
  **跨进程那半边不修**：要动 `cypy_hook` 的中间目录策略（同时影响 import hook 与缓存命中）⇒
  入账 BUG-54（`{bug54['rpc_bug_id']}` / `{bug54['task_id']}`），关闭判据写明必须是两个子进程并发。
- 行为未变（同一时刻复算）：pytest `{base['pytest']['line']}`（下限 {base['pytest']['floor']} =
  上环 1894 + 本环 9 条锁，collected={base['pytest']['collected']}）；
  自研套件 `{base['suite']['line']}`；端到端 `{base['e2e']['line']}`；基准未重注册。
  作用域化 lint：亲笔 {lint['authored_lines_checked']} 行零违例（含必然违例自检
  `{lint['selftest']}`），存量违例只减不增。git 红线 HEAD `{base['git']['head']}`、暂存 {base['git']['staged']}。
- 手册同步：`docs/USAGE.md` 2.5 段补 `-o` 产物、两种批次结论行措辞、以及"临时目录编译再复制 +
  同进程串行编译"的说明——文档里每一句都在上面的实测里有对应物。
- **自曝**：锁与 `artifact_dir` 一开始只写在 `__init__` 里，被全量撞红一条老用例
  （`tests/test_polish_20260926.py::test_bug10_cache_update_parse_failure_warns` 用
  `HotReloadEngine.__new__` 绕过构造造引擎 ⇒ `AttributeError: '_compile_lock'`）。老测试不可改 ⇒
  提成类属性，并补第 9 条锁 `test_engine_attributes_survive_construction_without_init` 钉住这条构造路径。
- 不算证明（本环明确排除）：① "重载成功"不证明产物落到了用户指定的目录 ⇒ 靠 before/after 两件的
  `outputs_in_out_dir` 差集；② "源码里出现了 `on_reload=`"不证明回调真被调用 ⇒ 靠哨件真调一次并
  核对 stdout 行；③ "加了锁之后跑通了"不证明锁在承重 ⇒ 靠同一夹具的锁关对照必须出红；
  ④ "三套基线全绿"不证明跨进程安全 ⇒ BUG-54 因此不关闭。
"""

    if PHRASE not in section:
        print(json.dumps({"refuse": ["生成的 FIXED 段里没有逐字原话（多半是被折行打断）"],
                          "written": False}, ensure_ascii=False))
        return 1
    lines = text.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## BUG-48 "))
    nxt = next((i for i in range(start + 1, len(lines)) if re.match(r"^## BUG-\d+ ", lines[i])), len(lines))
    insert_at = nxt
    while insert_at > start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    new = "\n".join(lines[:insert_at] + [""] + section.rstrip("\n").split("\n") + lines[insert_at:])
    LEDGER.write_text(new, encoding="utf-8")
    return emit(True)


def emit(written: bool) -> int:
    """落盘后（或幂等复跑时）只按**账本终态**判定。

    原来这里查的是「引用次数 +1」，结果一段把原话折了行的引用照样写得进去、只是数不到
    （本轮实测 +0）——次数增量证明不了"逐字"。终态口径是：原话在账上恰好出现 2 次
    （条目正文 1 次 + FIXED 段逐字 1 次），且第 2 次必须落在 FIXED 段内。
    """
    back = LEDGER.read_text(encoding="utf-8")
    out = {
        "written": written,
        "marker_count": back.count(MARKER),
        "fixed_sections": len(re.findall(r"^### FIXED\(", back, flags=re.M)),
        "entries": len(re.findall(r"^## BUG-\d+ ", back, flags=re.M)),
        "phrase_total": back.count(PHRASE),
        "phrase_in_fixed_section": PHRASE in back[back.index(MARKER):],
        "refuse": [],
    }
    if out["marker_count"] != 1:
        out["refuse"].append(f"标记出现 {out['marker_count']} 次（要 1）")
    if out["phrase_total"] != 2:
        out["refuse"].append(
            f"原话应恰有 2 处（条目正文 + FIXED 段逐字引用），实测 {out['phrase_total']} 处"
            "——引用被折行打断时也是这个形状"
        )
    if not out["phrase_in_fixed_section"]:
        out["refuse"].append("FIXED 段里找不到逐字原话")
    (LOOP / "advance_r2_ledger.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not out["refuse"] else 1


if __name__ == "__main__":
    sys.exit(main())
