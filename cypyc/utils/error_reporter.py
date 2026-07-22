from typing import List, Optional


class ErrorMessage:
    def __init__(self, level: str, message: str, line: int = 0, col: int = 0, file: str = ""):
        self.level = level
        self.message = message
        self.line = line
        self.col = col
        self.file = file

    def __repr__(self) -> str:
        location = ""
        if self.file:
            location += f"{self.file}:"
        if self.line > 0:
            location += f"{self.line}"
            if self.col > 0:
                location += f":{self.col}"
        if location:
            return f"{location}: {self.level}: {self.message}"
        return f"{self.level}: {self.message}"


class ErrorReporter:
    def __init__(self):
        self.errors: List[ErrorMessage] = []
        self.warnings: List[ErrorMessage] = []
        self.infos: List[ErrorMessage] = []

    def error(self, message: str, line: int = 0, col: int = 0, file: str = "") -> None:
        self.errors.append(ErrorMessage("error", message, line, col, file))

    def warning(self, message: str, line: int = 0, col: int = 0, file: str = "") -> None:
        self.warnings.append(ErrorMessage("warning", message, line, col, file))

    def info(self, message: str, line: int = 0, col: int = 0, file: str = "") -> None:
        self.infos.append(ErrorMessage("info", message, line, col, file))

    def report(self) -> str:
        lines = []
        for msg in self.errors + self.warnings + self.infos:
            lines.append(str(msg))
        return "\n".join(lines)

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def get_error_count(self) -> int:
        return len(self.errors)

    def get_warning_count(self) -> int:
        return len(self.warnings)

    def clear(self) -> None:
        self.errors = []
        self.warnings = []
        self.infos = []
