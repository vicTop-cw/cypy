"""R5-修复 环节的 needle 严口径实测：needle 必须是判据件里的**真键名**，不是文件名字符串。

为什么单独建一个驱动而不是在报告里手写数：上一环的教训是「环节计划里 15 个 needle 盘上不存在、
3 个只是子串假命中」，而那些数是我手写进计划的——手写的数本身就是主张。这里把「扫到多少、
哪几个不合格」全部现测，并把实测数**写回** spec 的 `needle_verification`，让报告引用的数与
判据件同源。canary 两条：前缀式 needle 必须被严口径拒（否则规则是假的），真键名必须放行
（否则规则把合格件也杀了，等于恒红）；两侧用的是同一把尺子 `keys_one_level`，尺子一松
（退化成子串/前缀匹配）canary 那头就先红。前缀不是我手打的，是从各件里**已判真的 needle**
上机械截出来的。

判据件口径也现测：本环八条法只允许引 `RING_FILES` 这八件（认领表/锁/根因/回退/影响面/
三套体系/账面/驱动面）。上一环 R5-寻虫 的 faces / declared / codegen / cli_face / book 不在
这八件里，计划点到它们就是串环，`off_ring_artifacts` 逐条点名判红。件还在跑（盘上只有
started/refuse 这种生命周期键的桩件，现在 fix_r5_baselines.json 就是这个样子）不写成
「needle 坏了」，写成 `pending_artifacts`——但它照样不进真键名计数，逐条门该红仍红。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "spec_r5_fix.json"
OUT = HERE / "fix_r5_needles.json"
# 本环（R5-修复）八条法的判据件文件名：spec 的 laws[].artifacts 只能落在这个集合里。
RING_FILES = (
    "fix_r5_intake.json",  # 法① 认领表
    "fix_r5_locks.json",  # 法② 锁先行
    "fix_r5_rc.json",  # 法③ 根因合并修
    "fix_r5_revert.json",  # 法④ 回退矩阵
    "fix_r5_impact.json",  # 法⑤ 语义变更影响面
    "fix_r5_baselines.json",  # 法⑥ 三套体系 + 地板 + 半径
    "fix_r5_ledger.json",  # 法⑦ 账面闭环
    "fix_r5_drivers_lint.json",  # 法⑧ 驱动面自证
)
# 一件「还没跑完」的判据件在盘上长这样：只有生命周期键，一个证据键都还没长出来。
STUB_KEYS = frozenset({"started", "refuse", "at_utc", "note", "finished_at_utc"})
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


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def keys_one_level(doc) -> set:
    out = set()
    if isinstance(doc, dict):
        for k, v in doc.items():
            out.add(str(k))
            if isinstance(v, dict):
                out.update(str(k2) for k2 in v)
            elif isinstance(v, list):
                for item in v[:6]:
                    if isinstance(item, dict):
                        out.update(str(k2) for k2 in item)
    return out


def is_stub(doc) -> bool:
    """判据件还是个桩（跑到一半先落了 started/refuse）：一个证据键都没长出来 ⇒ 记还没跑。

    什么证据会把它判红：桩判据只会把「needle 不在」降级成 pending，永远不能把「needle 在」
    升级成 real-key（调用处先判 is_key）；反过来，一件已经跑完、带 needle 的件被误判成桩，
    那一条法的真键名数就会掉到 3 以下，逐条门立刻红。
    """
    return isinstance(doc, dict) and bool(doc) and set(map(str, doc)) <= STUB_KEYS


def chop(needle: str) -> str:
    """从一条已判真的 needle 上机械截出前缀式假命中（canary 用，不手打字面量）。"""
    return needle[: max(3, len(needle) // 2)]


def main() -> int:
    plan = json.loads(SPEC.read_text(encoding="utf-8"))
    rows, pending, absent_file = [], [], []
    for i, law in enumerate(plan["laws"], 1):
        for entry in law["artifacts"]:
            rel, needle, minc = (entry + [1])[:3]
            p = ROOT / rel
            if not p.exists():
                pending.append(f"law{i}:{p.name}(件不在盘上)")
                rows.append(
                    {
                        "law": i,
                        "file": rel,
                        "needle": needle,
                        "verdict": "artifact-not-yet-produced",
                    }
                )
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            try:
                doc = json.loads(text)
            except json.JSONDecodeError as exc:
                REFUSE.append(f"{p.name} 不是合法 JSON：{str(exc)[:120]}")
                continue
            keys = keys_one_level(doc)
            in_text = needle in text
            is_key = needle in keys
            stub = is_stub(doc)
            if is_key:
                verdict = "real-key"
            elif stub:
                verdict = "artifact-pending-stub"
                pending.append(f"law{i}:{p.name}(桩件 {sorted(map(str, doc))})")
            elif in_text:
                verdict = "false-substring"
            else:
                verdict = "missing"
                absent_file.append(f"law{i}:{p.name}:{needle}")
            rows.append(
                {
                    "law": i,
                    "file": rel,
                    "needle": needle,
                    "min_chars": minc,
                    "in_text": in_text,
                    "is_real_key": is_key,
                    "stub_artifact": stub,
                    "file_chars": len(text),
                    "chars_ok": len(text) >= int(minc),
                    "verdict": verdict,
                }
            )
    strict_rejected = [r for r in rows if r["verdict"] != "real-key"]
    prefix_canary = []
    for rel in sorted({r["file"] for r in rows if r["verdict"] == "real-key"}):
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        ks = keys_one_level(json.loads(text))
        mine = sorted(
            {r["needle"] for r in rows if r["file"] == rel and r["verdict"] == "real-key"}
        )
        for needle in mine:
            pre = chop(needle)
            if pre == needle or pre in ks or pre not in text:
                continue
            prefix_canary.append(
                {
                    "file": p.name,
                    "needle": needle,
                    "prefix": pre,
                    "substring_present": True,
                    "is_real_key": False,
                }
            )
    check_ok_canary = any(r["is_real_key"] for r in rows)
    if not prefix_canary:
        REFUSE.append("canary 没抓到任何前缀式假命中 ⇒ 严口径与子串口径此刻无法区分，规则形同虚设")
    if not check_ok_canary:
        REFUSE.append("没有任何 needle 通过严口径 ⇒ 判据恒红，不是合格")
    bad_chars = [
        f"{r['law']}:{Path(r['file']).name}({r['file_chars']}<{r['min_chars']})"
        for r in rows
        if r["verdict"] == "real-key" and not r["chars_ok"]
    ]
    if bad_chars:
        REFUSE.append(f"min_chars 不达标：{bad_chars}")
    if absent_file:
        REFUSE.append(f"needle 在判据件里连子串都不是：{absent_file}")
    declared_files = sorted({Path(r["file"]).name for r in rows})
    off_ring = sorted(set(declared_files) - set(RING_FILES))
    stub_rows = sorted(
        {Path(r["file"]).name for r in rows if r["verdict"] == "artifact-pending-stub"}
    )
    nv = plan.get("needle_verification") or {}
    nv["checked_len"] = len(rows)
    nv["missing_before"] = len([r for r in rows if r["verdict"] == "missing"])
    nv["false_substring_before"] = len([r for r in rows if r["verdict"] == "false-substring"])
    nv["artifacts_pending"] = sorted(set(pending))
    nv["artifacts_declared"] = declared_files
    nv["off_ring_artifacts"] = off_ring
    nv["pending_stub_artifacts"] = stub_rows
    nv["strict_rule_rejected_len"] = len(strict_rejected)
    nv["canary_prefixes"] = len(prefix_canary)
    nv["measured_at_utc"] = now_iso()
    plan["needle_verification"] = nv
    SPEC.write_text(
        json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    check(
        "扫描覆盖面 = 计划里 artifacts 声明总数（不手数）",
        len(rows),
        sum(len(law["artifacts"]) for law in plan["laws"]),
        "两路回加",
    )
    check(
        "计划引用的判据件文件名 = 本环八件（寻虫环的 faces/declared/codegen/cli_face/book 混进来即红）",
        declared_files,
        sorted(RING_FILES),
        f"多出来的：{off_ring}",
    )
    check(
        "不合格 verdict 只允许「件还没跑」这一类（严口径不许混进结论）",
        sorted(
            {x["verdict"] for x in rows}
            - {"real-key", "artifact-not-yet-produced", "artifact-pending-stub"}
        ),
        [],
        "其余一类都算 needle 坏了",
    )
    check(
        "canary 两侧：前缀必被拒、真键名必放行",
        [bool(prefix_canary), check_ok_canary],
        [True, True],
        f"canary {len(prefix_canary)} 条 / 放行 {check_ok_canary}",
    )
    per_law_real = {}
    for n in range(1, len(plan["laws"]) + 1):
        of_law = [r for r in rows if r["law"] == n]
        per_law_real[f"law{n}"] = len([r for r in of_law if r["verdict"] == "real-key"])
        if len(of_law) != len(plan["laws"][n - 1]["artifacts"]):
            REFUSE.append(
                f"法{n} 声明 {len(plan['laws'][n-1]['artifacts'])} 件，扫到 {len(of_law)} 行"
            )
    check(
        "每条法的 needle 都按『法号→真键名条数』逐条给数（法号缺一个就是逐条门形同虚设）",
        sorted(per_law_real),
        [f"law{i}" for i in range(1, len(plan["laws"]) + 1)],
        json.dumps(per_law_real, ensure_ascii=False)[:200],
    )
    check(
        "每条法的三件证据都验到真键名（少一件就是那一条法的门没承重）",
        sorted(set(per_law_real.values())),
        [3],
        json.dumps(per_law_real, ensure_ascii=False)[:200],
    )
    red = [c["label"] for c in CHECKS if not c["ok"]]
    doc = {
        "started": now_iso(),
        "ring_files_expected": sorted(RING_FILES),
        "ring_files_declared": declared_files,
        "off_ring_artifacts": off_ring,
        "pending_stub_artifacts": stub_rows,
        "rows": rows,
        "checked_len": len(rows),
        "real_key_len": len([r for r in rows if r["verdict"] == "real-key"]),
        "per_law_real": per_law_real,
        "pending_artifacts": sorted(set(pending)),
        "prefix_canary": prefix_canary[:8],
        "prefix_canary_len": len(prefix_canary),
        "needle_verification_written_back": nv,
        "self_checks": CHECKS,
        "refuse": sorted(set(REFUSE) | {f"判据自证未过：{x}" for x in red}),
        "at_utc": now_iso(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "checked_len": doc["checked_len"],
                "real_key_len": doc["real_key_len"],
                "pending": doc["pending_artifacts"],
                "off_ring": off_ring,
                "canary_len": len(prefix_canary),
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
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"]}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
