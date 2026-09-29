"""给 BUG-130..133 追加 `### FIXED` 段（R11 收口腿，同轮确诊同轮修）。

三条纪律：
 · 标题行与条目正文一字不改（`OPEN` 也留着）—— 关闭只以追加段为准，服务端无关闭 API；
 · 段落戳用**写盘瞬间**的 UTC，不手敲钟点；
 · 可 `--refresh` 回收自己写的那一段（重复跑不会双写），并在收尾自证：抬头数不变、
   开口块少 4、FIXED 段多 4，任一条不符就回滚到入口快照。
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
MARK = "FIXED(R11 收口腿"

SECTIONS = {
    "130": """
### {mark} {ts}）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修在三处（同一件 `.fist-loop-20260929/run_r11_ring.py`）：
  ① 口径收敛成常量 `SPEC_KIND/CHECK_KIND/RESULT_KIND = "spec"/"check"/"result"`，五处
  `spec_rows(...)` 守卫全部改走常量（改前是 `"omega"`/`"omega_result"`，库里根本没有这两个值）；
  ② 开批门新增 `spec_kind_guard()`：对着活库读 `select distinct spec_type from specs`，
  本件用的三个值有任一缺失、或库里一行 specs 都没有 ⇒ 直接 refuse 收口并列出库里实有值。
  这是给"恒 0 针"配的基数门，不是装饰：把常量改成 `"omega"` 就会红；
  ③ `note()` 从两桶改三桶（幂等 / 真拒绝 / 良性重复），幂等回执单独计数并印进结论行
  （`idempotent=`），不再决定 rc。
- 复验（同树复跑，账的终态没动）：`logs/r11_ring_close_a3.out`（修前）
  `calls=105 refused=24 benign=0` → `logs/r11_ring_close_a4.out`（修后）
  `calls=21 refused=0 idempotent=0 benign=0 loop_ticks_ok=6 call_log_error_rows=0 rc=0`，
  两次都是 `root_status=已完成 rollup={{'已完成': 17}} non_closed=[] pending_leaves=0`。
- 限制：a3 的 24 条拒绝作为历史留在 `call_log`（不可改），`ring_r11_close.json` 已被 a4 原地覆写 ⇒
  a3 的读数只活在 `.out` 里；本轮报告 §6.4 点名了这次同名覆写。
""",
    "131": """
### {mark} {ts}）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：`run_r11_ring.py` 的收口自证改按 `call_log.ok=0` 取数（`call_log_error_rows`），
  并**同时**保留旧口径为 `call_log_error_rows_old_needle` 与它并印 ⇒ 两个读数一旦分叉就能当场看出来，
  而不是再信三次"0"。
- 两口径的差在本轮被实测钉住（`r11_loop_tick_fix.json` 的 `error_rows_two_needles`）：
  a3 窗口 `ok=0` 为 25 行，同窗口 `%__error__%` 为 0 行。
- 改判（不删历史报告，只在此作废自证句）：R9/R10/R11 三份报告里凡写过
  「`call_log` 0 错误行 / benign=0 即无幂等噪声」的句子，读数来源都是这把坏尺 ⇒ 一律作废，
  真实口径见本轮报告 §6.4。既往轮的**账**（任务状态、specs 行）没受影响，作废的只是那句自证。
- 复验：修后 a4 窗口两口径同为 0（该窗口确实无红），而 a3 窗口的 25/0 差值留作尺子的对照样本。
""",
    "132": """
### {mark} {ts}）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：新增 `.fist-loop-20260929/r11_loop_drive.py` —— **同一会话内** `loop_create` + 6×`loop_tick` +
  `loop_status`，回放的基线数从账上取（`loop_create_params()` 读上一笔成功的参数，查无即拒绝手填），
  `steps` 序列与账上登记值逐位比对，不一致直接 SystemExit；并接进 `run_r11_ring.py --stage close`
  的收口腿（`drive_loop()`，门表复用同一实现，不写第二份）。
- 两条成因分别取证（合起来才解释 33 条红）：
  ① 键名：`logs/r11_loopfix_a2.out` 的 `SHAPE_CONTROL` 逐字
  `{{"只传声明键": {{"环查无": 24, "成功": 24, "键名被拒": 0, "其它": 0}}, "含未声明键": {{"键名被拒": 10, "成功": 0, ...}}}}`
  ⇒ 注入未声明键 10/10 全拒、声明键栏 0 次键名拒绝（驱动侧统一带 `_omit_defaults` 退出键）；
  ② 进程内：换新 `FistClient`（会再 spawn 一个 serve）查同名环 ⇒ `loop not found: cypy-selfdrive-ring-r11`
  （`r11_loop_drive.json` 的 `cross_process_negative`），与 `loop_create` 自述的"进程内 LoopRegistry"一致。
