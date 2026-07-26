from typing import List, Optional, Dict, Any


# 错误代码定义
class ErrorCode:
    """错误代码分类"""
    # 解析器错误
    PARSE_UNEXPECTED_TOKEN = "PARSE001"
    PARSE_MISSING_COLON = "PARSE002"
    PARSE_UNMATCHED_PAREN = "PARSE003"
    PARSE_UNEXPECTED_EOF = "PARSE004"
    PARSE_INVALID_ASSIGNMENT = "PARSE005"
    
    # 作用域错误
    SCOPE_UNDEFINED_NAME = "SCOPE001"
    SCOPE_REDEFINED_NAME = "SCOPE002"
    SCOPE_OUT_OF_SCOPE = "SCOPE003"
    SCOPE_INVALID_NESTING = "SCOPE004"
    SCOPE_STRUCT_NOT_TOP_LEVEL = "SCOPE005"
    SCOPE_ENUM_NOT_TOP_LEVEL = "SCOPE006"
    
    # 类型错误
    TYPE_INCOMPATIBLE = "TYPE001"
    TYPE_MISSING_ANNOTATION = "TYPE002"
    TYPE_UNDEFINED_TYPE = "TYPE003"
    TYPE_INVALID_OPERATION = "TYPE004"
    TYPE_INCOMPATIBLE_RETURN = "TYPE005"
    TYPE_IMMUTABLE_REASSIGN = "TYPE006"
    TYPE_INVALID_CAST = "TYPE007"
    TYPE_MISSING_CAST_METHOD = "TYPE008"
    
    # 语法错误
    SYNTAX_INVALID_STRUCT = "SYNTAX001"
    SYNTAX_INVALID_ENUM = "SYNTAX002"
    SYNTAX_INVALID_FUNC = "SYNTAX003"
    SYNTAX_INVALID_CLASS = "SYNTAX004"
    SYNTAX_INVALID_CONST = "SYNTAX005"
    SYNTAX_INVALID_LET = "SYNTAX006"
    
    # 编译错误
    COMPILE_FAILED = "COMPILE001"
    COMPILE_MISSING_DEPENDENCY = "COMPILE002"
    
    # 运行时错误
    RUNTIME_ERROR = "RUNTIME001"


# 错误修复建议映射
ERROR_SUGGESTIONS: Dict[str, List[str]] = {
    ErrorCode.SCOPE_UNDEFINED_NAME: [
        "检查变量名是否拼写正确",
        "确保变量在使用前已定义",
        "如果是外部导入，请确认import语句正确"
    ],
    ErrorCode.SCOPE_REDEFINED_NAME: [
        "使用不同的变量名",
        "如果需要重新赋值，移除重复的定义语句"
    ],
    ErrorCode.SCOPE_STRUCT_NOT_TOP_LEVEL: [
        "结构体只能在模块顶级定义",
        "将结构体定义移到函数或类之外"
    ],
    ErrorCode.SCOPE_ENUM_NOT_TOP_LEVEL: [
        "枚举只能在模块顶级定义",
        "将枚举定义移到函数或类之外"
    ],
    ErrorCode.TYPE_INCOMPATIBLE: [
        "检查操作数的类型是否匹配",
        "考虑使用类型转换（as Type）",
        "确认函数返回类型与期望类型一致"
    ],
    ErrorCode.TYPE_MISSING_ANNOTATION: [
        "为变量添加类型注解，如: x: int = 0",
        "def函数中，有类型注解的参数会生成优化代码"
    ],
    ErrorCode.TYPE_UNDEFINED_TYPE: [
        "检查类型名称是否拼写正确",
        "确认类型已定义或已导入",
        "如果是自定义类型，确保定义在使用前"
    ],
    ErrorCode.TYPE_IMMUTABLE_REASSIGN: [
        "let声明的变量不可重新赋值",
        "如果需要重新赋值，使用普通赋值 x = value",
        "考虑使用mut关键字（如果支持）"
    ],
    ErrorCode.TYPE_INVALID_CAST: [
        "检查类型转换的源类型和目标类型",
        "基本类型之间可以直接转换",
        "自定义类型需要定义__cast__方法"
    ],
    ErrorCode.TYPE_MISSING_CAST_METHOD: [
        "为源类型定义__cast__[TargetType]方法",
        "或使用__try_cast__[TargetType]方法返回可选结果"
    ],
    ErrorCode.PARSE_UNEXPECTED_TOKEN: [
        "检查语法是否正确",
        "确认所有括号和引号已正确匹配",
        "查看该行前后是否有遗漏的符号"
    ],
    ErrorCode.SYNTAX_INVALID_STRUCT: [
        "结构体只能在模块顶级定义",
        "结构体字段需要类型注解",
        "结构体方法需要正确的参数列表"
    ],
    ErrorCode.SYNTAX_INVALID_CONST: [
        "const常量必须有初始值",
        "const只能在模块级别声明",
        "const值在编译期确定，不能是运行时计算"
    ],
    ErrorCode.SYNTAX_INVALID_LET: [
        "let声明的变量不可重新赋值",
        "如果需要可变变量，使用普通赋值 x = value",
        "let变量必须在声明时初始化"
    ],
}


