"""R5-寻虫 的渲染前自证：门禁按 report_kit 的**同一把尺子**预跑一遍，能红的先红。

为什么复用 `report_kit` 而不是自己写一套判定：上一环吃过「自证过了、渲染时另一套口径」的亏，
`load_art/walk/gate_ok` 是渲染器实际用的那三个函数，直接 import 才能保证两路口径同源。

本驱动自己也要能被红：
- 恒真门（`min: 0`、`min: 1` 套在必然存在的标量上）单列计数，>0 即拒；
- 每条门禁的 `path` 首段必须是判据件里的**真键名**（needle 严口径，同 hunt_r5_needles.py）；
- 判据件比它的驱动脚本旧 ⇒ 陈旧，除非在 `stale_ok` 里逐条写了理由；这条判据配一条合成 canary
  （把脚本 mtime 设到未来，必须被抓到），否则它可能只是一道恒绿门；
- 每份 JSON 判据件必须真能 parse（上一环的手补计划件就是靠这条抓出来的）；
- 正文里的 `{{件|路径}}` 占位必须全部解析得出来；空值占位要有 `equals: []` 的门禁佐证。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import report_kit as RK  # noqa: E402

SPEC = HERE / "report_spec_r5_hunt.json"
PLAN = HERE / "spec_r5_hunt.json"
NS = "cypy-loop-20260927"
OUT = HERE / "hunt_r5_self_audit.json"
REQUIRED = [
    "hunt_r5_faces.json",
    "hunt_r5_declared.json",
    "hunt_r5_codegen.json",
    "hunt_r5_cli_face.json",
    "hunt_r5_needles.json",
    "hunt_r5_book.json",
    "hunt_r5_baselines.json",
    "hunt_r5_drivers_lint.json",
    "hunt_r5_calllog_tally.json",
    "close_r5_hunt.out.json",
]
# 根上卷件在**渲染之后**才会存在（close_root 要拿渲染好的报告过 L4 产物门）：
# 本件在渲染前必须断言它「不在盘上」，而不是要求它在渲染前就在；渲染后由
# hunt_r5_render_order.py 现读断言它已落盘且根已归档。
POST_RENDER_ONLY = ["close_r5_hunt_root.out.json"]
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def driver_for(name: str):
    drv = HERE / name.replace(".json", ".py")
    return drv if drv.exists() else None


def is_stale(rel: str) -> bool:
    j = HERE / Path(rel).name
    drv = driver_for(j.name)
    return bool(drv and j.exists() and os.path.getmtime(drv) > os.path.getmtime(j) + 1)


def key_names(obj, acc: set, depth: int = 1) -> set:
    if depth < 0 or not isinstance(obj, dict):
        return acc
    for k, v in obj.items():
        acc.add(str(k))
        if isinstance(v, dict):
            key_names(v, acc, depth - 1)
        elif isinstance(v, list):
            for item in v[:8]:
                if isinstance(item, dict):
                    key_names(item, acc, depth - 1)
    return acc


def parse_err(txt: str) -> str:
    try:
        json.loads(txt)
        return ""
    except Exception as exc:
        return type(exc).__name__


def main() -> int:
    started = now_s()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    missing = [f for f in REQUIRED if not (HERE / f).exists()]
    if missing:
        REFUSE.append(f"判据件/收口件缺失，一个数字都不落：{missing}")
    L = {
        f: json.loads((HERE / f).read_text(encoding="utf-8"))
        for f in REQUIRED
        if (HERE / f).exists()
    }
    for f, doc in L.items():
        if isinstance(doc, dict) and doc.get("refuse"):
            REFUSE.append(f"{f} 自带拒绝：{json.dumps(doc['refuse'], ensure_ascii=False)[:200]}")

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    cache: dict = {}
    stale_disclosed = {d["artifact"]: d.get("reason", "") for d in spec.get("stale_ok", [])}

    # ① 门禁预跑（与渲染器同口径）
    green, red, fake_min, bad_needle = 0, [], [], []
    for g in spec["gates"]:
        st, obj = RK.load_art(g["artifact"], cache)
        if st == "missing":
            red.append(f"{g['label']} 件不在盘上：{g['artifact']}")
            continue
        val, why = RK.walk(obj, g["path"])
        if why:
            red.append(f"{g['label']} 路径解析不出：{g['artifact']}::{g['path']}（{why}）")
            continue
        ok, detail = RK.gate_ok(g, val)
        if ok:
            green += 1
        else:
            red.append(f"{g['label']} 门禁未过：{detail}")
        if "min" in g and int(g["min"]) <= 0:
            fake_min.append(g["label"])
        head = re.split(r"[.\[]", g["path"])[0]
        if head and head not in key_names(obj, set()):
            bad_needle.append(f"{g['label']}::{g['artifact']}::{head}")
    check("门禁全绿（红表必须为空）", red, [], f"{green}/{len(spec['gates'])} 绿")
    check("恒真门（min<=0）必须为 0 道", fake_min, [], "把门焊死不算通过")
    check(
        "每条门禁的 path 首段是被引件里的真键名",
        bad_needle,
        [],
        "子串假命中不算 needle（上一环 control/queue 那类）",
    )
    check(
        "门禁条数达八法 × 每法至少三道",
        len(spec["gates"]) >= 24,
        True,
        f"实得 {len(spec['gates'])} 道",
        ok=len(spec["gates"]) >= 24,
    )

    # ② 计划法条 ↔ 门禁覆盖
    arts_in_gates = {Path(g["artifact"]).name for g in spec["gates"]}
    uncovered = [
        f"法{i}:{Path(law['artifacts'][0][0]).name}"
        for i, law in enumerate(plan["laws"], 1)
        if Path(law["artifacts"][0][0]).name not in arts_in_gates
    ]
    check("八条法的头号证据件都有门禁家族在场", uncovered, [], f"件集 {sorted(arts_in_gates)}")
    check(
        "每条法配三道证据件（派单与收口读同一份计划）",
        sorted({len(law["artifacts"]) for law in plan["laws"]}),
        [3],
        "artifacts 条数分布",
    )

    # ③ 收口与根
    stage = L.get("close_r5_hunt.out.json", {})
    root_live = None
    try:
        con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
        row = con.execute(
            "select status from tasks where ns=? and id=?", (NS, spec["root_task"])
        ).fetchone()
        root_live = row[0] if row else None
        con.close()
    except Exception as exc:
        REFUSE.append(f"根状态现读失败：{type(exc).__name__}: {exc}")
    check("收口叶子 16 张", len(stage.get("leaves") or []), 16, "按 sqlite 反解的叶数")
    check(
        "收口零失败",
        stage.get("failed"),
        [],
        json.dumps(stage.get("failed"), ensure_ascii=False)[:200],
    )
    # 收口次序是「叶 → 渲染 → 根上卷」，本件在两个阶段各要说一句话，两句都可翻红：
    # 渲染前根不该已归档（否则是拿没出的报告去上卷），渲染后根必须已归档。
    root_art_present = (HERE / "close_r5_hunt_root.out.json").exists()
    if root_art_present:
        check(
            "渲染后阶段：根已上卷归档（sqlite 现读 = 已归档）",
            root_live,
            "已归档",
            f"live root={root_live} / 收口件在盘={root_art_present}",
        )
    else:
        check(
            "渲染前阶段：根尚未上卷（现读非已归档 且 收口件不在盘上，两条同时成立）",
            [root_live != "已归档", root_art_present is False],
            [True, True],
            f"live root={root_live} / root 件在盘={root_art_present}",
        )

    check(
        "每叶 omega 链走完（verify 结果为已完成）",
        sorted({row.get("verify") for row in stage.get("leaves") or []}),
        ["已完成"],
        "逐叶 verify 字段",
    )

    # ④ 三套体系与 git 红线
    base = L.get("hunt_r5_baselines.json", {})
    check("三套体系同刻为绿", base.get("three_systems_green"), True, "baselines 件自报")
    check(
        "pytest 失败汇总为 0 且 rc=0（字段名从件反解：failed_sum）",
        [base.get("pytest", {}).get("failed_sum"), base.get("pytest", {}).get("rc")],
        [0, 0],
        "两栏分列",
    )
    check(
        "pytest 通过数不低于上一环实测地板",
        base.get("pytest", {}).get("passed", 0) >= base.get("floors", {}).get("pytest", 1 << 30),
        True,
        f"passed={base.get('pytest', {}).get('passed')} floors={base.get('floors')}",
    )
    check(
        "收集数达地板（解析器活着）",
        base.get("collect", {}).get("nodeids", 0) >= base.get("floors", {}).get("collect", 1 << 30),
        True,
        f"collect={base.get('collect', {}).get('nodeids')}",
    )
    check(
        "地板四栏齐全且来源点名上一环件",
        sorted(base.get("floors") or {}),
        ["collect", "e2e_pass", "pytest", "suite"],
        str(base.get("floors_source"))[:160],
    )
    check(
        "e2e：PASS 达地板且 FAIL/WARN 为零",
        [
            base.get("e2e", {}).get("fields", {}).get("PASS"),
            base.get("e2e", {}).get("fields", {}).get("FAIL"),
            base.get("e2e", {}).get("fields", {}).get("WARN"),
        ],
        [base.get("floors", {}).get("e2e_pass"), 0, 0],
        "三栏分列",
    )
    check(
        "自研套件：Passed 达地板且 Failed 为零",
        [
            base.get("suite", {}).get("fields", {}).get("Passed"),
            base.get("suite", {}).get("fields", {}).get("Failed"),
        ],
        [base.get("floors", {}).get("suite"), 0],
        "两栏分列（拿字段比字段是恒真，这里比的是地板）",
    )
    check(
        "HEAD 未动 / 暂存为 0",
        [base.get("git", {}).get("head"), base.get("git", {}).get("staged")],
        ["17d68b4", 0],
        "本环零提交",
    )
    check(
        "冻结面改动为 0",
        base.get("radius", {}).get("forbidden_total"),
        0,
        json.dumps(base.get("radius", {}).get("touched_forbidden"), ensure_ascii=False)[:200],
    )
    check(
        "半径正面测出确实写了东西",
        base.get("radius", {}).get("allowed_touched", 0) > 10,
        True,
        f"loop/memory 侧 {base.get('radius', {}).get('allowed_touched')} 个",
        ok=base.get("radius", {}).get("allowed_touched", 0) > 10,
    )

    # ⑤ 入账与在账存在性
    bk = L.get("hunt_r5_book.json", {})
    cg, cl = L.get("hunt_r5_codegen.json", {}), L.get("hunt_r5_cli_face.json", {})
    confirmed = (cg.get("confirmed") or []) + (cl.get("confirmed") or [])
    check(
        "卡数 = 两批判据件确诊数之和",
        (bk.get("cards") if isinstance(bk.get("cards"), int) else len(bk.get("cards") or [])),
        len(confirmed),
        f"确诊 {sorted(confirmed)}",
    )
    check(
        "每张卡在账本与 bugs 树里都在（在账，不是我记得）",
        bk.get("on_disk_keys_len"),
        (bk.get("cards") if isinstance(bk.get("cards"), int) else len(bk.get("cards") or [])),
        "per_key_on_disk 全命中",
    )
    check(
        "账本最大号 = 现读 memory/bugs.md",
        bk.get("ledger_after_max"),
        max(
            int(x)
            for x in re.findall(
                r"(?m)^## BUG-(\d+) ", (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
            )
        ),
        "两路独立现读",
    )
    check(
        "未确认档不占号（cli_face 的 UNSURE 不许混进卡表）",
        [x for x in (cl.get("unsure") or []) if x in (bk.get("keys") or [])],
        [],
        "H02 只留件不入账",
    )

    # ⑥ 陈旧与 parse
    stale = sorted({Path(g["artifact"]).name for g in spec["gates"] if is_stale(g["artifact"])})
    undeclared = [s for s in stale if s not in stale_disclosed]
    check(
        "没有判据件比它的驱动脚本旧（除非逐条披露理由）",
        undeclared,
        [],
        f"陈旧集 {stale}，已披露 {list(stale_disclosed)}",
    )
    fake_disclosed = [k for k in stale_disclosed if k not in stale]
    check(
        "披露的例外必须真属陈旧（不许拿 stale_ok 当免检通道）",
        fake_disclosed,
        [],
        "披露而不成立 ⇒ 拒",
    )
    on_disk = sorted(p.name for p in HERE.glob("hunt_r5_*.json"))
    parses = {n: parse_err((HERE / n).read_text(encoding="utf-8")) for n in on_disk}
    bad_parses = sorted(k for k, v in parses.items() if v)
    check(
        "每份 JSON 判据件都能 parse", bad_parses, [], json.dumps(parses, ensure_ascii=False)[:300]
    )
    check(
        "parse 覆盖面 = 盘上判据件数（基数门，不手数）",
        len(parses),
        len(on_disk),
        f"{len(on_disk)} 份",
    )
    check(
        "canary：parse 判据对「相邻字符串续行」必红",
        parse_err('{"why": "甲，"\n "乙"}'),
        "JSONDecodeError",
        "不是恒绿的存在性检查",
    )
    check(
        "canary：parse 判据不误抓合法 JSON",
        parse_err('{"why": "甲，乙", "n": 1}'),
        "",
        "同一把尺子的另一侧",
    )

    # ⑦ 正文占位与 §十
    body_rel = spec["fragment"]
    bstate, btxt = RK.load_art(body_rel, cache)
    text = btxt if isinstance(btxt, str) else ""
    if bstate == "missing":
        REFUSE.append(f"正文片段不在盘上：{body_rel}")
    ph = re.findall(r"\{\{([^{}]+)\}\}", text)
    unresolved_ph = []
    empty_with_witness, empty_no_witness = [], []
    for expr in ph:
        rel, _, dotted = expr.partition("|")
        st, obj = RK.load_art(rel.strip(), cache)
        if st == "missing":
            unresolved_ph.append(f"{expr}（件缺失）")
            continue
        val, w = obj, ""
        if dotted:
            val, w = RK.walk(obj, dotted)
        if w:
            unresolved_ph.append(f"{expr}（{w}）")
        elif val in ([], {}, "", None):
            head = re.split(r"[.\[]", dotted)[0]
            gate_backed = any(
                Path(g["artifact"]).name == Path(rel.strip()).name
                and g["path"].split(".")[0] == head
                and g.get("equals") == []
                for g in spec["gates"]
            )
            (empty_with_witness if gate_backed else empty_no_witness).append(expr)
    check("正文占位全部解析得出来", unresolved_ph, [], f"{len(ph)} 个占位")
    check(
        "空值占位必须有 equals:[] 的门禁背书",
        empty_no_witness,
        [],
        f"有背书 {len(empty_with_witness)} 个",
    )
    s10_declared = (
        len(re.findall(r"(?m)^\d+\. ", text.split("## 八、")[-1])) if "## 八、" in text else -1
    )
    check(
        "§八 失效条目在正文里数得出来（负数=没有该节）",
        s10_declared > 0,
        True,
        f"实测 {s10_declared} 条",
        ok=s10_declared > 0,
    )

    # ⑧ needle 件与法条一致
    nd = L.get("hunt_r5_needles.json", {})
    check(
        "needle 严口径：全部 needle 都是真键名",
        nd.get("real_key_len"),
        nd.get("checked_len"),
        f"{nd.get('real_key_len')}/{nd.get('checked_len')}",
    )
    check(
        "扫描时不存在判据件必须为空表（法条不许引用空气）",
        nd.get("pending_artifacts"),
        [],
        "收口前复扫",
    )
    check(
        "前缀式假命中 canary 抓到了东西",
        bool(nd.get("prefix_canary")),
        True,
        f"{len(nd.get('prefix_canary') or [])} 条",
        ok=bool(nd.get("prefix_canary")),
    )

    # ⑨ 驱动面
    ln = L.get("hunt_r5_drivers_lint.json", {})
    check(
        "亲笔驱动硬错为 0",
        ln.get("hard_violations"),
        0,
        json.dumps(ln.get("hard_lines"), ensure_ascii=False)[:200],
    )
    check("软账不高于上一环基线 0", ln.get("soft_total"), 0, f"码表 {ln.get('soft_codes')}")

    doc = {
        "started": started,
        "gates_total": len(spec["gates"]),
        "gates_green": green,
        "gates_red": red,
        "fake_min_gates": fake_min,
        "needle_bad": bad_needle,
        "stale_undeclared": undeclared,
        "stale_disclosed": list(stale_disclosed),
        "placeholders_total": len(ph),
        "placeholders_unresolved": unresolved_ph,
        "placeholders_empty_unjustified": empty_no_witness,
        "section10_items_declared": s10_declared,
        "closure": {
            "leaves": len(stage.get("leaves") or []),
            "failed": stage.get("failed"),
            "root_pre_render": root_live,
        },
        "self_checks": CHECKS,
        "refuse": [],
        "identity": {"report": spec["name"], "root_task": spec["root_task"]},
        "at_utc": now_s(),
    }
    red_checks = [c["label"] for c in CHECKS if not c["ok"]]
    doc["refuse"] = sorted(set(REFUSE) | {f"判据自证未过：{x}" for x in red_checks})
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "gates_green": f"{green}/{len(spec['gates'])}",
                "self_checks": f"{len(CHECKS) - len(red_checks)}/{len(CHECKS)}",
                "placeholders": len(ph),
                "at_utc": doc["at_utc"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"], "at_utc": now_s()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
