"""R4-修复 的认领表：十张单（BUG-61..BUG-70）逐张从**盘上账本**反解，给出归属与理由。

三条自证：
① 号与标题从 `memory/bugs.md` 现读，不抄计划（计划里的括号标注与真实号可能错位）；
② 每张单必须有归属（本环可修 / 交人工 / 转下一环），且「本环可修」的要在改动集里真的出现；
③ 「交人工/转下一环」的必须写理由，理由要能指回它自己的定位（冻结面 / 需真编译 / 不可逆结构改动）。
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "fix_r4_claim.json"
REFUSE: list = []
CHECKS: list = []

# 归属口径：fix=本环改产品码/文档；handoff=交人工（冻结面或不可逆）；next=转下一环（需授权或需真编译）
DISPOSITION = {
    61: ("fix", "分析器内部机制，不碰 PROJECT-SPEC/SYNTAX 冻结语义；已有成对锁（C01..C05）"),
    62: ("fix", "与 61 共用同一张可调用签名表，判据入口只有 `_callable_arg_mismatch` 一个"),
    63: ("fix", "`self` 绑定不再被 object 覆盖 + 属性位 Callable 复用同一套判定；61/62 的锁不受牵连"),
    64: ("fix", "显示层新增 `_type_display`/`_mismatch` 统一出口，判定仍用 Type 对象（不把文案当语义）"),
    65: ("handoff", "appendix-C 特性表与主类型表在 `SYNTAX/`、`PROJECT-SPEC/` 冻结面内 ⇒ 只挂账不动刀"),
    66: ("fix", "`docs/USAGE.md` 不是冻结面：把不存在的旗标、未记选项与转述错按 argparse 实读改写"),
    67: ("fix", "文档示例引用不存在的符号 ⇒ 按实现真形状改写（非冻结面）"),
    68: ("next", "改缓存根目录会影响既有 .pyd 命中路径，需与 69 一起做真编译验证（要授权）"),
    69: ("next", "生成的 C 与 Cython 等价性要 MSVC 真编译才能判，本轮无授权 ⇒ 转 R4-验证 申请"),
    70: ("handoff", "拆分 parser.py/cython_generator.py 是不可逆结构改动 ⇒ 交人工排专门结构轮"),
}
REF = {"61": "RC1", "62": "RC2", "63": "RC3", "64": "RC4"}


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def read_cards() -> dict:
    """逐条目标题切块，块内取第一行 `- summary:`。

    反面教训：`^## BUG-(\\d+) .*?\\n- summary: (.*)` 配 `re.S` 时，贪婪的 `(.*)` 会一路吃到
    全文最后一个 `\\n- ` ⇒ 整个 70 条账本只反解出 **1 张**卡（BUG-1），其余 69 张在判据眼里
    "不存在"。这里改成显式按下一条标题切块，并在 main 里断言条数，避免又一次静默少读。
    """
    md = LEDGER.read_text(encoding="utf-8")
    cards = {}
    heads = list(re.finditer(r"^## BUG-(\d+) [^\n]*\n", md, re.M))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        s = re.search(r"^- summary: (.*)$", md[m.end():end], re.M)
        if s:
            cards[int(m.group(1))] = s.group(1).strip()
    return cards


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    cards = read_cards()
    headings = len(re.findall(r"^## BUG-\d+",
                              LEDGER.read_text(encoding="utf-8"), re.M))
    check("反解条目数必须等于盘上标题数（读少了我不知道）",
          len(cards), headings, f"反解 {len(cards)} / 标题 {headings}")
    missing = [n for n in DISPOSITION if n not in cards]
    if missing:
        REFUSE.append(f"账本里找不到这些号：{missing}")
    # git 改动面（未跟踪 + 已改）用来正面证明「标 fix 的单确实动了东西」
    diff = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    touched = set((diff.stdout or "").splitlines())
    core = "cypyc/analyzer/type_checker.py"
    rows = []
    for n, (disp, why) in sorted(DISPOSITION.items()):
        key = ""
        m = re.match(r"\[([^\]]+)\]", cards.get(n, ""))
        if m:
            key = m.group(1)
        rows.append({"number": f"BUG-{n}", "root_cause_key": key, "disposition": disp,
                     "reason": why, "summary": cards.get(n, "")[:220]})
    fix_rows = [r for r in rows if r["disposition"] == "fix"]
    code_fixed = [r["number"] for r in fix_rows if r["root_cause_key"].startswith("RC")]
    doc_fixed = [r["number"] for r in fix_rows if r["root_cause_key"].startswith("DOC")]
    handoff = [r["number"] for r in rows if r["disposition"] == "handoff"]
    next_round = [r["number"] for r in rows if r["disposition"] == "next"]
    check("十个号全部有归属", len(rows), 10, f"实测 {len(rows)} 行")
    check("分析器四单标为本环可修", code_fixed, ["BUG-61", "BUG-62", "BUG-63", "BUG-64"],
          "按 root_cause_key=RC* 反解")
    check("文档两单标为本环可修", doc_fixed, ["BUG-66", "BUG-67"], "按 root_cause_key=DOC* 反解")
    check("核心文件在改动集里（正面证明不是空口认领）", core in touched, True,
          f"git diff 前 6 项：{sorted(touched)[:6]}")
    check("每条理由都非空", [bool(r["reason"]) for r in rows], [True] * len(rows), "归属不能无理由")
    doc_rows = [r for r in fix_rows if not r["root_cause_key"].startswith("RC")]
    docs_touched = [p for p in touched if p.startswith("docs/")]
    if doc_rows and not docs_touched:
        REFUSE.append(f"标了可修 {len(doc_rows)} 张文档单，但 docs/ 一个文件都没改：{doc_rows}")

    refuse = sorted(set(REFUSE)) + [f"自证未过：{c['label']}（实得 "
                                    f"{json.dumps(c['got'], ensure_ascii=False)[:200]}）"
                                    for c in CHECKS if not c["ok"]]
    doc = {"started": started, "ledger": "memory/bugs.md", "rows": rows,
           "fixed_code": code_fixed, "fixed_docs": doc_fixed, "docs_touched": docs_touched,
           "handoff": handoff, "next_round": next_round,
           "note": "计划里对 BUG-66/67 的括号标注与实际号有错位（真实 66/67 是文档面、68 才是 bridge 缓存）"
                   "⇒ 本表一律按盘上标题反解，不按计划文字",
           "refuse": refuse,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse, "fixed_code": code_fixed, "fixed_docs": doc_fixed,
                      "handoff": handoff, "next": next_round, "docs_touched": docs_touched},
                     ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
