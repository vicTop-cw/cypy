"""Cypy 预处理器：#include 解析与 #define 宏替换。

安全契约（2026-Q3 审计 T0r61.2.2 修复）：

* ``#include`` 的文件名只能在配置的搜索根（:meth:`Preprocessor.set_include_paths`）
  内解析。绝对路径、盘符路径、UNC，以及任何带 ``..`` 上溯的写法都直接报
  :class:`IncludeEscape`；解析后还会用 ``realpath`` 再做一次“是否落在某个搜索根
  之内”的包含性检查，避免符号链接 / ``a/../b`` 之类的规范化后逃逸。
* 配置了搜索根时，找不到的 include 是硬错误（:class:`IncludeNotFound`），不再被静默吞掉。
* **未配置搜索根时保留旧的宽松行为**：``cypy_hook/hook.py:91`` 与 ``:212`` 构造
  ``Preprocessor()`` 后直接调用 ``process()``，include_paths 为空。此时若也报
  “找不到就出错”，会把普通构建变成硬失败，因此这种形态仍按当前工作目录相对读取
  （并限制在 CWD 之内），读不到才静默跳过；但绝对路径与 ``..`` 逃逸同样被拒绝。

宏替换（:meth:`Preprocessor._process_macros`）在词法单元层面进行：字符串字面量与
注释中的标识符不会被改写，替换值也不会被再次扫描（见 :func:`iter_code_chunks`）。
"""

import os
import re
from typing import List, Iterator, Tuple

# 字符串字面量 / 注释 的词法扫描（用于“只在代码上下文里做替换”）
_STR_PREFIX = r'[rbfuRBFU]{0,2}'
_TOKEN_RE = re.compile(
    _STR_PREFIX + r'"""(?:\\.|[^"\\])*?"""'      # 三引号字符串
    + '|' + _STR_PREFIX + r"'''(?:\\.|[^'\\])*?'''"
    + '|' + _STR_PREFIX + r'"(?:\\.|[^"\\\n])*"'  # 单行字符串
    + '|' + _STR_PREFIX + r"'(?:\\.|[^'\\\n])*'"
    + r'|\#[^\n]*'                        # Cypy/Python 风格注释
    + r'|//[^\n]*'                        # C 风格行注释
    + r'|/\*.*?\*/'                       # C 风格块注释
    , re.DOTALL)

_ABSOLUTE_NAME_RE = re.compile(r'^(?:[A-Za-z]:[\\/]|[/\\]|\\\\)')
_IDENT_FULL_RE = re.compile(r'[A-Za-z_]\w*')


class IncludeError(Exception):
    """#include 无法安全解析（路径逃逸搜索根或文件不存在）。"""


class IncludeEscape(IncludeError):
    """#include 试图逃出配置的搜索根（绝对路径 / ".." 上溯 / 符号链接）。"""


class IncludeNotFound(IncludeError):
    """配置了搜索根，但没有任何搜索根下存在该文件。"""


def iter_code_chunks(source: str) -> Iterator[Tuple[bool, str]]:
    """把源码切成 (是否代码上下文, 文本) 序列。

    字符串字面量与注释返回 ``(False, text)``，其余连续文本返回 ``(True, text)``，
    使调用方能够在“词法单元”而非“原始字符流”上做替换。代码上下文保持为整块文本，
    因此 ``$name`` 这类跨字符的记号不会被拆开。
    """
    pos = 0
    for match in _TOKEN_RE.finditer(source):
        if match.start() > pos:
            yield True, source[pos:match.start()]
        yield False, match.group(0)
        pos = match.end()
    if pos < len(source):
        yield True, source[pos:]


def mask_names(text: str, names: List[str]) -> str:
    """把待替换的名字换成占位符（配合 :func:`apply_values` 使用，长名优先）。"""
    if not text:
        return text
    for index, needle in enumerate(names):
        if needle:
            text = text.replace(needle, f'\x00CYPYSUB{index}\x00')
    return text


def apply_values(text: str, values: List[str]) -> str:
    """占位符 -> 替换值：整个替换流程的最后一步，插入的文本不再被扫描。"""
    for index, value in enumerate(values):
        text = text.replace(f'\x00CYPYSUB{index}\x00', value)
    return text


def serialize_string_literal(value: str, prefix: str = None) -> str:
    """把已解码的字符串内容重新序列化为可被 Cypy 词法分析器读回的字面量。

    只转义 Cypy 词法分析器会还原的序列（``\\\\``、引号、``\\n``、``\\r``、``\\t``），
    其余字符原样输出，保证 ``字面量 -> lexer -> 值`` 往返一致。
    """
    quote = "'" if ('"' in value and "'" not in value) else '"'
    escaped = value.replace('\\', '\\\\')
    escaped = escaped.replace(quote, '\\' + quote)
    escaped = escaped.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return f'{prefix or ""}{quote}{escaped}{quote}'