class ErrorMessage:
    def __init__(self, level: str, message: str, line: int = 0, col: int = 0, file: str = "", 
                 error_code: str = "", suggestion: str = ""):
        self.level = level
        self.message = message
        self.line = line
        self.col = col
        self.file = file
        self.error_code = error_code
        self.suggestion = suggestion

    def __repr__(self) -> str:
        parts = []
        
        # 位置信息
        location = ""
        if self.file:
            location += f"{self.file}"
        if self.line > 0:
            if location:
                location += ":"
            location += f"{self.line}"
            if self.col > 0:
                location += f":{self.col}"
        if location:
            parts.append(f"\033[34m{location}\033[0m")
        
        # 级别和错误代码
        level_color = {
            "error": "\033[31m",
            "warning": "\033[33m",
            "info": "\033[32m"
        }
        level_text = f"{level_color.get(self.level, '')}{self.level.upper()}\033[0m"
        
        if self.error_code:
            parts.append(f"{level_text} \033[35m[{self.error_code}]\033[0m")
        else:
            parts.append(level_text)
        
        # 错误消息
        parts.append(self.message)
        
        # 修复建议
        if self.suggestion:
            parts.append(f"\n  \033[36mHint:\033[0m {self.suggestion}")
        
        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于JSON输出）"""
        return {
            "level": self.level,
            "message": self.message,
            "line": self.line,
            "col": self.col,
            "file": self.file,
            "error_code": self.error_code,
            "suggestion": self.suggestion
        }


class ErrorReporter:
    def __init__(self):
        self.errors: List[ErrorMessage] = []
        self.warnings: List[ErrorMessage] = []
        self.infos: List[ErrorMessage] = []

    def error(self, message: str, line: int = 0, col: int = 0, file: str = "", 
              error_code: str = "", suggestion: str = "") -> None:
        """添加错误消息"""
        # 如果没有提供建议，尝试从错误代码获取
        if not suggestion and error_code in ERROR_SUGGESTIONS:
            suggestion = "；".join(ERROR_SUGGESTIONS[error_code])
        
        self.errors.append(ErrorMessage("error", message, line, col, file, error_code, suggestion))

    def warning(self, message: str, line: int = 0, col: int = 0, file: str = "", 
                error_code: str = "", suggestion: str = "") -> None:
        """添加警告消息"""
        if not suggestion and error_code in ERROR_SUGGESTIONS:
            suggestion = "；".join(ERROR_SUGGESTIONS[error_code])
        
        self.warnings.append(ErrorMessage("warning", message, line, col, file, error_code, suggestion))

    def info(self, message: str, line: int = 0, col: int = 0, file: str = "") -> None:
        """添加信息消息"""
        self.infos.append(ErrorMessage("info", message, line, col, file))

    def report(self, colored: bool = True) -> str:
        """生成格式化的错误报告"""
        if not colored:
            # 移除颜色代码
            import re
            clean_report = self._generate_report()
            return re.sub(r'\033\[\d+m', '', clean_report)
        return self._generate_report()

    def _generate_report(self) -> str:
        """生成带颜色的错误报告"""
        lines = []
        
        if self.errors:
            lines.append(f"\n\033[1mErrors ({len(self.errors)}):\033[0m")
            for i, msg in enumerate(self.errors, 1):
                lines.append(f"{i}. {msg}")
        
        if self.warnings:
            lines.append(f"\n\033[1mWarnings ({len(self.warnings)}):\033[0m")
            for i, msg in enumerate(self.warnings, 1):
                lines.append(f"{i}. {msg}")
        
        if self.infos:
            lines.append(f"\n\033[1mInfo ({len(self.infos)}):\033[0m")
            for msg in self.infos:
                lines.append(f"  {msg}")
        
        return "\n".join(lines)

    def report_json(self) -> str:
        """生成JSON格式的错误报告"""
        import json
        data = {
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "infos": [i.to_dict() for i in self.infos],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "info_count": len(self.infos)
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

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
    
    def merge(self, other: 'ErrorReporter') -> None:
        """合并另一个错误报告器的结果"""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.infos.extend(other.infos)
