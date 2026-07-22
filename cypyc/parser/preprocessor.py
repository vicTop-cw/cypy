import re
from typing import List, Tuple


class Preprocessor:
    def __init__(self):
        self.macros = {}
        self.include_paths = []

    def add_macro(self, name: str, value: str) -> None:
        self.macros[name] = value

    def set_include_paths(self, paths: List[str]) -> None:
        self.include_paths = paths

    def process(self, source: str) -> str:
        source = self._process_includes(source)
        source = self._process_macros(source)
        source = self._process_line_directives(source)
        return source

    def _process_includes(self, source: str) -> str:
        lines = source.split("\n")
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            match = re.match(r"^\s*#include\s+[\"<](.+)[\">]", line)
            if match:
                include_file = match.group(1)
                included_content = self._read_include_file(include_file)
                if included_content:
                    result.append(included_content)
            else:
                result.append(line)
            i += 1
        return "\n".join(result)

    def _read_include_file(self, filename: str) -> str:
        for path in self.include_paths:
            try:
                with open(f"{path}/{filename}", "r", encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                continue
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def _process_macros(self, source: str) -> str:
        for name, value in self.macros.items():
            source = source.replace(name, value)
        return source

    def _process_line_directives(self, source: str) -> str:
        return source

    def extract_metadata(self, source: str) -> dict:
        metadata = {
            "version": None,
            "requires": [],
            "features": [],
        }
        lines = source.split("\n")
        for line in lines:
            match = re.match(r"^\s*#pragma\s+cypy\s+(\w+)\s*=\s*(.+)", line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                if key == "version":
                    metadata["version"] = value
                elif key == "requires":
                    metadata["requires"] = [r.strip() for r in value.split(",")]
                elif key == "features":
                    metadata["features"] = [f.strip() for f in value.split(",")]
        return metadata
