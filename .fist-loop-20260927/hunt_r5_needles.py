"""R5-寻虫 环节的 needle 严口径实测：needle 必须是判据件里的**真键名**，不是文件名字符串。

为什么单独建一个驱动而不是在报告里手写数：上一环的教训是「环节计划里 15 个 needle 盘上不存在、
3 个只是子串假命中」，而那些数是我手写进计划的——手写的数本身就是主张。这里把「扫到多少、
哪几个不合格」全部现测，并把实测数**写回** spec 的 `needle_verification`，让报告引用的数与
判据件同源。canary 两条：前缀式 needle 必须被严口径拒（否则规则是假的），真键名必须放行
（否则规则把合格件也杀了，等于恒红）。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "spec_r5_hunt.json"
OUT = HERE / "hunt_r5_needles.json"
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


def main() -> int:
    plan = json.loads(SPEC.read_text(encoding="utf-8"))
    rows, pending, absent_file = [], [], []
    for i, law in enumerate(plan["laws"], 1):
        for entry in law["artifacts"]:
            rel, needle, minc = (entry + [1])[:3]
            p = ROOT / rel
            if not p.exists():
                pending.append(f"law{i}:{rel}")
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
                REFUSE.append(f"{rel} 不是合法 JSON：{str(exc)[:120]}")
                continue
            keys = keys_one_level(doc)
            in_text = needle in text
            is_key = needle in keys
            if not in_text:
                absent_file.append(f"law{i}:{rel}:{needle}")
            verdict = "real-key" if is_key else ("false-substring" if in_text else "missing")
            rows.append(
                {
                    "law": i,
                    "file": rel,
                    "needle": needle,
                    "min_chars": minc,
                    "in_text": in_text,
                    "is_real_key": is_key,
                    "file_chars": len(text),
                    "chars_ok": len(text) >= int(minc),
                    "verdict": verdict,
                }
            )
    strict_rejected = [r for r in rows if r["verdict"] != "real-key"]
    prefix_canary = []
    for rel in sorted({r["file"] for r in rows if r["verdict"] == "real-key"}):
        p = ROOT / rel
        doc = json.loads(p.read_text(encoding="utf-8"))
        ks = keys_one_level(doc)
        for pre in ("confi", "unattr", "row"):
            if pre in p.read_text(encoding="utf-8") and pre not in ks:
                prefix_canary.append(
                    {"file": rel, "prefix": pre, "substring_present": True, "is_real_key": False}
                )
    check_ok_canary = any(r["is_real_key"] for r in rows)
    if not prefix_canary:
        REFUSE.append("canary 没抓到任何前缀式假命中 ⇒ 严口径与子串口径此刻无法区分，规则形同虚设")
    if not check_ok_canary:
        REFUSE.append("没有任何 needle 通过严口径 ⇒ 判据恒红，不是合格")
    bad_chars = [
        f"{r['law']}:{r['file']}({r['file_chars']}<{r['min_chars']})"
        for r in rows
        if r["verdict"] == "real-key" and not r["chars_ok"]
    ]
    if bad_chars:
        REFUSE.append(f"min_chars 不达标：{bad_chars}")
    if absent_file:
        REFUSE.append(f"needle 在判据件里连子串都不是：{absent_file}")
    nv = plan.get("needle_verification") or {}
    nv["checked_len"] = len(rows)
    nv["missing_before"] = len([r for r in rows if r["verdict"] == "missing"])
    nv["false_substring_before"] = len([r for r in rows if r["verdict"] == "false-substring"])
    nv["artifacts_pending"] = sorted(set(pending))
    nv["strict_rule_rejected_len"] = len(strict_rejected)
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
        "不合格 verdict 只允许「件还没跑」这一种（严口径不许混进结论）",
        sorted({x["verdict"] for x in rows} - {"real-key", "artifact-not-yet-produced"}),
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
        "rows": rows,
        "checked_len": len(rows),
        "real_key_len": len([r for r in rows if r["verdict"] == "real-key"]),
        "per_law_real": per_law_real,
        "pending_artifacts": sorted(set(pending)),
        "prefix_canary": prefix_canary[:8],
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
