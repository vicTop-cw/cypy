#!/usr/bin/env python3
"""Seventh-pass fixes, part 2: the four sites that need a receiver/entry lookup.

Same anchor discipline as part 1: hit-count asserted before writing, result re-read and
confirmed, CRLF preserved where the file uses it.
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

EDITS = [
    # BUG-18: existence is not freshness -- compare the dependency's recorded hash.
    ("cypyc/incremental/incremental_manager.py",
     "        for module_name in imported_modules:\n"
     "            # 尝试找到模块对应的文件\n"
     "            module_file = self._find_module_file(module_name)\n"
     "            if module_file and os.path.exists(module_file):\n"
     "                # 检查模块的缓存是否失效\n"
     "                if not self.is_cached(module_file):\n"
     "                    return True\n"
     "        return False",
     "        for module_name in imported_modules:\n"
     "            # 尝试找到模块对应的文件\n"
     "            module_file = self._find_module_file(module_name)\n"
     "            if not (module_file and os.path.exists(module_file)):\n"
     "                continue\n"
     "            # BUG-18: is_cached() 只回答「有没有条目」，不回答「条目还有效吗」。\n"
     "            # 只看存在性时，改过的依赖只要缓存过就被判成没变，导入方复用陈旧 .pyd。\n"
     "            # 这里比对依赖自己的 file_hash 与当前内容摘要（口径同 :248）。\n"
     "            if not self.is_cached(module_file):\n"
     "                return True\n"
     "            entry = self._load_cache(module_file)\n"
     "            if entry is None:\n"
     "                return True\n"
     "            recorded = getattr(entry, \"file_hash\", None)\n"
     "            if recorded != self._compute_file_hash(module_file):\n"
     "                return True\n"
     "        return False",
     1, "BUG-18"),

    # BUG-20: route `recv.method(args)` through the attribute table instead of str(node).
    ("cypyc/analyzer/comptime_evaluator.py",
     "        if isinstance(node, Call):\n"
     "            func_name = self._get_func_name(node.func)\n"
     "            args = [self.evaluate(arg) for arg in node.args]\n"
     "            return self._evaluate_call(func_name, args)",
     "        if isinstance(node, Call):\n"
     "            # BUG-20: func 是 Attribute（\"abc\".upper()）时 _get_func_name 退回\n"
     "            # str(node)，得到带行列号的节点 repr，永远查不进任何表 —— 于是\n"
     "            # :188-276 整张字符串/列表方法表不可达，语句被静默丢成注释。\n"
     "            # 按 _evaluate_attribute_access 的契约取回已绑定接收者的方法再调用。\n"
     "            receiver = getattr(node.func, \"value\", None)\n"
     "            attr = getattr(node.func, \"attr\", None)\n"
     "            args = [self.evaluate(arg) for arg in node.args]\n"
     "            if receiver is not None and attr:\n"
     "                obj_val = self.evaluate(receiver)\n"
     "                if obj_val is None:\n"
     "                    return None\n"
     "                method = self._evaluate_attribute_access(obj_val, attr)\n"
     "                if callable(method):\n"
     "                    try:\n"
     "                        return method(*args)\n"
     "                    except TypeError:\n"
     "                        return None\n"
     "                return method\n"
     "            func_name = self._get_func_name(node.func)\n"
     "            return self._evaluate_call(func_name, args)",
     1, "BUG-20"),

    # BUG-21: name the impl target instead of registering an AST-node repr.
    ("cypyc/analyzer/type_checker.py",
     "                trait_name = stmt.trait_name\n"
     "                for_type_name = getattr(stmt.for_type, 'id', str(stmt.for_type))\n"
     "                if trait_name not in self.trait_impls:",
     "                trait_name = stmt.trait_name\n"
     "                # BUG-21: GenericType（`impl Show for Box<T>`）没有 .id，默认分支\n"
     "                # str(node) 会把 \"GenericType(line=5, col=15)\" 当成类型名登记，\n"
     "                # 于是这条实现在约束检查里永远匹配不上。口径与 codegen 侧\n"
     "                # cython_generator.py:482-486 一致：泛型取基类型名。\n"
     "                for_type_name = (getattr(stmt.for_type, 'id', None)\n"
     "                                 or getattr(stmt.for_type, 'name', None)\n"
     "                                 or str(stmt.for_type))\n"
     "                if trait_name not in self.trait_impls:",
     1, "BUG-21"),

    # BUG-22: `fr"..."` is claimed by the comment two lines above but rejected here.
    ("cypyc/parser/lexer.py",
     "                # 检查是否是 f-string 前缀 (支持 f, F, rf, fr)\n"
     "                if char in ('f', 'F', 'r', 'R') and self._peek_ahead(1) in ('\"', \"'\", 'f', 'F'):\n"
     "                    prefix_chars = char\n"
     "                    # 检查组合前缀 (rf, fr)\n"
     "                    if self._peek_ahead(1) in ('f', 'F'):\n",
     "                # 检查是否是 f-string 前缀 (支持 f, F, rf, fr)\n"
     "                # BUG-22: 第二字符集合里没有 r/R，注释承诺的 `fr\"...\"` 实际被拆成\n"
     "                # IDENTIFIER `fr` + STRING（`rf\"...\"` 却能过），报错点远在 parse。\n"
     "                # 组合前缀只承认 rf/fr 两种，不接受 rr/ff。\n"
     "                _nxt = self._peek_ahead(1)\n"
     "                _combo = (char in ('f', 'F') and _nxt in ('r', 'R')) or \\\n"
     "                    (char in ('r', 'R') and _nxt in ('f', 'F'))\n"
     "                if char in ('f', 'F', 'r', 'R') and (_nxt in ('\"', \"'\") or _combo):\n"
     "                    prefix_chars = char\n"
     "                    # 检查组合前缀 (rf, fr)\n"
     "                    if _nxt in ('f', 'F', 'r', 'R'):\n",
     1, "BUG-22"),
]


def main() -> int:
    report, errors = [], []
    for rel, old, new, want, ticket in EDITS:
        path = ROOT / rel
        text = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in text
        if crlf:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        hits = text.count(old)
        if hits != want:
            errors.append(f"{ticket} {rel}: anchor hit {hits}, expected {want} -- NOT written")
            continue
        if new in text:
            errors.append(f"{ticket} {rel}: already applied -- NOT written")
            continue
        after = text.replace(old, new, 1)
        path.write_bytes(after.encode("utf-8"))
        check = path.read_bytes().decode("utf-8")
        ok = new in check and crlf == ("\r\n" in check)
        report.append({"ticket": ticket, "file": rel, "crlf_preserved": crlf == ("\r\n" in check),
                       "verified": ok})
        if not ok:
            errors.append(f"{ticket} {rel}: post-write verification failed")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"applied={len(report)} errors={len(errors)}")
    for e in errors:
        print("  !", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
