#!/usr/bin/env python3
"""R3-修复：六件缺陷的「修前 / 修后」成对复算 + 判据自证。

复算用的是 R3-寻虫 留下的同一批夹具（`hunt_r3_repro.py`，退出码 0=现形 / 1=不现形 / 2=夹具坏），
所以这不是"换了一把更宽的尺子"：

- **C1/C3/C4/C6** 必须从 0 翻到 1 ⇒ 四件按原主张已消除；
- **C5/C8** 允许仍是 0，但必须给出"为什么仍红"的可机器否证证据：
  - C5 的现形判据钉的是 `realloc(p, 0)` **返回 None** 这一半，而那一半被既有测试
    `test_realloc_zero_size` 钉着（红线：不弱化既有测试）⇒ 本环只修"注解/文档与返回值互斥"，
    所以 observed 里 `annotation` 必须从 `int` 变成 `Optional`，`returned` 仍是 `None`；
  - C8 的现形判据钉的是"块外指针不报错"，而按 SYNTAX/04-pointer-types.md 那**才是正确行为**
    ⇒ 本环修的是 docstring 规则 2 的字面：旧字面必须从模块里消失、新字面必须引用
      SYNTAX/04 与函数作用域口径。

修前 rc 取自 2026-09-28 00:03 那一批快照（`tmp_r3/before_C*.out`，同一夹具、未动产品码之前），
常量 `BEFORE_RC` 就抄自当时的终端输出；快照文件本身也在盘上，可逐字对照。

两条自证防"尺子坏了"：夹具任何一例 rc=2 记 refuse；修前快照的 `defect_present` 必须仍是
true（否则"翻转"这件事没有对照组）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TMP = HERE / "tmp_r3"
REPRO = HERE / "hunt_r3_repro.py"
MUST_FLIP = ("C1", "C3", "C4", "C6")
SHAPE_KEPT = ("C5", "C8")
BEFORE_RC = {"C1": 0, "C3": 0, "C4": 0, "C5": 0, "C6": 0, "C8": 0}
OLD_RULE2 = "指针语法只能在构建块内部使用"

REFUSE: list = []


def run_case(case: str) -> tuple:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPRO), case],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=400,
    )
    lines = (proc.stdout or "").strip().splitlines()
    doc = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
    return proc.returncode, doc


def decide(case: str, after_rc: int) -> tuple:
    """翻转判定的唯一口径；自证也走这里，避免"判据在别处又写了一遍"。"""
    if case in MUST_FLIP:
        return ("before=0 → after=1", BEFORE_RC[case] == 0 and after_rc == 1)
    return ("before=0 → after=0（行为被既有测试/冻结层钉住），只修声明侧",
            BEFORE_RC[case] == 0 and after_rc == 0)


def read_snapshot(name: str) -> dict:
    path = TMP / name
    if not path.exists():
        REFUSE.append(f"缺快照 {name}（对照链断了）")
        return {}
    lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    last = lines[-1] if lines else ""
    return json.loads(last) if last.startswith("{") else {}


def main() -> int:
    flips = {}
    for case in MUST_FLIP + SHAPE_KEPT:
        before_doc = read_snapshot(f"before_{case}.out")
        if before_doc.get("id") != case:
            REFUSE.append(f"before_{case}.out 不是 {case} 的快照：{before_doc}")
        if before_doc.get("defect_present") is not True:
            REFUSE.append(f"{case} 的修前对照不成立（defect_present 不为 true）：{before_doc}")
        after_rc, after_doc = run_case(case)
        expected, ok = decide(case, after_rc)
        row = {
            "before_rc": BEFORE_RC[case],
            "before_observed": before_doc.get("observed"),
            "after_rc": after_rc,
            "after_observed": after_doc.get("observed"),
            "present_after": after_doc.get("defect_present"),
            "expected": expected,
            "ok": ok,
        }
        if after_rc == 2:
            REFUSE.append(f"{case} 夹具坏了（rc=2），不能拿来当已修的证据")
        if not ok:
            REFUSE.append(f"{case} 判定未成立：期望 {expected}，实得 after={after_rc}")
        flips[case] = row

    c5_obs = flips["C5"]["after_observed"] or {}
    if c5_obs.get("annotation") != "Optional" or c5_obs.get("returned") != "None":
        REFUSE.append(f"C5 声明侧未成立：observed={c5_obs}")
    if (flips["C5"]["before_observed"] or {}).get("annotation") != "int":
        REFUSE.append(f"C5 修前注解不是 int，对照断了：{flips['C5']['before_observed']}")

    bbc = (ROOT / "cypyc" / "analyzer" / "build_block_checker.py").read_text(encoding="utf-8")
    parts = bbc.split('"""')
    mod_doc = parts[1] if len(parts) >= 3 else ""
    checks = {
        "old_rule2_literal_gone": OLD_RULE2 not in bbc,
        "mentions_frozen_doc": "04-pointer-types" in mod_doc,
        "mentions_function_scope": "函数作用域" in mod_doc,
    }
    for key, value in checks.items():
        if not value:
            REFUSE.append(f"C8 声明侧未成立：{key}=false")

    if not all(flips[c]["ok"] for c in MUST_FLIP + SHAPE_KEPT):
        REFUSE.append("有用例的 ok 旗为 false")

    # 自证：同一判定函数必须能抓"没翻"、且不误抓"翻了"
    probe_flip_not_caught = decide("C1", 0)[1] is False
    probe_flip_caught = decide("C1", 1)[1] is True
    probe_kept_not_caught = decide("C5", 1)[1] is False
    if not (probe_flip_not_caught and probe_flip_caught and probe_kept_not_caught):
        REFUSE.append(f"翻转判据自证失败：{probe_flip_not_caught}/"
                      f"{probe_flip_caught}/{probe_kept_not_caught}")

    out = {
        "flips": flips,
        "declared_side": {"c5_observed": c5_obs, "c8_doc_checks": checks},
        "judge_selfprobe": {
            "must_catch_no_flip_on_C1": probe_flip_not_caught,
            "must_not_miss_flip_on_C1": probe_flip_caught,
            "must_catch_spurious_flip_on_C5": probe_kept_not_caught,
        },
        "refuse": REFUSE,
    }
    (HERE / "fix_r3_evidence.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
