#!/usr/bin/env python3
"""R2-寻虫 的预算内 fuzz：专找"rc=0 但产物是垃圾/空"的静默型。

变异形状：单点删字符、单点换行截断、成对括号删一个、关键字大小写改写。
判据不是"有没有崩"（崩了是显式失败，不占号），而是**三件同时成立**才算抓到：
 rc=0 ∧ CLI 打了成功横幅 ∧ 产物里没有任何被声明过的符号痕迹（或 .pyx 为空）。
另配两条对照：
 A 正例必不抓：已知合法源必须 rc=0 且产物含符号（否则判据在抓一切，等于恒红）；
 B 反例必抓：一条人造的"rc=0 但产物空"的场景如果判据不报，说明判据恒绿（记 refuse）。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
PY = sys.executable
BUDGET = 72
REFUSE: list = []

SEEDS = {
    "struct": "struct Point:\n    x: int\n    y: int\n\nlet p = Point(1, 2)\nprint(p.x)\n",
    "generic": "def identity<T>(v: T) -> T:\n    return v\n\nprint(identity(3))\n",
    "enum": "enum Color:\n    RED\n    GREEN\n\nprint(Color.RED)\n",
}


def transpile(src: str, tag: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        p = ROOT / ".fist-loop-20260927" / "probes" / f"fz_{tag}.cypy"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8", newline=chr(10))
        r = subprocess.run(
            [PY, "-X", "utf8", "-m", "cypyc", "transpile", str(p), "-o", str(out)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        pyx = sorted(out.rglob("*.pyx"))
        body = pyx[0].read_text(encoding="utf-8", errors="replace") if pyx else ""
        return {
            "rc": r.returncode,
            "banner": "Transpiled successfully" in (r.stdout or ""),
            "emitted": bool(pyx),
            "bytes": len(body),
            "out": body,
        }


def mutations(src: str):
    for i in range(0, len(src), max(1, len(src) // 6)):
        yield f"delchar{i}", "".join(c for j, c in enumerate(src) if j != i)
        yield f"cut{i}", src[:i]
    yield "unbalanced_paren", src.replace("Point(1, 2)", "Point(1, 2", 1)
    yield "keyword_case", src.replace("struct", "Struct", 1)


def verdict(res: dict, want_symbol: str) -> tuple:
    """静默型判据：rc=0 + 成功横幅 + 产物里没有被声明的符号。"""
    silent = (
        res["rc"] == 0
        and res["banner"]
        and (res["bytes"] == 0 or (want_symbol and want_symbol not in res["out"]))
    )
    return silent


def main() -> int:
    # 对照 B（必被抓）：人造一条"rc=0 + 成功横幅 + 空产物"，判据若不放红就是恒绿判据。
    fake = {"rc": 0, "banner": True, "bytes": 0, "out": ""}
    if not verdict(fake, "Point"):
        REFUSE.append("对照 B 失败：合成的静默违例没被抓到 ⇒ 判据恒绿，本轮 fuzz 结果无效")
    # 对照 A′（必不误抓）：rc=0 且产物里有符号的正常情况不能报红。
    good = {"rc": 0, "banner": True, "bytes": 40, "out": "cdef class Point:\n    pass\n"}
    if verdict(good, "Point"):
        REFUSE.append("对照 A′ 失败：合法产物被判成静默缺陷 ⇒ 判据在抓一切，等于恒红")
    rows = []
    n = 0
    for tag, seed in SEEDS.items():
        want = {"struct": "Point", "generic": "identity", "enum": "Color"}[tag]
        base = transpile(seed, f"{tag}_base")
        ok_base = base["rc"] == 0 and want in base["out"]
        rows.append(
            {"case": f"{tag}:unmutated", "rc": base["rc"], "silent": False, "baseline_ok": ok_base}
        )
        if not ok_base:
            REFUSE.append(
                f"对照 A 失败：{tag} 的未变异源本身没通过（rc={base['rc']}），"
                "判据的基线不成立，静默检测不可信"
            )
        for name, mutant in mutations(seed):
            if n >= BUDGET:
                break
            if not mutant.strip():
                # 空源码编译成空模块是合法行为，不是静默缺陷；上一版把 cut0（截成空串）
                # 当成违例抓，三条"silent"全是这个假阳性。
                continue
            n += 1
            r = transpile(mutant, f"{tag}_{n}")
            rows.append(
                {
                    "case": f"{tag}:{name}",
                    "rc": r["rc"],
                    "banner": r["banner"],
                    "bytes": r["bytes"],
                    "silent": verdict(r, want),
                }
            )
    caught = [x for x in rows if x.get("silent")]
    explicit = [x for x in rows if x["rc"] != 0]
    doc = {
        "refuse": REFUSE,
        "budget": BUDGET,
        "mutants_run": n,
        "silent_defects": caught,
        "explicit_failures": len(explicit),
        "clean_rows": len(rows) - len(caught) - len(explicit),
        "rows": rows,
    }
    (HERE / "hunt_r2_fuzz.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": REFUSE,
                "mutants_run": n,
                "silent": [c["case"] for c in caught][:8],
                "explicit_failures": len(explicit),
            },
            ensure_ascii=False,
        )
    )
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
