import re
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

        common_indents = set(indent_counts)
        if len(common_indents) == 1:
            self.indent_size = list(common_indents)[0]
        else:
            self.indent_size = 4

        self.indent_type = "spaces"
        return self.indent_type, self.indent_size

    def normalize(self, source: str) -> str:
        self.detect(source)
        lines = source.split("\n")
        result = []
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                original_indent = len(line) - len(stripped)
                if self.indent_type == "tabs":
                    new_indent = "\t" * (original_indent // 4)
                else:
                    new_indent = " " * self.indent_size * (original_indent // self.indent_size)
                result.append(new_indent + stripped)
            else:
                result.append(line)
        return "\n".join(result)
