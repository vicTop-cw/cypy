#!/usr/bin/env python3
"""T0r258.5.2 自门控探针 —— 附录 A 关键字表 vs `Lexer.KEYWORDS` 的双向一致性（只读，幂等）。

为什么需要它（本轮真实发生过）：`SYNTAX/appendix-A-keywords.md` 的分类表原写「共 61 个」，
而 2026-09-26 实测 `len(Lexer.KEYWORDS)` = 65；实现轮每往词表里加一个词，这张表就漂一律，
且**两个方向都会错**——表漏词（读者以为还能当标识符用）与表多词（读者以为某个词已被保留）。

判据（全部可机检）：
  Y1 MISSING   : `set(KEYWORDS) - set(表)` 非空 —— 词表里有、附录没列
  Y2 PHANTOM   : `set(表) - set(KEYWORDS)` 非空 —— 附录列了、词表里根本没有（幽灵保留字）
  Y3 QUICKREF  : 「关键字速查表」代码块里的词集合与分类表不一致（同一文件内部打架）

退出码：0 = 全部一致；1 = 任一 Y1~Y3 命中（缺陷仍在）；2 = 探针自身读不到文件/词表。

**为什么没有「文内总数必须等于 len(KEYWORDS)」这条门**：总数是**散文**，实测这一份文件里
`[0-9]+ ?个|词` 命中三处 ——「原写的『共 61 个』」（描述**修正前**的历史值，本身就该不等于 65）、
「分为 11 个类别」（类别数，不是词数）、以及「去重 **65** 词」。把它写成硬门得到的是一条
**必然误报**的判据，下一轮只要改写这段说明文字就得回来放宽它——判据与措辞耦合是这个仓库
已经付过学费的失败模式（见 `feat_anchor_01.py` 的 `criteria_health()` 与轮报告 §2.5）。
词表与两张清单（分类表、速查表）的集合相等才是可判定的不变量，总数只作 INFO 打印。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:                                    # 与同目录其它探针一致：落盘日志固定 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                       # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
APPENDIX = ROOT / "SYNTAX" / "appendix-A-keywords.md"

ROW = re.compile(r"^\|\s*`([A-Za-z_][A-Za-z_0-9]*)`\s*\|")
TOTAL = re.compile(r"(\d+)\s*(?:个|词)")
QUICKREF = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*(?:\s+[A-Za-z_][A-Za-z_0-9]*)*)\s*$")


def load_keywords():
    sys.path.insert(0, str(ROOT))
    from cypyc.parser.lexer import Lexer
    return set(Lexer.KEYWORDS)


def main() -> int:
    if not APPENDIX.is_file():
        print("[docs-02] 读不到 %s —— 判据自身出错" % APPENDIX)
        return 2
    try:
        lex = load_keywords()
    except Exception as exc:                                   # noqa: BLE001
        print("[docs-02] 导入 Lexer.KEYWORDS 失败：%r —— 判据自身出错" % exc)
        return 2

    text = APPENDIX.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    table_words, order = set(), []
    for line in lines:
        m = ROW.match(line)
        if m and m.group(1) not in table_words:
            table_words.add(m.group(1))
            order.append(m.group(1))

    # 速查表：`## 关键字速查表` 之后第一个围栏代码块
    quick = set()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("## 关键字速查表"))
        fence = [i for i, l in enumerate(lines[start:], start) if l.startswith("```")]
        if len(fence) >= 2:
            for l in lines[fence[0] + 1:fence[1]]:
                qm = QUICKREF.match(l)
                if qm:
                    quick |= set(qm.group(1).split())
    except StopIteration:
        pass

    print("[docs-02] Lexer.KEYWORDS 实测 %d 词；附录分类表 %d 行（去重 %d 词）；速查表 %d 词"
          % (len(lex), len([1 for l in lines if ROW.match(l)]), len(table_words), len(quick)))

    findings = []
    missing = sorted(lex - table_words)
    phantom = sorted(table_words - lex)
    if missing:
        findings.append(("Y1 MISSING", "词表里有、附录没列：%s" % ", ".join(missing)))
    if phantom:
        findings.append(("Y2 PHANTOM", "附录列了、词表里没有：%s" % ", ".join(phantom)))
    if quick and quick != table_words:
        findings.append(("Y3 QUICKREF", "速查表与分类表不一致：只在速查表=%s / 只在分类表=%s"
                         % (sorted(quick - table_words)[:6], sorted(table_words - quick)[:6])))

    for code, why in findings:
        print("  [%s] %s" % (code, why))
    print("-" * 78)
    if findings:
        print("REPRODUCED —— 附录 A 与词表不一致 %d 类（Y1~Y3）。" % len(findings))
        return 1
    print("NOT-REPRODUCED —— 附录 A 分类表与速查表均与 Lexer.KEYWORDS(%d) 双向一致。"
          % len(lex))
    print("INFO 文内出现的「N 个/N 词」原文（不作门，见模块 docstring）：")
    for line in lines:
        if TOTAL.search(line) and not line.startswith("#"):
            print("     %s" % line.strip()[:88])
    return 0


if __name__ == "__main__":
    sys.exit(main())
