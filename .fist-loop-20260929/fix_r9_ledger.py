"""R9 账面：只增不删地追加闭环/去重段落，每条都被 `hunt_r9_stale_claims.py` 的实测格驱动。

三条纪律写死在这里：
1. 编号与区间一律从账本正文反解（`pick_block` 命中必须恰好一条，`BUG-96` 有两个抬头就按 summary 二次筛）；
2. 主张作废 ≠ 删正文 —— append-only，用 `### DUPLICATE` 指认正身，正身自己该 OPEN 就仍 OPEN；
3. 落盘前 difflib 必须证明「只有插入」，temp+os.replace，重跑有幂等守卫（已有同名段落就跳过）。
"""

from __future__ import annotations

import datetime
import difflib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "fix_r9_ledger.json"

STALE_LOG = HERE / "logs" / "r9_stale_a1.txt"
GATE_LOG = HERE / "logs" / "r9_gate_a2.txt"
DEMO_LOG = HERE / "logs" / "r9_demo_check.txt"
PYTEST_LOG = HERE / "logs" / "r9_pytest_r2.log"
SPEC14 = ROOT / "SYNTAX" / "14-syntax-sugar.md"
SPEC17 = ROOT / "SYNTAX" / "17-pattern-matching.md"


def tail_line(path: Path, needle: str) -> str:
    if not path.exists():
        return f"(缺文件 {path.name})"
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return f"(未找到 {needle} 行)"


def blocks(src: str) -> list:
    """[(bug_id, start, end, body)]，按出现顺序 —— BUG-96 有两个抬头，必须按区间而不是编号取。"""
    hits = list(re.finditer(r"(?m)^## (BUG-\d+) ", src))
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(src)
        out.append((m.group(1), m.start(), end, src[m.end():end]))
    return out


def pick(src: str, bid: str, needle: str = "") -> tuple:
    for b, s, e, body in blocks(src):
        if b == bid and (not needle or needle in body):
            return (b, s, e, 1)
    return ("", 0, 0, 0)


