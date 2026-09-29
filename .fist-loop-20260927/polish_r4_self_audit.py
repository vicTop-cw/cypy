"""R4-打磨 的报告自证：渲染之前把 spec 的每道门禁、散文里每个占位、件-脚本同源与 needle 口径都解一遍。

与 R4-验证 同构，但本环加了三条（都是这一环现场抓出来的失效形状）：

1. **needle 口径升级**：上一环的判据是「needle 作为子串出现在件的全文里」。本环实测发现
   `control` 命中的是件里 `SYNTAX/15-control-flow.md` 这个**文件名**，`queue` 命中的是
   `queue_frozen_edit` 的前缀——子串口径会把这种假命中放过去，收口预检于是「过」在
   根本没测到的东西上。这里改成「needle 必须是被引件里的真键名」，并配 canary 证明
   旧口径确实放过 `control`、新口径确实拒掉它。
2. **docs/tests 是白名单而不是「必须为空」**：打磨环允许改文档与加测试，
   沿用上一环的「三栏全空」会让这条门恒红或恒绿，取决于哪一栏被读错。
3. **件-脚本同源 + 时间戳新鲜度**：本环件必须由同名脚本产出且脚本不比件新，
   时间戳不许早于环节起点（拿旧环件当本轮证据是另一类谎）。

`report_kit.py` 在 refuse 非空时不写报告，所以目标是「一次渲染成功」。
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

SPEC = HERE / "report_spec_r4_polish.json"
PLAN = HERE / "spec_r4_polish.json"
OUT = HERE / "polish_r4_self_audit.json"
WINDOW_START = "2026-09-28T01:41:16"
DRIVER_ALIAS = {"close_r4_polish.json": "polish_r4_close_spec.py"}
TRACKED_PREFIX = "polish_r4_"
TRACKED_EXTRA = {"close_r4_polish.json"}
TESTS_ALLOW = {"tests/test_loop_20260927_polish_r4.py"}
DOCS_ALLOW = {"docs/USAGE.md", "docs/APPENDIX_C_DEVIATIONS.md"}
NEEDLE_CANARY_ART = ".fist-loop-20260927/polish_r4_docs.json"
NEEDLE_CANARY = "control"
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def tracked(name: str) -> bool:
    return name.startswith(TRACKED_PREFIX) or name in TRACKED_EXTRA


def driver_for(name: str):
    if name == OUT.name:
        return None
    return HERE / DRIVER_ALIAS.get(name, name[: -len(".json")] + ".py")


def newer(drv: Path, json_path: Path) -> bool:
    return drv.stat().st_mtime > json_path.stat().st_mtime


def is_stale(json_rel: str) -> bool:
    drv = driver_for(Path(json_rel).name)
    if drv is None or not (ROOT / json_rel).exists():
        return False
    if not drv.exists():
        raise FileNotFoundError(f"件 {json_rel} 没有同名判据脚本")
    return newer(drv, ROOT / json_rel)


def key_names(obj, acc: set) -> set:
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            key_names(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            key_names(v, acc)
    return acc


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

    # ① 每道 gate 当场解一遍；指向我这份件的 gate 只能由渲染器判（自引用），记进 deferred。
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
        REFUSE.append(f"{len(fail_msgs)} 道门禁未过："
                      + json.dumps(fail_msgs, ensure_ascii=False))

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
        REFUSE.append(f"{len(bad_ph)} 个散文占位解析不出："
                      + json.dumps(bad_ph, ensure_ascii=False))
    check("散文占位全部解析成功", bad_ph, [], "件在盘上且路径可解")
    zero_gates = {f"{Path(x['artifact']).name}|{x['path']}" for x in spec["gates"]
                  if isinstance(x.get("equals"), (list, dict, str)) and len(x["equals"]) == 0}
    unjustified = sorted(set(empty_ph) - zero_gates)
    check("空值占位必须由 equals 为空值的门禁作证", unjustified, [],
          f"空值 {len(set(empty_ph))} 个，无佐证 {len(unjustified)} 个")

    # ③ 散文点名的件都要在 artifacts 清单里；清单里的件都要在盘上
    used = sorted({e.split("|", 1)[0].strip() for e in refs if "|" in e})
    used_bases = {Path(u).name for u in used}
    listed_bases = {Path(a).name for a in spec["artifacts"]}
    check("散文点名的件都在 artifacts 清单里", sorted(used_bases - listed_bases), [],
          "按 basename 对齐")
    check("artifacts 清单里的件都在盘上",
          [a for a in spec["artifacts"]
           if not (ROOT / a).exists() and Path(a).name != OUT.name], [],
          "存在性（我这一份件在本轮第一次跑时本就还不存在）")
    check("artifacts 清单不许有重复",
          sorted({a for a in spec["artifacts"] if spec["artifacts"].count(a) > 1}), [],
          "重复声明=口径含糊")

    # ④ 件自己的 refuse 必须为空；时间戳必须落在本环窗口内
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
        if tracked(Path(rel).name) and at and at < WINDOW_START:
            not_fresh.append(f"{Path(rel).name} 时间戳 {at} 早于本环窗口 {WINDOW_START}")
    if with_refuse:
        REFUSE.append(f"{len(with_refuse)} 份判据件自带拒绝："
                      + json.dumps(with_refuse, ensure_ascii=False))
    check("被引用的件不许带 refuse", with_refuse, [], "件里非空=门禁不绿")
    check("本环件的时间戳不许早于环节窗口", not_fresh, [], "旧件当本轮证据")

    # ⑤ 件-脚本同源（例外必须在 spec 的 stale_ok 里披露理由）
    undisclosed, disclosed = [], []
    for rel in spec["artifacts"]:
        name = Path(rel).name
        if not tracked(name) or not name.endswith(".json") or not (ROOT / rel).exists():
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

    tmp = HERE / "polish_r4_tmp" / "stale_canary"
    tmp.mkdir(parents=True, exist_ok=True)
    ca_j, ca_p = tmp / "polish_r4_canary_stale.json", tmp / "polish_r4_canary_stale.py"
    fr_j, fr_p = tmp / "polish_r4_canary_fresh.json", tmp / "polish_r4_canary_fresh.py"
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
    check("合成违例目录清干净", sorted(x.name for x in (HERE / "polish_r4_tmp").glob("*canary*")),
          [], "残留=下一轮把它当真件")

    # ⑥ 法覆盖 + needle 的**严口径**：必须是被引件里的真键名，不接受值里的子串命中
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
    strict_bad, loose_only = [], []
    for i, law in enumerate(laws, 1):
        for rel, ndl, _m in law["artifacts"]:
            st, obj = RK.load_art(rel, cache)
            if st != "OK":
                strict_bad.append(f"law{i} {rel} 不可用（{st}）")
                continue
            keys = key_names(obj, set())
            if ndl not in keys:
                strict_bad.append(f"law{i} needle {ndl} 不是 {Path(rel).name} 里的真键名"
                                  f"（旧子串口径会不会放过：{ndl in json.dumps(obj, ensure_ascii=False)}）")
            elif ndl not in json.dumps(obj, ensure_ascii=False):
                loose_only.append(f"law{i} {ndl}")
    check("needle 严口径违例为零", strict_bad, [], "必须是被引件里的真键名")
    if strict_bad:
        REFUSE.append(f"{len(strict_bad)} 个 needle 通不过严口径："
                      + json.dumps(strict_bad, ensure_ascii=False))

    # needle 口径的 canary：旧规则必须确实放过 control，新规则必须确实拒掉它
    st_c, obj_c = RK.load_art(NEEDLE_CANARY_ART, cache)
    ok_c = st_c == "OK" and isinstance(obj_c, dict)
    keys_c = key_names(obj_c, set()) if ok_c else set()
    text_c = (ROOT / NEEDLE_CANARY_ART).read_text(encoding="utf-8") if ok_c else ""
    fz = (obj_c.get("frozen_sha") or {}) if ok_c else {}
    hit_is_filename = any(NEEDLE_CANARY in str(k) or NEEDLE_CANARY in str(v)
                          for k, v in fz.items())
    canary = {"substring_rule_would_pass_control": NEEDLE_CANARY in text_c,
              "strict_rule_rejects_control": NEEDLE_CANARY not in keys_c,
              "control_hit_is_a_filename_inside_frozen_sha": hit_is_filename}
    check("canary：旧子串口径确实会放过 control（否则升级口径没有代价可谈）",
          canary["substring_rule_would_pass_control"], True, text_c.count(NEEDLE_CANARY))
    check("canary：严口径必须拒掉 control", canary["strict_rule_rejects_control"], True,
          f"control 在键名集里={NEEDLE_CANARY in keys_c}")
    if not (canary["substring_rule_would_pass_control"]
            and canary["strict_rule_rejects_control"]):
        REFUSE.append("needle 口径的 canary 不成立：" + json.dumps(canary, ensure_ascii=False))

    # ⑦ 打磨环的白名单半径（不能沿用上一环的「三栏全空」）
    bs_p = ROOT / ".fist-loop-20260927/polish_r4_baselines.json"
    if bs_p.exists():
        bs = json.loads(bs_p.read_text(encoding="utf-8"))
        rad = bs["radius"]
        check("半径：产品码必须为空", sorted(rad["product"]), [], "本环不改语义")
        check("半径：冻结面必须为空", sorted(rad["frozen"]), [], "冻结面交人工")
        check("半径：tests 只许白名单内的新锁",
              sorted(set(rad["tests"]) - TESTS_ALLOW), [], f"实测 {rad['tests']}")
        check("半径：docs 只许白名单内的改写与补注",
              sorted(set(rad["docs"]) - DOCS_ALLOW), [], f"实测 {rad['docs']}")
        wl_bad = (sorted(set(rad["tests"]) - TESTS_ALLOW)
                  + sorted(set(rad["docs"]) - DOCS_ALLOW) + sorted(rad["product"])
                  + sorted(rad["frozen"]))
        if wl_bad:
            REFUSE.append("白名单半径违例：" + json.dumps(wl_bad, ensure_ascii=False))
    else:
        REFUSE.append("基线件还没落盘（白名单半径无从复核）")

    # ⑧ §十 声明条数 == 正文条数
    sec = re.search(r"## 十、本环我自己的失效（(\d+) 条[^\n]*\n([\s\S]*?)(?=\n## 十一、)", body)
    declared = int(sec.group(1)) if sec else -1
    actual = len(re.findall(r"^\d+\. ", sec.group(2), re.M)) if sec else -1
    check("§十 标题声明条数 == 正文编号条数", actual, declared,
          sec.group(0).splitlines()[0] if sec else "§十 缺失")

    # ⑨ 不动点：收口 spec 正文引用了本件的格数，而本件有门禁读收口 spec
    FKEYS = ["gates_pass", "gates_total", "placeholders_total", "stale_artifacts_len"]
    close_p = HERE / "close_r4_polish.json"
    fp = {"close_spec": close_p.name, "keys": FKEYS, "mismatch": [], "converged": False,
          "embedded": {}, "actual": {}, "note": ""}
    if not close_p.exists():
        REFUSE.append("收口 spec 还没生成（close_r4_polish.json 缺件）⇒ 不动点无从比对")
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
        drift_fake = dict(emb)
        drift_fake["gates_pass"] = emb.get("gates_pass", 0) - 1
        drift = [k for k in FKEYS if drift_fake.get(k) != here_now[k]]
        if "gates_pass" not in drift:
            REFUSE.append("canary 失效：引用漂了一格也没被抓 ⇒ 不动点比对是恒绿的")
        fp["canary_drift_caught"] = "gates_pass" in drift
        fp["converged"] = not fp["mismatch"] and not miss
        fp["note"] = ("不动点已推到：收口 spec 引用的格数与其后一次自证实测逐格相同"
                      if fp["converged"] else "未收敛（预期 pass1 红，靠再跑一次链收敛）")
        if fp["mismatch"]:
            REFUSE.append("引用漂了（收口正文用的是旧态的格数）："
                          + json.dumps(fp["mismatch"], ensure_ascii=False))

    refuse = sorted(set(REFUSE)) + [
        f"自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:240]}）"
        for c in CHECKS if not c["ok"]]
    doc = {"started": started, "spec": SPEC.name, "report_name": spec["name"],
           "window_start_utc": WINDOW_START,
           "gates_total": len(spec["gates"]), "gates_pass": len(pass_labels),
           "gates_self_deferred": deferred, "gates_fail": fail_msgs,
           "gates_by_law": {k: len(v) for k, v in by_law.items()},
           "artifacts_declared": len(spec["artifacts"]),
           "artifacts_with_refuse": with_refuse,
           "stale_timestamps": not_fresh,
           "section10_items": {"declared": declared, "actual": actual},
           "placeholders_total": len(refs), "placeholders_bad": bad_ph,
           "placeholders_self_pending_first_run": self_pending,
           "placeholders_empty": sorted(set(empty_ph)),
           "placeholders_empty_unjustified": unjustified,
           "needle_strict_violations": strict_bad,
           "needle_loose_only_hits": loose_only,
           "needle_canary": canary,
           "needle_rule": "needle 必须是被引件里的真键名；旧口径（值里含子串）会放过文件名与前缀命中",
           "stale_undisclosed": undisclosed,
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
                      "needle": {"violations": strict_bad, "canary": canary},
                      "fixpoint": {"converged": fp["converged"], "mismatch": fp["mismatch"],
                                   "embedded": fp["embedded"], "actual": fp["actual"]},
                      "stale_artifacts": [s["artifact"] for s in disclosed]},
                     ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
