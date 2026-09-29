#!/usr/bin/env python3
"""R3-寻虫：把 `hunt_r3_confirm.json` 里 CONFIRMED 的候选逐条入账（BUG-55 起）。

三条硬约束（都是前几环踩过来的）：
1. **数字不手打**：每条 detail 的 pos/ctl 观测值从证据件反解，本脚本里没有一处字面量数字；
2. **幂等**：账本里已有同 summary ⇒ 该条跳过并在输出里点名（上一轮重跑非幂等脚本造出过双发单）；
3. **只入 CONFIRMED**：DESIGN（自己文本里写明未实现）与 REJECTED（被推翻）都不入账，
   但要在输出里逐条列名——"撤回了哪几条"和"入账了哪几条"同等重要。

复跑口径统一指向 `hunt_r3_repro.py <ID>`（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）。
v1 的 detail 里塞的是嵌套引号的 `python -c "..."`，在这个平台上根本跑不动——
寻虫单留给修复轮的第一件事就是"能一键复跑"，所以必须是一个真能执行的命令。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LEDGER = ROOT / "memory" / "bugs.md"
EVIDENCE = HERE / "hunt_r3_confirm.json"
OUT = HERE / "hunt_r3_filed.json"
NOW = lfist_lib.utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
# 上一版把手敲的钟点当 UTC 戳写进 RPC（我填 12:45:00Z，账本实际落盘 12:46:09Z）。
# 手敲的戳一定和写盘瞬间不一致 ⇒ 改成取当前 UTC，并让下面第 4 步的对照成为硬门。
REPORTER = "cypy-hunter"
REPRO_TMPL = "python -X utf8 .fist-loop-20260927/hunt_r3_repro.py {cid}"

META = {
    "C1": {
        "severity": "medium",
        "why": "泛型定义在转换阶段被静默丢弃：`GenericTransformer.generic_defs` 恒空 ⇒ "
               "任何依赖泛型注册的下游（类型约束、单态化）拿不到输入，而接口不报错。",
        "not_proof": "只说『文件里有 generic 关键字』不算；必须给出真解析出的节点带 generic_params "
                     "而收集结果为空，并配一条『属性叫 type_params 时确实被收集』的对照。",
    },
    "C3": {
        "severity": "medium",
        "why": "`cypyc transpile` 把 --check-only/--emit-ast/--generate-setup/--emit-cython 印给用户，"
               "但 run_transpile 一个都不读 ⇒ 用户以为做了静态检查/出了中间码，实际什么都没发生；"
               "真正读这四个旗标的是只能从不可达 else 分支进入的 run_default。",
        "not_proof": "只证明『旗标能解析成 args.xxx』不算（那是 argparse 的功劳）；必须证明 transpile 路径上"
                     "没有任何读取，且 --help 确实承诺过这四个旗标（调用面实测，不是读源码字面）。",
    },
    "C4": {
        "severity": "low",
        "why": "`cypy_bridge.union` 的 docstring/工厂函数示例用 Python 内建类型 `CUnion(int, float)`，"
               "而实现对它们调 `ctypes.sizeof` ⇒ 照文档抄一行就抛 `TypeError: this type has no size`。"
               "文档示例是这个模块对外唯一的用法说明。",
        "not_proof": "只说『文档写得不够清楚』不算；必须实证示例代码本身跑不通，"
                     "并配一条『换成 ctypes 类型即成功』的对照（证明坏在示例，不是整个 API）。",
    },
    "C5": {
        "severity": "medium",
        "why": "`memory.realloc` 签名 `-> int`、docstring 只说返回地址，却在 `size<=0` 分支先 free 再 "
               "`return None` ⇒ 调用方按 int 拿返回值做地址运算会拿到 None（且原内存已被释放）。"
               "同族入口 `malloc(0)` 走的是抛 MemoryError，说明这不是模块统一风格。",
        "not_proof": "『文档没写这个分支』只是措辞问题；要的是**注解与返回值互斥**（int 却给 None）"
                     "且同族入口行为不一致这两条同时成立。",
    },
    "C6": {
        "severity": "medium",
        "why": "`get_compilation_order` 把环内模块塞进 `set` 再 extend ⇒ 存在循环依赖时推荐编译序"
               "随进程字符串哈希种子变化（同一张图在不同 PYTHONHASHSEED 下给出不同顺序），"
               "破坏可重现构建；文档只承诺『跳过循环中的模块』，没承诺任意序。",
        "not_proof": "在同进程里改 `os.environ['PYTHONHASHSEED']` **测不出来**（字符串哈希在解释器启动时已定，"
                     "本环 v1 就这么假绿过一次）⇒ 必须是独立子进程各带一个种子；"
                     "还要配一条无环图给确定序的对照，否则分不清是产品 nondeterminism 还是夹具噪声。",
    },
    "C8": {
        "severity": "low",
        "why": "`build_block_checker` 模块 docstring 列的规则 2『指针语法只能在构建块内部使用』没有实现："
               "`_visit_DerefExpr`/`_visit_PointerType` 只留了一句『移除…限制』的注释，不 append 任何 error "
               "⇒ 函数体里裸用 `*int` 也过得了这道门。要么补实现，要么改文档口径。",
        "not_proof": "只说『注释写着移除』不算；必须实测块外指针语法 errors 为空，"
                     "且配一条『别的规则确实在报』的对照（否则整个检查器空转是另一码事）。"
                     "另：规则清单在**模块** docstring，读类 docstring 会读空（本环 v3 误判过一次）。",
    },
}


def detail_for(case: dict) -> str:
    pos, ctl = case["pos"], case["ctl"]
    meta = META[case["id"]]
    return "\n".join([
        f"主张：{case['claim']}",
        f"声明面（缺陷就是与它矛盾之处）：{case['declared']}",
        "",
        "现形判据(pos) 实测：" + json.dumps(pos["observed"], ensure_ascii=False, default=str),
        "  期望：" + pos["want"],
        "对照判据(ctl) 实测：" + json.dumps(ctl["observed"], ensure_ascii=False, default=str),
        "  期望：" + ctl["want"],
        "",
        f"为什么值得入账：{meta['why']}",
        "",
        "复跑（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）：" + REPRO_TMPL.format(cid=case["id"]),
        "整批复跑：python -X utf8 .fist-loop-20260927/hunt_r3_confirm.py"
        "（判据件 .fist-loop-20260927/hunt_r3_confirm.json）",
        "",
        f"不算证明：{meta['not_proof']}",
        "",
        "来历（待修复轮确认，我只给到调用面事实与形状）：见上面 file:line 与两条判据的实测输出。",
    ])


def main() -> int:
    refuse: list = []
    ev = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else {}
    if not ev:
        return print_and_refuse(["证据件缺失：hunt_r3_confirm.json 不在盘上"])
    if ev.get("refuse"):
        return print_and_refuse([f"证据件自身 refuse 非空：{ev['refuse']}"])
    by_id = {c["id"]: c for c in ev["cases"]}
    confirmed = [i for i in ev["confirmed"] if i in by_id]
    if sorted(confirmed) != sorted(META):
        return print_and_refuse([
            f"META 与 CONFIRMED 不齐套：meta_only={sorted(set(META) - set(confirmed))} "
            f"confirmed_only={sorted(set(confirmed) - set(META))}"
        ])
    text = LEDGER.read_text(encoding="utf-8")
    numbers_before = [int(n) for n in re.findall(r"^## BUG-(\d+) ", text, flags=re.M)]

    filed, skipped = [], []
    c = lfist_lib.Client(timeout=240)
    try:
        for cid in sorted(confirmed):
            case = by_id[cid]
            summary = case["claim"][:120]
            if summary in text:
                skipped.append({"id": cid, "reason": "同 summary 已在账上（幂等跳过）"})
                continue
            resp = c.call("report_bug", {
                "summary": summary,
                "detail": detail_for(case),
                "severity": META[cid]["severity"],
                "project_dir": ".",
                "reported_by": REPORTER,
                "publish_task": True,
                "now": NOW,
            })
            bug_id = resp.get("bug_id") or resp.get("id")
            row = {
                "id": cid,
                "rpc_bug_id": bug_id,
                "task_id": resp.get("task_id"),
                "severity": META[cid]["severity"],
                "ledger_path": resp.get("path"),
                "summary_on_disk": summary in LEDGER.read_text(encoding="utf-8"),
                "repro_cmd": REPRO_TMPL.format(cid=cid),
            }
            if not bug_id:
                refuse.append(f"{cid}：report_bug 没回 bug_id：{json.dumps(resp, ensure_ascii=False)[:200]}")
            if not row["summary_on_disk"]:
                refuse.append(f"{cid}：RPC 说入了账但 md 里搜不到该 summary")
            filed.append(row)
    finally:
        c.close()

    after = LEDGER.read_text(encoding="utf-8")
    numbers_after = [int(n) for n in re.findall(r"^## BUG-(\d+) ", after, flags=re.M)]
    out = {
        "now": NOW,
        "filed": filed,
        "skipped": skipped,
        "withdrawn": [{"id": x["id"], "verdict": x["verdict"]} for x in ev["cases"]
                      if x["verdict"] in ("DESIGN", "REJECTED", "UNSURE")],
        "entries_before": len(numbers_before),
        "entries_after": len(numbers_after),
        "new_numbers": sorted(set(numbers_after) - set(numbers_before)),
        "refuse": refuse,
    }
    stamps = re.findall(r"^## BUG-(\d+) \[([^\]]+)\]", after, flags=re.M)
    out["ledger_stamps"] = {f"BUG-{n}": s for n, s in stamps if n in {str(x).split("-")[-1] for x in out["new_numbers"]}}
    if len(out["ledger_stamps"]) != len(filed):
        out["refuse"].append(
            f"入账 {len(filed)} 条但只从账本反解出 {len(out['ledger_stamps'])} 个时间戳"
            "⇒ 号或标题行形状不对，戳无从核对")
    if len(out["new_numbers"]) != len(filed):
        out["refuse"].append(
            f"入账 {len(filed)} 条但账本号只新增 {len(out['new_numbers'])} 个（{out['new_numbers']}）"
            "⇒ 有单没落地或号被复用"
        )
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: out[k] for k in ("filed", "skipped", "withdrawn", "entries_before",
                                          "entries_after", "new_numbers", "refuse")}, ensure_ascii=False))
    return 1 if out["refuse"] else 0


def print_and_refuse(msgs):
    print(json.dumps({"refuse": msgs, "filed": []}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())
