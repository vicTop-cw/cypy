#!/usr/bin/env python3
"""Seventh-pass fixes, part 1: the eleven sites whose replacement text is unambiguous.

Every edit is asserted: the script counts occurrences of the anchor and refuses to write unless
it hit exactly the expected number, then re-reads the file and confirms the new text is present.
That is the guard against a silently mis-anchored bulk patch (same-shape string appearing at a
neighbouring site). Part 2 covers the four sites that need a helper or a multi-line rewrite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (relpath, old, new, expected_hits, ticket)
EDITS = [
    ("cypyc/parser/lexer.py",
     '                if self.source[self.pos:self.pos+2] == "``":',
     '                if self.source[self.pos:self.pos+3] == "```":',
     1, "BUG-15"),

    ("cypyc/parser/parser.py",
     "            if self._current().type == TokenType.AT:\n"
     "                decorators = []\n"
     "                while self._current().type == TokenType.AT:\n"
     "                    decorator = self._parse_decorator()\n"
     "                    decorators.append(decorator)\n"
     "                if self._current().type == TokenType.DEF:\n"
     "                    method = self._parse_func_def(decorators=decorators)\n",
     "            if self._current().type == TokenType.AT:\n"
     "                # BUG-16: 成员装饰器必须是独立的局部名 —— 覆写 `decorators` 会把\n"
     "                # :1326 形参带来的 struct 级装饰器（如 @value）整份丢掉，\n"
     "                # 并在 :1407 把成员装饰器当成 struct 自己的装饰器交出去。\n"
     "                member_decorators = []\n"
     "                while self._current().type == TokenType.AT:\n"
     "                    decorator = self._parse_decorator()\n"
     "                    member_decorators.append(decorator)\n"
     "                if self._current().type == TokenType.DEF:\n"
     "                    method = self._parse_func_def(decorators=member_decorators)\n",
     1, "BUG-16"),

    ("cypyc/project/project_compiler.py",
     "        return sorted(candidates)[0] if candidates else None",
     "        # BUG-17: 名字全不匹配时必须返回 None —— 兜底返回 sorted()[0] 会把\n"
     "        # 别的模块或历史残留的 .pyd 当成本次该模块的产物，令「No .pyd file\n"
     "        # generated」永不触发，与本函数 docstring 声明的挑选目的相反。\n"
     "        return None",
     1, "BUG-17"),

    ("cypyc/codegen/cython_generator.py",
     "        if 'from cypy_bridge.pointer import own, transfer_ownership, borrow, Owned, Borrowed' not in self.output:\n"
     "            self.output.insert(0, 'from cypy_bridge.pointer import own, transfer_ownership, borrow, Owned, Borrowed')",
     "        line = 'from cypy_bridge.pointer import own, transfer_ownership, borrow, Owned, Borrowed'\n"
     "        if line not in self.output:\n"
     "            # BUG-19: 不能插到第 0 行 —— :299 规定 `# cython:` 指令必须在文件最\n"
     "            # 顶部，否则整组指令失效（文档字符串也会从首语句降级）。插到开头\n"
     "            # 连续的注释/指令块之后。\n"
     "            at = 0\n"
     "            while at < len(self.output):\n"
     "                text = self.output[at].strip()\n"
     "                if text.startswith('#') or text.startswith('\"\"\"') or text.startswith(\"'''\"):\n"
     "                    at += 1\n"
     "                    continue\n"
     "                break\n"
     "            self.output.insert(at, line)",
     1, "BUG-19"),

    ("cypy_bridge/pointer.py",
     "        if hasattr(obj, 'value'):\n"
     "            return ctypes.addressof(obj)\n"
     "        elif isinstance(obj, ctypes._Pointer):\n"
     "            return ctypes.addressof(obj.contents)\n"
     "        elif isinstance(obj, ctypes.c_void_p):\n"
     "            return obj.value",
     "        # BUG-23: c_void_p 也有 .value，原先放在 hasattr 分支之后即成死代码，\n"
     "        # 于是 addr(c_void_p(4096)) 返回盒子地址、addr(c_void_p(0)) 返回非零，\n"
     "        # 用户的 NULL 判定永不成立。必须优先按 c_void_p 取其指向的值。\n"
     "        if isinstance(obj, ctypes.c_void_p):\n"
     "            return obj.value or 0\n"
     "        elif hasattr(obj, 'value'):\n"
     "            return ctypes.addressof(obj)\n"
     "        elif isinstance(obj, ctypes._Pointer):\n"
     "            return ctypes.addressof(obj.contents)",
     1, "BUG-23"),

    ("cypy_hook/hook.py",
     '                if os.path.basename(root) == "cypy" and os.path.dirname(root) == "__pycache__":',
     '                # BUG-24: os.walk(os.getcwd()) 给的 root 是绝对路径，与裸 "__pycache__"\n'
     '                # 恒不相等 —— 无参 clear_cache() 于是永远删 0 个文件却仍报成功。\n'
     '                if os.path.basename(root) == "cypy" and os.path.basename(os.path.dirname(root)) == "__pycache__":',
     1, "BUG-24"),

    ("cypy_bridge/compiler.py",
     "            with open(c_file, 'w') as f:",
     "            # BUG-25: 不带 encoding 的文本写盘按本地代码页（本机 cp936）落字节，\n"
     "            # 与读源码侧的 encoding=\"utf-8\" 不一致，非本地字符直接 UnicodeEncodeError。\n"
     "            with open(c_file, 'w', encoding='utf-8') as f:",
     1, "BUG-25"),

    ("cypy_bridge/compiler.py",
     "            with open(setup_file, 'w') as f:",
     "            with open(setup_file, 'w', encoding='utf-8') as f:",
     1, "BUG-25"),

    ("cypy_bridge/compiler.py",
     "                    if file.endswith('.pyd'):",
     "                    # BUG-26: _detect_compiler 支持 linux/darwin，产物扫描却只认 .pyd，\n"
     "                    # 非 Windows 上成功的编译会被报成「没找到产物」。与同文件 :3683、\n"
     "                    # cypy_hook/hook.py:542 的既有口径统一。\n"
     "                    if file.endswith('.pyd') or file.endswith('.so') or file.endswith('.dll'):",
     1, "BUG-26"),

    ("cypyc/incremental/hot_reload.py",
     "                    affected_definitions=set.union(*[r.affected_definitions for r in results]),",
     "                    # BUG-27: set.union 是未绑定方法，results 为空（纯删除批次）时抛\n"
     "                    # TypeError 并被下面的 except 误报成「用户回调出错」。\n"
     "                    affected_definitions=set().union(*[r.affected_definitions for r in results]),",
     1, "BUG-27"),

    ("cypyc/utils/indent_detector.py",
     "        common_indents = set(indent_counts)\n"
     "        if len(common_indents) == 1:\n"
     "            self.indent_size = list(common_indents)[0]\n"
     "        else:\n"
     "            self.indent_size = 4",
     "        # BUG-28: 观测到多种宽度时一律取 4，会让 2 空格风格的第一层体在\n"
     "        # normalize() 的 `indent // size` 里塌成 0 层（块结构被毁）。层数单位应是\n"
     "        # 观测宽度的最大公约数：{2,4}->2、{3,6}->3、{4,8}->4。\n"
     "        common_indents = set(indent_counts)\n"
     "        size = 0\n"
     "        for value in sorted(common_indents):\n"
     "            size = value if not size else _gcd(size, value)\n"
     "        self.indent_size = size or 4",
     1, "BUG-28"),

    ("cypyc/utils/indent_detector.py",
     "import re\nfrom typing import Optional, Tuple",
     "import re\nfrom math import gcd as _gcd\nfrom typing import Optional, Tuple",
     1, "BUG-28"),

    ("cypy_hook/hook.py",
     "        if os.path.isfile(parsed_args.source):",
     "        # BUG-29: source 是可选位置参数，`cypyc hook` 不带文件时它是 None，\n"
     "        # os.path.isfile(None) 抛裸 TypeError；这里应当给出用法提示。\n"
     "        if parsed_args.source is None:\n"
     "            print(\"Error: no source file given (try: cypyc hook <file.cypy> [--compile] [--run <fn>])\",\n"
     "                  file=sys.stderr)\n"
     "            return 1\n"
     "\n"
     "        if os.path.isfile(parsed_args.source):",
     1, "BUG-29"),
]


def main() -> int:
    report, errors = [], []
    for rel, old, new, want, ticket in EDITS:
        path = ROOT / rel
        # Read raw so a CRLF file (lexer/parser/cython_generator/hot_reload) is not silently
        # rewritten as LF -- anchors are translated to whichever convention the file uses.
        text = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in text
        if crlf:
            old = old.replace("\n", "\r\n")
            new = new.replace("\n", "\r\n")
        hits = text.count(old)
        if hits != want:
            errors.append(f"{ticket} {rel}: anchor hit {hits}, expected {want} -- NOT written")
            continue
        if new in text:
            errors.append(f"{ticket} {rel}: replacement already present -- NOT written")
            continue
        path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
        after = path.read_bytes().decode("utf-8")
        ok = new in after and after.count(old) == hits - 1
        report.append({"ticket": ticket, "file": rel, "hits": hits,
                       "crlf_preserved": crlf == ("\r\n" in after), "verified": ok})
        if not ok:
            errors.append(f"{ticket} {rel}: post-write verification failed")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"applied={len(report)} errors={len(errors)}")
    for e in errors:
        print("  !", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