- 复验：`logs/r11_loopdrive_a2.out` ⇒ `ticks_ok=6/6`，九格门全 true
  （`round_advanced` 0→1、`mode_sequence_matches_declared_steps` 逐位相同、
  `current_idx_progression` 1..5→0、`no_early_stop`、跨会话负控制成立）；
  负控制自检 `logs/r11_loopdrive_selftest_a1.out` ⇒ `cases=8 bad=[]`
  （round 不前进／少 tick／mode 打乱／服务端叫停／单次被拒／跨会话竟查得到／create 被拒／status 被拒
  各自把对应门翻红）。
- 限制（不遮挡本单关闭）：环状态是进程内的 ⇒ 服务端**没有**跨轮可审的环账，本报告"环已推进"只能指
  「同会话内 6 步走完且回执全绿」这一格；要跨轮审计得把 LoopRegistry 落库（FIST 侧，不属本仓改动面）。
""",
    "133": """
### {mark} {ts}）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：close 分支起手显式绑定 `root_id`；查无根单时**拒绝并落 refused 回执**
  （原因逐字含 ns、前缀、`parent_id=''` 三个口径），绝不静默新建一棵树去凑数。
- 负控制（真跑，不是读代码）：把 `ROOT_PREFIX` 换成账上必然查无的名字另存为
  `run_r11_ring_negctl.py`（与原文件只差 1 行）⇒ `logs/r11_ring_close_negctl_a1.out`
  逐字 `REFUSED (开批门) local | 账上查无根单 T0r999-不存在的根单前缀` +
  `CONCLUSION refused=1 stage=close gate_reasons=1`，rc=1 而不是 traceback；
  且该窗口 `call_log` 新增行数 0 ⇒ 拒绝发生在任何 RPC 之前，没有半途写账。
- 复验：修后 a3/a4 两次收口都在同一棵根上跑完（`root=T0r117`，`rollup={{'已完成': 17}}`）。
""",
}


def counts(text: str) -> dict:
    blocks = [b for b in re.split(r"(?m)^(?=## BUG-)", text) if b.startswith("## BUG-")]
    open_blocks = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)]
    return {"headers": len(blocks), "open": len(open_blocks),
            "fixed": len(re.findall(r"(?m)^### FIXED", text)),
            "mine": text.count(MARK)}


def main() -> int:
    refresh = "--refresh" in sys.argv
    src = LEDGER.read_text(encoding="utf-8")
    before = counts(src)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, touched = src, []
    for bid, body in SECTIONS.items():
        seg = body.format(mark=MARK.rstrip("（"), ts=ts)
        pat = re.compile(r"(?ms)(?<=\n)### " + re.escape(MARK) + r".*?(?=\n## BUG-|\Z)")
        head = re.search(r"(?ms)^## BUG-" + bid + r" .*?(?=\n## BUG-|\Z)", out)
        if not head:
            raise SystemExit(f"账上查无 BUG-{bid} ⇒ 先取号再写台账，本件拒绝凭空插段")
        block = head.group(0)
        already = pat.search(block + "\n")
        if already and not refresh:
            print(f"SKIP BUG-{bid}：本件那段已在账上（要覆盖用 --refresh）")
            continue
        new_block = block.rstrip("\n") + "\n" + seg.rstrip("\n") + "\n"
        if already:
            # 回收自己那段：按匹配区间替换，并钉住"被替换掉的确实是我的段"，否则宁可不动
            removed = block[already.start():already.end()]
            if MARK not in removed:
                raise SystemExit(f"BUG-{bid} 要回收的区段里不含本件标记 ⇒ 停手，不动账")
            new_block = block[:already.start()] + seg.lstrip("\n").rstrip("\n") + "\n" + block[already.end():]
        out = out.replace(block, new_block, 1)
        touched.append(bid)
    if not touched:
        print("CONCLUSION touched=0（全部已在账，幂等）")
        return 0
    backup = LEDGER.with_name("bugs.md.pre_r11_ledger_bugs")
    backup.write_text(src, encoding="utf-8", newline="\n")
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    after = counts(tmp.read_text(encoding="utf-8"))
    after_text = tmp.read_text(encoding="utf-8")
    preserved = []
    for bid in touched:
        old_block = re.search(r"(?ms)^## BUG-" + bid + r" .*?(?=\n## BUG-|\Z)", src).group(0)
        keep = [ln for ln in old_block.splitlines() if ln.startswith("## BUG-") or ln.startswith("- summary:")]
        preserved.append(all(k in after_text for k in keep))
    ok = (after["headers"] == before["headers"] and after["open"] == before["open"] - len(touched)
          and after["fixed"] == before["fixed"] + len(touched) and after["mine"] == len(touched)
          and all(preserved))
    print("BEFORE", before, "AFTER", after, "TOUCHED", touched, "SUMMARY_KEPT", preserved)
    if not ok:
        raise SystemExit("自证不符（抬头数/开口数/FIXED 段数/本件段数/标题与 summary 逐字留存）⇒ 不落盘，"
                         "tmp 与备份留在 .fist-loop-20260929/ 待查")
    tmp.replace(LEDGER)
    print(f"CONCLUSION touched={len(touched)} ids={','.join('BUG-' + i for i in touched)} "
          f"headers={after['headers']} open={after['open']} fixed={after['fixed']} refresh={refresh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
