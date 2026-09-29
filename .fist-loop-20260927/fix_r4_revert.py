"""回退矩阵：把每个根因的实现**单独摘掉**，看该根因的锁是不是真的变红、对照锁是不是仍然绿。

四件事都要正面测出来，不是「我觉得锁很稳」：
① 摘 RC1 ⇒ C01..C05 里至少一条红；摘 RC2 ⇒ C06..C08 红；摘 RC3 ⇒ C09..C11 红；摘 RC4 ⇒ C12/横向锁红；
② **四条对照锁在任何一次摘除里都必须保持绿**（它们钉的是「正确程序不该报错」，
   如果摘掉实现反而让它们红，说明锁钉的是文案而不是行为）；
③ 跨根因一起红是**允许**的（本次就是合并修，共用同一张签名表），但要逐条记下来；
④ 每次摘除后必须把文件按 sha 复原，复原不自证就等于改坏了产品码。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TARGET = ROOT / "cypyc" / "analyzer" / "type_checker.py"
LOCK_FILE = "tests/test_loop_20260927_fix_r4.py"
OUT = HERE / "fix_r4_revert.json"
REFUSE: list = []

CONTROLS = {"test_arity_control_on_alias_callable_still_reports",
            "test_arg_type_control_on_dynamic_value_stays_silent",
            "test_fixture_matches_declared_expectation[C08_ctl]",
            "test_fixture_matches_declared_expectation[C09_ctl]"}

# (根因, 唯一锚点行, 摘除后的替换)
MUTATIONS = [
    ("RC1", '        name = getattr(node, "name", None)',
     '        return  # MUT_RC1\n        name = getattr(node, "name", None)'),
    ("RC2", '        if not isinstance(want, Type) or not isinstance(got, Type):',
     '        return False  # MUT_RC2\n'
     '        if not isinstance(want, Type) or not isinstance(got, Type):'),
    ("RC3", '                if param.name == "self" and "self" in self.type_map:',
     '                if False:  # MUT_RC3'),
    ("RC4", '        if not isinstance(t, Type):\n            return str(t)',
     '        return t.name if isinstance(t, Type) else str(t)  # MUT_RC4\n'
     '        if not isinstance(t, Type):\n            return str(t)'),
]
EXPECT_RED = {"RC1": r"\[C0[1-5]\]", "RC2": r"\[C0[6-8]\]", "RC3": r"\[C09\]|\[C10\]|\[C11\]",
              "RC4": r"\[C12\]|test_no_internal_repr_leaks"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_locks() -> tuple:
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", LOCK_FILE,
         "-p", "no:cacheprovider", "--no-header", "-o", "addopts=", "-q", "--tb=no"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)
    text = (r.stdout or "") + (r.stderr or "")
    failed = sorted({m.group(1).split("::")[-1] for m in
                     re.finditer(r"^FAILED \S+::(\S+)", text, re.M)})
    if " passed" not in text and " failed" not in text:
        REFUSE.append(f"pytest 输出读不到汇总行：{text[-200:]!r}")
    return failed, text


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    original = TARGET.read_text(encoding="utf-8")
    base_sha = sha(TARGET)
    rows = []
    try:
        clean_failed, _ = run_locks()
        if clean_failed:
            REFUSE.append(f"未摘任何东西时锁就有红：{clean_failed}（矩阵的基线不成立）")
        for rc, needle, replacement in MUTATIONS:
            if original.count(needle) != 1:
                REFUSE.append(f"{rc} 的锚点命中 {original.count(needle)} 次（应为 1）⇒ 不敢动")
                rows.append({"rc": rc, "status": "anchor_not_unique",
                             "hits": original.count(needle)})
                continue
            TARGET.write_text(original.replace(needle, replacement, 1), encoding="utf-8",
                              newline="\n")
            if sha(TARGET) == base_sha:
                REFUSE.append(f"{rc}：摘除后文件没变（针没扎进去）")
            failed, text = run_locks()
            rows.append({"rc": rc, "status": "mutated", "failed": failed,
                         "expected_red_hit": bool([f for f in failed
                                                   if re.search(EXPECT_RED[rc], f)]),
                         "controls_green": sorted(CONTROLS - set(failed)),
                         "controls_broken": sorted(CONTROLS & set(failed)),
                         "other_cause_failures": sorted(
                             f for f in failed
                             if not re.search(EXPECT_RED[rc], f) and f not in CONTROLS)})
            if text.count("error") and "1 failed" not in text and "1 error" in text:
                rows[-1]["mutation_broke_collection"] = True
            TARGET.write_text(original, encoding="utf-8", newline="\n")
            if sha(TARGET) != base_sha:
                REFUSE.append(f"{rc} 之后 sha 复原失败：{sha(TARGET)[:12]} ≠ {base_sha[:12]}")
    finally:
        TARGET.write_text(original, encoding="utf-8", newline="\n")
        if sha(TARGET) != base_sha:
            REFUSE.append(f"收尾复原失败：{TARGET} 的 sha 与起点不一致")

    for row in rows:
        if row.get("status") == "mutated":
            if not row["expected_red_hit"]:
                REFUSE.append(f"{row['rc']} 摘掉实现后该根因的锁一条都没红 ⇒ 锁不承重")
            if row["controls_broken"]:
                REFUSE.append(f"{row['rc']} 摘除时把对照锁也弄红了：{row['controls_broken']}")
    collateral = {r["rc"]: r["other_cause_failures"] for r in rows
                  if r.get("status") == "mutated" and r["other_cause_failures"]}
    doc = {"started": started, "lock_file": LOCK_FILE, "baseline_sha256": base_sha,
           "restored_sha256": sha(TARGET), "clean_run_failed": clean_failed if rows else [],
           "rows": rows, "collateral": collateral,
           "note": "跨根因连带变红是**合并修**的必然结果（共用 callable_sigs 与 "
                   "_callable_arg_mismatch），逐条记下但不算违例；违例只看两条："
                   "本根因的锁必须红、四条对照锁必须一直绿",
           "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"],
                      "rows": [{"rc": r.get("rc"), "status": r.get("status"),
                                "expected_red": r.get("expected_red_hit"),
                                "failed_n": len(r.get("failed", []))} for r in rows],
                      "restored": doc["restored_sha256"] == base_sha},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
