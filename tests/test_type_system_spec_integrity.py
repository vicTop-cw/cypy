"""三件套规范 `SYNTAX/33-...` 的**内部自洽**判据（T0r258.3.2 的收口门）。

规范是下一轮实现者唯一的输入，所以它必须自己咬得住：条款号被引用却没定义、
裁决表漏项，都会把「按规范开工」变成靠猜。两条判据都**只依赖文本结构**，
不依赖实现状态 —— 实现转绿后它们依然成立（不像「某关键字尚未进 KEYWORDS」
那种修完必反的探针，见 reports/2026-09-26 §2.5）。
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "SYNTAX" / "33-type-constraints-subtypes-dispatch.md"

ID = r"D-[a-z][a-z0-9]*|[PCS]-[0-9]+(?:\.[0-9]+)?'|[PCS]-[0-9]+(?:\.[0-9]+)?"


def _defined(text: str) -> set:
    """条款 id 的「定义处」：标题（含括号里的家族号）、条目/表格行的加粗开头、
    以及 `**2.2.1 xxx**` 这种小节内加粗子条款号。"""
    found = set()
    for line in text.splitlines():
        heads = [line] if line.startswith("#") else []
        if line.startswith("#"):
            found |= {"§" + m for m in re.findall(r"^#{2,4}\s*([0-9]+(?:\.[0-9]+)*)", line)}
        for h in heads:
            found |= set(re.findall(r"(?<![A-Za-z0-9-])(%s)" % ID, h))
        for m in re.finditer(r"^\s*[*-]\s*\*\*\s*(%s)" % ID, line):
            found.add(m.group(1))
        for m in re.finditer(r"^\|\s*\*\*(%s)\*\*" % ID, line):
            found.add(m.group(1))
        for m in re.finditer(r"^\s*[*-]\s*\*\*\s*(\d+\.\d+(?:\.\d+)?)\s", line):
            found.add("§" + m.group(1))
    return found


def _referenced(text: str) -> set:
    refs = set(re.findall(r"\b(%s)\b" % ID, text))
    refs |= {"§" + m for m in re.findall(r"§\s*([0-9]+(?:\.[0-9]+)*)", text)}
    return refs


class TestSpecSelfConsistency:

    def test_spec_present_and_non_trivial(self):
        text = SPEC.read_text(encoding="utf-8")
        assert len(text) > 20000, "规范文件异常短，判据没有可比对象"

    def test_no_dangling_clause_references(self):
        text = SPEC.read_text(encoding="utf-8")
        defined = _defined(text)
        dangling = sorted(r for r in _referenced(text) if r not in defined)
        assert not dangling, (
            "规范引用了未定义的条款号/节号（实现者会按这些号找条款）: %s" % ", ".join(dangling))

    def test_detector_itself_bites(self):
        """开关对照：检测器必须能报出人造的悬空条款号（否则上一条测试是空转）。"""
        sample = ("## 7. 缺口与裁决清单\n\n"
                  "### 9.1 语法（S-9）\n\n"
                  "* 引用了从未定义的 **P-9.9**，也没有 §9.2。\n"
                  "* **P-9.1 定义过的条款**不应被报出。\n")
        defined = _defined(sample)
        dangling = sorted(r for r in _referenced(sample) if r not in defined)
        assert "P-9.9" in dangling and "§9.2" in dangling, dangling
        assert "S-9" not in dangling, dangling       # 定义在标题括号里
        assert "P-9.1" not in dangling, dangling     # 定义在条目加粗开头

    def test_rulings_cover_every_open_decision(self):
        text = SPEC.read_text(encoding="utf-8")
        table = text.split("## 7. 缺口与裁决清单", 1)
        assert len(table) == 1 + 1, "§7 裁决清单不见了，实现单元的前置门失效"
        body = table[1]
        decided = set(re.findall(r"^\|\s*\*\*(D-[a-z0-9]+)\*\*", body, re.M))
        assert {"D-0", "D-1", "D-2", "D-3", "D-4", "D-5", "D-6",
                "D-7", "D-8", "D-9"} <= decided, (
            "§7/§7.1 的裁决覆盖不全，缺: %s"
            % sorted({"D-0", "D-1", "D-2", "D-3", "D-4", "D-5", "D-6",
                      "D-7", "D-8", "D-9"} - decided))
        assert "### 7.1 指挥官裁决" in body, "§7.1 裁决小节不见了"