def substitute_identifiers(text: str, values: dict) -> str:
    """按词边界替换标识符形式的宏名；字符串/注释上下文原样保留，替换值不再被扫描。"""
    if not values or not text:
        return text
    out = []
    for is_code, chunk in iter_code_chunks(text):
        if not is_code:
            out.append(chunk)
            continue
        out.append(re.sub(
            r'[A-Za-z_]\w*',
            lambda m: str(values[m.group(0)]) if m.group(0) in values else m.group(0),
            chunk))
    return "".join(out)


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

    # ------------------------------------------------------------------ #
    # include 路径校验
    # ------------------------------------------------------------------ #
    def _resolved_roots(self) -> List[str]:
        roots = []
        for path in self.include_paths:
            try:
                roots.append(os.path.realpath(os.path.abspath(str(path))))
            except OSError:                       # 无效路径：跳过该根
                continue
        return roots

    @staticmethod
    def _is_absolute_name(name: str) -> bool:
        return bool(_ABSOLUTE_NAME_RE.match(name)) or os.path.isabs(name)

    @staticmethod
    def _has_parent_reference(name: str) -> bool:
        return any(part == ".." for part in name.replace("\\", "/").split("/"))

    @staticmethod
    def _is_inside(candidate: str, root: str) -> bool:
        """realpath 之后的包含性判断（Windows 下忽略大小写与盘符差异）。"""
        cand = os.path.normcase(os.path.realpath(candidate))
        base = os.path.normcase(os.path.realpath(root))
        try:
            rel = os.path.relpath(cand, base)
        except ValueError:                        # 不同盘符，无公共路径
            return False
        return rel == os.curdir or (
            not os.path.isabs(rel)
            and rel != os.pardir
            and not rel.startswith(os.pardir + os.sep)
        )

    def _read_include_file(self, filename: str) -> str:
        name = filename.strip()
        if not name:
            raise IncludeError("Empty #include filename: a quoted or bracketed path is required")
        if self._is_absolute_name(name):
            raise IncludeEscape(
                f"#include rejects absolute path {name!r}: include files resolve only inside the configured search roots")
        if self._has_parent_reference(name):
            raise IncludeEscape(
                f"#include rejects parent-traversal path {name!r}: escaping the include search roots is not allowed")

        roots = self._resolved_roots()
        if roots:
            for root in roots:
                candidate = os.path.realpath(os.path.join(root, name))
                if not self._is_inside(candidate, root):
                    raise IncludeEscape(
                        f"#include {name!r} resolves outside the search root ({candidate}), rejected")
                if os.path.isfile(candidate):
                    with open(candidate, "r", encoding="utf-8") as f:
                        return f.read()
            raise IncludeNotFound(
                f"#include {name!r} not found in any include search root: {', '.join(roots)}")

        # 未配置搜索根（cypy_hook 形态）：保持宽松的 CWD 相对读取，
        # 但仍拒绝逃出当前工作目录的写法；读不到时沿用旧的静默跳过行为。
        base = os.path.realpath(os.getcwd())
        candidate = os.path.realpath(os.path.join(base, name))
        if not self._is_inside(candidate, base):
            raise IncludeEscape(
                f"#include {name!r} resolves outside the working directory ({candidate}), rejected")
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def _process_macros(self, source: str) -> str:
        # 词法单元级替换：字符串与注释中的宏名保持原样，替换值不被二次扫描。
        if not self.macros:
            return source
        identifier_macros = {}
        literal_names: List[str] = []
        literal_values: List[str] = []
        for name, value in self.macros.items():
            name = str(name)
            if _IDENT_FULL_RE.fullmatch(name):
                identifier_macros[name] = value
            else:
                literal_names.append(name)
                literal_values.append(str(value))
        # 长名字优先，避免短名字先吃掉长名字的一部分
        pairs = sorted(zip(literal_names, literal_values),
                       key=lambda pair: len(pair[0]), reverse=True)
        literal_names = [name for name, _ in pairs]
        literal_values = [value for _, value in pairs]

        pieces = []
        for is_code, chunk in iter_code_chunks(source):
            if is_code:
                # 1) 非标识符宏名 -> 占位符（占位符不是标识符，后续步骤不会再动它）
                chunk = mask_names(chunk, literal_names)
                # 2) 标识符宏名按词边界替换
                chunk = substitute_identifiers(chunk, identifier_macros)
            pieces.append(chunk)
        # 3) 最后一步才把替换值拼回去，因此值里的宏名不会被继续展开
        return apply_values("".join(pieces), literal_values)

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
