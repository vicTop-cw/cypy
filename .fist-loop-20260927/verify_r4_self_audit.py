"""R4-验证 的报告自证：渲染之前把 spec 的每道门禁、散文里每个占位、以及「件是否产自当前脚本」都解一遍。

与上一环的自证同口径，但加了三条本环特有的门（都是这一环真抓出来的失效形状）：

1. **件-脚本同源**：`verify_r4_X.json` 必须由同目录的 `verify_r4_X.py` 在其之后产出。
   本环的判据件跑完后又被修过 lint，所以这条门必须显式列出「已披露的例外 + 理由」，
   没披露的过期件一律拒；canary 用一对合成文件证明这个谓词真的会抓、也不误抓新鲜的。
2. **法覆盖**：环节计划 `spec_r4_verify.json` 的八条法，每条至少一道门禁；每条法声明的
   证据件必须出现在门禁清单里 ⇒ 收口预检要查的东西，报告里也必须有人认领
   （上一环栽在「清单口径漏一个目录」）。
3. **件自己的 refuse 必须为空**：渲染前逐件读 `refuse`，非空就不许出绿报告；
   并且每件时间戳必须落在本环窗口内（拿旧环的件当本轮证据是另一类谎）。

`report_kit.py` 在 refuse 非空时不会写报告文件，所以这里的目标是「一次渲染成功」。
解析器直接复用 report_kit 的 `walk/load_art/gate_ok`，避免「自证过了、渲染时另一套口径」。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import report_kit as RK  # noqa: E402

SPEC = HERE / "report_spec_r4_verify.json"
PLAN = HERE / "spec_r4_verify.json"
OUT = HERE / "verify_r4_self_audit.json"
WINDOW_START = "2026-09-27T23:40:14"
DRIVER_ALIAS = {"verify_r4_calllog_tally_final.json": "verify_r4_calllog_tally.py"}
SELF_EXEMPT = {OUT.name}
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def driver_for(name: str):
    if name in SELF_EXEMPT:
        return None
    return HERE / DRIVER_ALIAS.get(name, name[: -len(".json")] + ".py")


def newer(drv: Path, json_path: Path) -> bool:
    """判据本体：脚本 mtime 比件新 ⇒ 件不是当前脚本产的。"""
    return drv.stat().st_mtime > json_path.stat().st_mtime


def is_stale(json_rel: str) -> bool:
    drv = driver_for(Path(json_rel).name)
    if drv is None or not (ROOT / json_rel).exists():
        return False
    if not drv.exists():
        raise FileNotFoundError(f"件 {json_rel} 没有同名判据脚本")
    return newer(drv, ROOT / json_rel)


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    cache: dict = {}
    stale_disclosed = {d["artifact"]: d.get("reason", "") for d in spec.get("stale_ok", [])}

    state, body = RK.load_art(spec["fragment"], cache)
    if state != "TEXT" or not body:
        REFUSE.append(f"散文片段 {spec['fragment']} 不可用（{state}）")
        body = ""

    # ① 每道 gate 当场解一遍
    #    指向我这一份件的 gate 只能由渲染器判（自引用：我在跑的时候还没把自己写出来），
    #    这里记进 deferred，跑两次的数字才稳定。
    pass_labels, fail_msgs, deferred = [], [], []
    for g in spec["gates"]:
        if Path(g["artifact"]).name == OUT.name:
            deferred.append(g["label"])
            continue
        st, obj = RK.load_art(g["artifact"], cache)
        if st != "OK":
            fail_msgs.append(f'{g["label"]} 件不可用（{st}）：{g["artifact"]}')
            continue
        val, why = RK.walk(obj, g["path"])
        if why:
            fail_msgs.append(f'{g["label"]} 路径失败：{why}')
            continue
        ok, detail = RK.gate_ok(g, val)
        if ok:
            pass_labels.append(g["label"])
        else:
            fail_msgs.append(f'{g["label"]} 判据不成立：{detail}')
    if fail_msgs:
        REFUSE.append(f"{len(fail_msgs)} 道门禁未过：" + json.dumps(fail_msgs, ensure_ascii=False))

    labels = [g["label"] for g in spec["gates"]]
    check("门禁 label 不重复", sorted({x for x in labels if labels.count(x) > 1}), [],
          "按 label 计数")
    check("不许有 min=0 的恒真门", [g["label"] for g in spec["gates"] if g.get("min") == 0], [],
          "min=0 永远成立")
    check("每道门禁都自带可判谓词",
          [g["label"] for g in spec["gates"]
           if not ({"min", "equals"} & set(g) or "truthy" in g)], [],
          "缺 min/equals/truthy")

    # ② 散文占位全部解析；空值必须由一道 equals 打成空值的门禁作证
    refs = re.findall(r"\{\{([^{}]+)\}\}", body)
    bad_ph, empty_ph, self_pending = [], [], []
    for expr in refs:
        if "|" not in expr:
            bad_ph.append(f"占位不是 件|路径 形状：{expr}")
            continue
        rel, dotted = expr.split("|", 1)
        if Path(rel.strip()).name == OUT.name:
            # 指向我自己的占位一律不在自证里解：这一份件的第 N 次运行只能读到第 N-1 次的自己，
            # 那是自指振荡（而且会让「重跑一次格数就漂一格」永远收不了口）。
            # 渲染器读的是**最后一次**自证件，它当场解不出就是整份报告不出——判据仍承重。
            self_pending.append(f"{rel}|{dotted}")
            continue
        st, obj = RK.load_art(rel.strip(), cache)
        if st != "OK":
            bad_ph.append(f"{rel} 不可用（{st}）")
            continue
        val, why = RK.walk(obj, dotted)
        if why:
            bad_ph.append(f"{rel}|{dotted} 解析失败：{why}")
        elif isinstance(val, (list, dict, str)) and len(val) == 0:
            empty_ph.append(f"{Path(rel.strip()).name}|{dotted}")
    if bad_ph:
        REFUSE.append(f"{len(bad_ph)} 个散文占位解析不出：" + json.dumps(bad_ph, ensure_ascii=False))
    check("散文占位全部解析成功", bad_ph, [], "件在盘上且路径可解")
    zero_gates = {f"{Path(x['artifact']).name}|{x['path']}" for x in spec["gates"]
                  if isinstance(x.get("equals"), (list, dict, str)) and len(x["equals"]) == 0}
    unjustified = sorted(set(empty_ph) - zero_gates)
    check("空值占位必须由 equals 为空值的门禁作证", unjustified, [],
          f"空值 {len(set(empty_ph))} 个，无佐证 {len(unjustified)} 个")

    # ③ 散文点名的件都要在 artifacts 清单里；清单里的件都要在盘上
    #    （散文允许只写文件名，装配器会回落到 .fist-loop 目录 ⇒ 这里按 basename 对齐）
    used = sorted({e.split("|", 1)[0].strip() for e in refs if "|" in e})
    used_bases = {Path(u).name for u in used}
    listed_bases = {Path(a).name for a in spec["artifacts"]}
    check("散文点名的件都在 artifacts 清单里",
          sorted(used_bases - listed_bases), [], "按 basename 对齐")
    check("artifacts 清单里的件都在盘上",
          [a for a in spec["artifacts"]
           if not (ROOT / a).exists() and Path(a).name != OUT.name], [],
          "存在性（我这一份件在本轮第一次跑时本就还不存在）")
    check("artifacts 清单不许有重复",
          sorted({a for a in spec["artifacts"] if spec["artifacts"].count(a) > 1}), [],
          "重复声明=口径含糊")

    # ④ 件自己说的 refuse 必须为空；件的时间戳必须落在本环窗口内
    #    我这一份件不在此列：第 N 次跑读到的是第 N-1 次的自己，那是自指振荡而不是判据；
    #    自证件的 refuse 由渲染器（report_kit 的 ⑨-13..⑨-19）当场判。
    with_refuse, not_fresh = [], []
    for rel in spec["artifacts"]:
        if not rel.endswith(".json") or Path(rel).name == OUT.name:
            continue
        st, obj = RK.load_art(rel, cache)
        if st != "OK":
            continue
        r = obj.get("refuse")
        if r:
            with_refuse.append(f"{Path(rel).name} refuse 非空："
                               f"{json.dumps(r, ensure_ascii=False)[:200]}")
        at = obj.get("at_utc") or obj.get("queried_at_utc") or obj.get("started") or ""
        if Path(rel).name.startswith("verify_r4_") and at and at < WINDOW_START:
            not_fresh.append(f"{Path(rel).name} 时间戳 {at} 早于本环窗口 {WINDOW_START}")
    if with_refuse:
        REFUSE.append(f"{len(with_refuse)} 份判据件自带拒绝："
                      + json.dumps(with_refuse, ensure_ascii=False))
    check("被引用的件不许带 refuse", with_refuse, [], "件里非空=门禁不绿")
    check("本环件的时间戳不许早于环节窗口", not_fresh, [], "旧件当本轮证据")

    # ⑤ 件-脚本同源（例外必须披露理由）
    undisclosed, disclosed = [], []
    for rel in spec["artifacts"]:
        name = Path(rel).name
        if not name.startswith("verify_r4_") or not name.endswith(".json"):
            continue
        if not (ROOT / rel).exists():
            continue
        drv = driver_for(name)
        if drv is not None and not drv.exists():
            undisclosed.append(f"{name} 找不到同名判据脚本（件是谁产的？）")
            continue
        if is_stale(rel):
            if rel in stale_disclosed and stale_disclosed[rel]:
                disclosed.append({"artifact": rel, "reason": stale_disclosed[rel]})
            else:
                undisclosed.append(f"{name} 的脚本比件新且未披露 ⇒ 件不是当前脚本产的")
    fake = [k for k in stale_disclosed if not is_stale(k)]
    if fake:
        REFUSE.append(f"披露了其实没过期的件（把豁免当装饰）：{fake}")
    if undisclosed:
        REFUSE.append(f"{len(undisclosed)} 份件与脚本不同源："
                      + json.dumps(undisclosed, ensure_ascii=False))
    check("未披露的过期件为零", undisclosed, [], "披露位=报告里要逐条写的例外")

    # canary：合成一对「脚本比件新」的文件，谓词必须抓到；再配一对新鲜的证明不误抓
    tmp = HERE / "verify_r4_tmp" / "stale_canary"
    tmp.mkdir(parents=True, exist_ok=True)
    ca_j, ca_p = tmp / "verify_r4_canary_stale.json", tmp / "verify_r4_canary_stale.py"
    fr_j, fr_p = tmp / "verify_r4_canary_fresh.json", tmp / "verify_r4_canary_fresh.py"
    fr_p.write_text("x = 1\n", encoding="utf-8", newline="\n")
    fr_j.write_text('{"refuse": []}\n', encoding="utf-8", newline="\n")
    ca_j.write_text('{"refuse": []}\n', encoding="utf-8", newline="\n")
    now = ca_j.stat().st_mtime - 5
    os.utime(ca_j, (now, now))
    ca_p.write_text("x = 1\n", encoding="utf-8", newline="\n")
    check("canary：过期件必须被抓到", newer(ca_p, ca_j), True,
          f"py={ca_p.stat().st_mtime_ns} json={ca_j.stat().st_mtime_ns}")
    check("canary 不误抓：刚写出的件不许被判过期", newer(fr_p, fr_j), False,
          f"py={fr_p.stat().st_mtime_ns} json={fr_j.stat().st_mtime_ns}")
    for p in (ca_j, ca_p, fr_j, fr_p):
        p.unlink(missing_ok=True)
    tmp.rmdir()
    check("合成违例目录清干净", sorted(x.name for x in (HERE / "verify_r4_tmp").glob("*canary*")),
          [], "残留=下一轮把它当真件")

    # ⑥ 法覆盖：八条法每条有门禁，法声明的证据件都被门禁认领，needle 真在件里
    laws = plan["laws"]
    gate_art_bases = {Path(g["artifact"]).name for g in spec["gates"]}
    by_law = {i: [g["label"] for g in spec["gates"]
                  if g["label"].startswith(chr(0x2460 + i - 1))] for i in range(1, len(laws) + 1)}
    check("每条法都至少一道门禁", [i for i, v in by_law.items() if not v], [],
          json.dumps({k: len(v) for k, v in by_law.items()}))
    unclaimed = [f"law{i}:{Path(rel).name}" for i, law in enumerate(laws, 1)
                 for rel, _n, _m in law["artifacts"] if Path(rel).name not in gate_art_bases]
    check("法声明的每件证据都有门禁认领（预检查的=报告认的）", sorted(set(unclaimed)), [],
          "按 basename 对齐")
    missing_needle = [f"{Path(rel).name}|{ndl}" for law in laws
                      for rel, ndl, _m in law["artifacts"]
                      if RK.load_art(rel, cache)[0] == "OK"
                      and ndl not in json.dumps(RK.load_art(rel, cache)[1], ensure_ascii=False)]
    check("法声明的 needle 必须真在件里", sorted(set(missing_needle)), [],
          "件内 JSON 全文搜")

    # ⑦ §十 声明条数 == 正文条数
    sec = re.search(r"## 十、本环我自己的失效（(\d+) 条[^\n]*\n([\s\S]*?)(?=\n## 十一、)", body)
    declared = int(sec.group(1)) if sec else -1
    actual = len(re.findall(r"^\d+\. ", sec.group(2), re.M)) if sec else -1
    check("§十 标题声明条数 == 正文编号条数", actual, declared,
          sec.group(0).splitlines()[0] if sec else "§十 缺失")

    # ⑧ 不动点：收口 spec 的根交付物正文引用了「自证格数」，而这几道门禁里就有指向收口 spec 的
    #    ⇒ 两者互为输入，顺序必然是 audit → close_spec → audit。这里把收口 spec 引用的那组数与
    #    我这一次实测逐格对上；对不上就是「正文交出去的是旧态的数」（上一环栽在条数随评定态漂）。
    FKEYS = ["gates_pass", "gates_total", "placeholders_total", "stale_artifacts_len"]
    close_p = HERE / "close_r4_verify.json"
    fp = {"close_spec": close_p.name, "keys": FKEYS, "mismatch": [], "converged": False,
          "embedded": {}, "actual": {}, "note": ""}
    if not close_p.exists():
        REFUSE.append("收口 spec 还没生成（close_r4_verify.json 缺件）⇒ 不动点无从比对")
    else:
        cdoc = json.loads(close_p.read_text(encoding="utf-8"))
        emb = cdoc.get("embedded_self_audit") or {}
        miss = [k for k in FKEYS if k not in emb]
        if miss:
            REFUSE.append(f"收口 spec 没带自证引用位（embedded_self_audit 缺 {miss}）")
        here_now = {"gates_pass": len(pass_labels), "gates_total": len(spec["gates"]),
                    "placeholders_total": len(refs), "stale_artifacts_len": len(disclosed)}
        fp["embedded"], fp["actual"] = emb, here_now
        fp["mismatch"] = [f"{k}: 收口 spec 引用 {emb.get(k)} ≠ 本次实测 {here_now[k]}"
                          for k in FKEYS if emb.get(k) != here_now[k]]
        # canary：引用漂一格必须被抓到；逐格相同不得被抓（否则这个门恒绿）
        fake = dict(emb)
        fake["gates_pass"] = emb.get("gates_pass", 0) - 1
        drift = [k for k in FKEYS if fake.get(k) != here_now[k]]
        if "gates_pass" not in drift:
            REFUSE.append("canary 失效：引用漂了一格也没被抓 ⇒ 不动点比对是恒绿的")
        fp["canary_drift_caught"] = "gates_pass" in drift
        fp["converged"] = not fp["mismatch"] and not miss
        fp["note"] = ("不动点已推到：收口 spec 引用的格数与其后一次自证实测逐格相同"
                      if fp["converged"] else "未收敛（预期：pass1/pass2 就是红的，靠再跑一次收口 spec 收敛）")
        if fp["mismatch"]:
            REFUSE.append("引用漂了（收口正文用的是旧态的格数）："
                          + json.dumps(fp["mismatch"], ensure_ascii=False))

    refuse = sorted(set(REFUSE)) + [
        f"自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:240]}）"
        for c in CHECKS if not c["ok"]]
    doc = {"started": started, "spec": SPEC.name, "report_name": spec["name"],
           "window_start_utc": WINDOW_START,
           "gates_total": len(spec["gates"]), "gates_pass": len(pass_labels),
           "gates_self_deferred": deferred,
           "gates_fail": fail_msgs,
           "gates_by_law": {k: len(v) for k, v in by_law.items()},
           "artifacts_declared": len(spec["artifacts"]),
           "section10_items": {"declared": declared, "actual": actual},
           "placeholders_total": len(refs), "placeholders_bad": bad_ph,
           "placeholders_self_pending_first_run": self_pending,
           "placeholders_empty": sorted(set(empty_ph)),
           "stale_artifacts": disclosed, "stale_canary_caught": True,
           "fixpoint": fp,
           "body": spec["fragment"], "self_checks": CHECKS, "refuse": refuse,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse,
                      "gates": f"{len(pass_labels)}/{len(spec['gates'])}",
                      "placeholders": f"{len(refs) - len(bad_ph)}/{len(refs)}",
                      "gates_by_law": doc["gates_by_law"],
                      "empty_placeholders": doc["placeholders_empty"],
                      "fixpoint": {"converged": fp["converged"],
                                   "mismatch": fp["mismatch"],
                                   "embedded": fp["embedded"], "actual": fp["actual"]},
                      "stale_artifacts": [s["artifact"] for s in disclosed]},
                     ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
