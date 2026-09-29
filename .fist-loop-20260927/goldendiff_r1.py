"""基准重注册的逐行差判定：`.out` 只允许「数字面」变化，且变化文件集合必须等于申报集合。

口径来自 R1-修复 spec 的 fingerprint：「基准重注册前后逐行差只落在数字上」。
两条判据都是**双向**的：既不许有意料外文件被改（--update 会重写全部 25 份，mtime 动了
不等于内容动了），也不许申报的文件其实没变（那说明修复没打到端到端面）。

用法：python goldendiff_r1.py <允许变化的文件名列表(逗号分隔)>
退出码非 0 = 拒绝（不写盘）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
BEFORE = HERE / "golden_before"
AFTER = ROOT / "examples"
NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def skeleton(text: str) -> str:
    """把数值 token 换成占位符，得到「非数字面骨架」。"""
    return NUM.sub("#", text)


def numeric_change(before: str, after: str) -> bool:
    """该行是否**只**在数字面变化：骨架相同 + 数值 token 一一对应且数值相等。

    `42` → `42.0` 这类"浮点化后打印形态变了、值没变"是本单唯一的合法差异；
    值本身变了（42 → 43）就不是"只落在数字上"，必须走人工审定另开一单。
    """
    if skeleton(before) != skeleton(after):
        return False
    nb, na = NUM.findall(before), NUM.findall(after)
    if len(nb) != len(na) or not nb:
        return False
    for x, y in zip(nb, na):
        try:
            if float(x) != float(y):
                return False
        except ValueError:
            return False
    return True


def selftest() -> None:
    """判据自己也得被钉住：一条必过、两条必不过（否则"只落在数字上"是句空话）。"""
    assert numeric_change("auto(int to float): 42", "auto(int to float): 42.0")
    assert not numeric_change(
        "auto(int to float): 42", "auto(int to float): 43"
    ), "值变了却被判成数字面差异"
    assert not numeric_change("float: 3.14", "double: 3.14"), "骨架变了却被判成数字面差异"
    assert not numeric_change("no number here", "no number here"), "无 token 的行不该算差异"


def main() -> int:
    selftest()
    allowed = [a.strip() for a in sys.argv[1].split(",") if a.strip()]
    if not allowed:
        print("REFUSE — 没申报允许变化的基准文件，判据无法成立")
        return 1

    before = sorted(p.name for p in BEFORE.glob("*.out"))
    after = sorted(p.name for p in AFTER.glob("*.out"))
    refuse = []
    if before != after:
        refuse.append(
            f"基准文件集合本身变了：only_before={set(before) - set(after)} "
            f"only_after={set(after) - set(before)}"
        )

    changed, digit_only_lines, other_lines = {}, [], []
    for name in before:
        b = (BEFORE / name).read_text(encoding="utf-8", errors="replace")
        a = (
            (AFTER / name).read_text(encoding="utf-8", errors="replace")
            if (AFTER / name).exists()
            else ""
        )
        if a == b:
            continue
        bl, al = b.splitlines(), a.splitlines()
        changed[name] = {"before_lines": len(bl), "after_lines": len(al)}
        if len(bl) != len(al):
            refuse.append(f"{name} 行数变了（{len(bl)}→{len(al)}），不是「只落在数字上」的变化")
            continue
        for i, (x, y) in enumerate(zip(bl, al), 1):
            if x == y:
                continue
            if numeric_change(x, y):
                digit_only_lines.append({"file": name, "line": i, "before": x, "after": y})
            else:
                other_lines.append({"file": name, "line": i, "before": x, "after": y})

    if set(changed) != set(allowed):
        refuse.append(f"变化文件集合与申报不符：实测 {sorted(changed)} vs 申报 {sorted(allowed)}")
    if other_lines:
        refuse.append(f"{len(other_lines)} 行差异不是数字面（首条：{other_lines[0]}）")
    if not digit_only_lines:
        refuse.append("没有任何数字面差异 ⇒ 修复没有打到端到端输出，别把重注册当已完成")

    doc = {
        "refuse": refuse,
        "changed_files": changed,
        "unchanged_files": len(before) - len(changed),
        "digit_only_lines": digit_only_lines,
        "other_lines": other_lines,
    }
    (HERE / "golden_diff_r1.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "changed": sorted(changed),
                "unchanged": doc["unchanged_files"],
                "digit_only_line_count": len(digit_only_lines),
            },
            ensure_ascii=False,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
