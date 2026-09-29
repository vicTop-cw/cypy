import re
from math import gcd as _gcd
from typing import Optional, Tuple


class IndentDetector:
    def __init__(self):
        self.indent_type = "spaces"
        self.indent_size = 4

    def detect(self, source: str) -> Tuple[str, int]:
        lines = source.split("\n")
        indent_counts = []

        for line in lines:
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                if indent > 0:
                    indent_counts.append(indent)

        if not indent_counts:
            return self.indent_type, self.indent_size

        for line in lines:
            if "\t" in line[:len(line) - len(line.lstrip())]:
                self.indent_type = "tabs"
                self.indent_size = 4
                return self.indent_type, self.indent_size

        # BUG-28: 观测到多种宽度时一律取 4，会让 2 空格风格的第一层体在
        # normalize() 的 `indent // size` 里塌成 0 层（块结构被毁）。层数单位应是
        # 观测宽度的最大公约数：{2,4}->2、{3,6}->3、{4,8}->4。
        common_indents = set(indent_counts)
        size = 0
        for value in sorted(common_indents):
            size = value if not size else _gcd(size, value)
        self.indent_size = size or 4

        self.indent_type = "spaces"
        return self.indent_type, self.indent_size

    def normalize(self, source: str) -> str:
        self.detect(source)
        lines = source.split("\n")
        result = []
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                prefix = line[:len(line) - len(stripped)]
                if self.indent_type == "tabs":
                    # 单位必须是“列”而不是“字符数”：cypyc/parser/lexer.py:419-420
                    # 以 1 tab == 4 列展开，detect() 也因此对 tab 缩进报告
                    # indent_size == 4。先把前导空白换算成列，再按 indent_size 取层，
                    # 于是 1 个 tab -> 4 列 -> 1 层（旧实现直接用字符数 //4，
                    # 使 1~3 个 tab 全部塌缩成 0 层）。
                    size = self.indent_size or 4
                    columns = sum(4 if ch == "\t" else 1 for ch in prefix)
                    new_indent = "\t" * (columns // size)
                else:
                    original_indent = len(prefix)
                    new_indent = " " * self.indent_size * (original_indent // self.indent_size)
                result.append(new_indent + stripped)
            else:
                result.append(line)
        return "\n".join(result)