def build(src: str, ts: str) -> tuple:
    refuse: list = []
    bl = blocks(src)
    counts = {}
    for b, _, _, _ in bl:
        counts[b] = counts.get(b, 0) + 1

    sect = {}

    ok71 = pick(src, "BUG-71")
    if not ok71[0]:
        refuse.append("BUG-71 抬头缺失 ⇒ 锚点失效")
    else:
        sect["BUG-71"] = f"""### FIXED(R9 组合环 {ts}，ns cypy-loop-20260929) — 追加留档（正文一字未改）

- 机制即卡片所写（`_visit_Subscript` 只看 `hasattr(node.slice,'kind')`，切片是 dict 形态 ⇒ 走不到分支直接返回 `params[0]`）：
  本轮在返回元素类型之前先分辨切片形态，`cypyc/analyzer/type_checker.py` 的 `_is_slice_form()` 只认
  `cypyc/parser/parser.py:3952-3991` 落的那个 `{{"slice": True, …}}` dict（语言里没有独立的 `Slice` AST 节点，
  所以判据只有这一支，不写「万一是节点」的死分支）。
- 规范先行：`SYNTAX/14-syntax-sugar.md` 新增「切片的类型规则（R9 补）」1-3 条 ——
  切片结果=被切容器自身类型；只有下标形态降到元素类型；切片不做越界/常量化判定。现测 {len(SPEC14.read_text(encoding='utf-8').splitlines())} 行。
- R5 那条 `### NOT-FIXED` 的四个卡点逐一补齐：
  ① 锁 = `corpus/cypy.type.slice.json` 8 格 + `tests/regression/test_corpus_pairs.py` 参数化格（成对的另一半：
     `y: int = xs[1:3]` 必须报 `Type mismatch: expected int, got list[int]` 带行列，防止「判据恒绿」）；
  ② 摘掉即红 = `.fist-loop-20260929/verify_r9_locks.py` 的 S1 格（切片形态判断恒假 ⇒ Ω-gate 真红），副本树、逐字节摘回；
  ③ 当前树全绿 = 本段落盘时 pytest 终版结论 `{tail_line(PYTEST_LOG, '====')}`；
  ④ 调用面 = 卡片点名的仓内 DEMO `examples/demos/upcoming_features/planned_features.cypy`
     `transpile --check-only` 由 rc=1（4 条诊断，首条 `Type mismatch: expected list[int], got int at 60:9`）
     变 rc=0，逐字 `{tail_line(DEMO_LOG, '[OK]')}`。
- 未随本段关闭的相邻面：元组可变长切片 `tuple<int, ...>` 仍进不了解析器（账上「语法未落地」那条），
  本条只主张 list/str 与「下标 vs 切片」形态区分这一型已闭。
"""

    for bid in ("BUG-98", "BUG-101", "BUG-104"):
            if not pick(src, bid)[0]:
                refuse.append(f"{bid} 抬头缺失")
                continue
            sect[bid] = f"""### DUPLICATE(R9 组合环 {ts}) — 正身 = BUG-95（R8 已闭）；且本条主张本身已被实测作废

- 主张「`corpus/` 与 `tests/regression/` 在本仓不存在」今天不成立，逐字（`.fist-loop-20260929/logs/r9_stale_a1.txt`）：
  `{tail_line(STALE_LOG, 'CONCLUSION')}`；
  目录实测 `corpus_dir_exists=True regr_dir_exists=True`，跑批 `{tail_line(GATE_LOG, 'CONCLUSION')}`。
- 三条同 summary 的重复登记由 BUG-107 记账（`report_bug` 无幂等键）；此处只指认正身，不改写原文。
- 覆盖面仍未闭的部分另有条目在账（Ω-spec 只覆盖 3 个 op），本段不得被读成「规范落地面已全部闭环」。
"""

    b96dup = pick(src, "BUG-96", "非法标注形态")
    if not b96dup[0]:
        refuse.append("BUG-96（类型标注那一条）按 summary 认不出 ⇒ 不写悬空指认")
    else:
        sect[("BUG-96", "非法标注形态")] = """### DUPLICATE(R9 组合环 {ts}) — 正身 = BUG-108（R7 已闭）

- 本条与 BUG-108 是同一主张（`xs: [int]` 把 AST 节点 repr 落进产物且零诊断）；
  R7 已在 BUG-108 落地注解形态闭集 + 生成器末路退化，并有 `corpus/cypy.annotation.shape.json` 24 格锁。
- 撞号本身（两个 `## BUG-96` 抬头）由 BUG-107 记账，本段不删除任何原文。
""".replace("{ts}", ts)

    b99 = pick(src, "BUG-99")
    if not b99[0]:
        refuse.append("BUG-99 抬头缺失")
    else:
        sect["BUG-99"] = f"""### AMENDMENT(R9 组合环 {ts}) — 拆成两半：可见字段的一半已闭，不可见的一半仍在账

- 已闭的那半（有锁）：类型在本模块可见（生成器登记过 `_class_fields`/`_struct_types`）且实参元数 > 字段数时，
  生成器不再发 `.__f{{i}}` 成员访问，而是让该 `case` 恒不命中（产物末段 `and False`），分析器仍按规则 1 报元数错；
  配套 `SYNTAX/17-pattern-matching.md` 规则 8（现测 {len(SPEC17.read_text(encoding='utf-8').splitlines())} 行）。
  证据格 = `corpus/cypy.pattern.positional.json` 第 #17/#18 格（0 基口径），
  承重 = `verify_r9_locks.py` 的 S2（把该分支退回发 `.__f{{i}}` ⇒ Ω-gate 真红）。
- **未闭的那半**：类型不可见（外部类，规则 4「改由运行期 `__unapply__` 解包路径处理」）时，
  产物仍是 `.__f0/.__f1` 形态 —— 既有锁 `tests/test_extractor_pattern.py::test_extractor_pattern_codegen`
  逐字钉着 `assert "_match_subject_1.__f0" in code`（其源里 `Email` 从未定义 ⇒ 属规则 4 半径）。
  本轮把 S2 的初版直接推广到全形态时**打红了这条既有锁**（逐字：`1 failed, 2211 passed in 359.56s`），
  因此按「不可见类型的运行期解包形态是什么」尚未裁出来收回到只处理可见字段的一半，
  而不是改测试凑绿。该裁决面另立单，本条保持 OPEN。
"""

    b116 = pick(src, "BUG-116")
    if not b116[0]:
        refuse.append("BUG-116 抬头缺失")
    else:
        sect["BUG-116"] = f"""### AMENDMENT(R9 组合环 {ts}) — 覆盖面从 2 op/41 对推进到 3 op/51 对，本条仍 OPEN

- 新增 `corpus/cypy.type.slice.json` 8 格；`cypy.pattern.positional.json` 17→19 格（越界槽位两格）；
  回归件地板 `FLOOR_CASES` 41→51、`FLOOR_SPECS` 2→3，逐字跑批 `{tail_line(GATE_LOG, 'CONCLUSION')}`。
- 仍缺的是「其余 SYNTAX 章节没有 Ω-spec」，本条不被任何闭环段遮蔽；下一轮的判据扩面仍以本条为靶。
"""

    b96first = pick(src, "BUG-96", "无 __unapply__")
    b102 = pick(src, "BUG-102")
    for label, got in (("BUG-96(规范缺口)", b96first), ("BUG-102", b102)):
        if not got[0]:
            refuse.append(f"{label} 按 summary 认不出")
            continue
        sect[(got[0], "无 __unapply__")] = f"""### DUPLICATE(R9 组合环 {ts}) — 正身 = BUG-99

- 与 BUG-99 逐字同 summary（`report_bug` 无幂等键造成的三处双写之一，见 BUG-107）。
- **指认重复不等于缺陷已修**：正身 BUG-99 本段之后仍 OPEN（不可见类型那一半未裁）。
"""

    out = src
    done, skipped = [], []
    for key, section in sect.items():
        bid = key[0] if isinstance(key, tuple) else key
        needle = key[1] if isinstance(key, tuple) else ""
        got = pick(out, bid, needle)
        if not got[0]:
            refuse.append(f"{bid} 区间在写入时失效")
            continue
        _, s, e, _ = got
        marker_head = section.splitlines()[0]
        if marker_head in out[s:e]:
            skipped.append(str(key))
            continue
        out = out[:e] + "\n" + section.rstrip("\n") + "\n" + out[e:]
        done.append(str(key))
    return out, {"refuse": refuse, "appended": done, "skipped_existing": skipped,
                 "header_counts": {k: v for k, v in counts.items() if v > 1},
                 "written_at_utc": ts}


def removed(old: str, new: str) -> list:
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    return [l for t, i1, i2, j1, j2 in sm.get_opcodes() if t in ("delete", "replace")
            for l in old.splitlines()[i1:i2]]


def main() -> int:
    src = LEDGER.read_text(encoding="utf-8")
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    out, meta = build(src, ts)
    bad = removed(src, out)
    if bad:
        meta["refuse"].append(f"存在删除/改写行 {len(bad)} 条，首条：{bad[0][:120]}")
    if meta["refuse"]:
        OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False, indent=1))
        return 1
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    os.replace(tmp, LEDGER)
    back = LEDGER.read_text(encoding="utf-8")
    bl = blocks(back)
    closed = [b for b, _, _, body in bl if re.search(r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)", body)]
    open_blocks = [b for b, _, _, body in bl
                   if not re.search(r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)", body)]
    meta["recheck"] = {"headers": len(bl), "distinct_ids": len({b for b, _, _, _ in bl}),
                       "closed_blocks": len(closed), "open_blocks": len(open_blocks),
                       "open_ids": sorted(set(open_blocks)),
                       "fixed_sections": len(re.findall(r"(?m)^### FIXED\(", back)),
                       "duplicate_sections": len(re.findall(r"(?m)^### DUPLICATE\(", back)),
                       "amendment_sections": len(re.findall(r"(?m)^### AMENDMENT\(", back)),
                       "insert_only_verified": not removed(src, back),
                       "spec14_lines": len(SPEC14.read_text(encoding="utf-8").splitlines()),
                       "spec17_lines": len(SPEC17.read_text(encoding="utf-8").splitlines())}
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    print("CONCLUSION appended=%d open_blocks=%d open_distinct=%d headers=%d insert_only=%s rc=0"
          % (len(meta["appended"]), meta["recheck"]["open_blocks"],
             len(set(meta["recheck"]["open_ids"])), meta["recheck"]["headers"],
             meta["recheck"]["insert_only_verified"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
