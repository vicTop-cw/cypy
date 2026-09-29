#!/usr/bin/env python3
"""Fourth-pass mechanical sweep: the defect classes the brief names that passes 1-3 only sampled.

Scans cypyc/, cypy_bridge/, cypy_hook/ for
  A) mutable default arguments (list/dict/set literal in a parameter default)
  B) open()/NamedTemporaryFile without a context manager and without a visible close()
  C) subprocess.* calls with no timeout= anywhere in the call
  D) thread locks acquired without try/finally release
  E) list subscripts on a slicing result assumed non-empty  ([0] right after a filter/ comprehension)

Output is candidate *sites* only. Judgement (real defect / false positive / semantics TBD)
is made by reading each site; nothing here is filed automatically.
"""
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIRS = ["cypyc", "cypy_bridge", "cypy_hook"]
MUTABLE = (ast.List, ast.Dict, ast.Set)
# no `import subprocess as sp` anywhere in the three packages (verified by grep), so the
# plain module name is the only receiver worth matching.
SUBPROCESS_NAMES = {"subprocess"}


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def files():
    for pkg in PKG_DIRS:
        base = os.path.join(ROOT, pkg)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".venv", "venv")]
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    yield os.path.join(dirpath, fn)


def seg_calls(node, name):
    """True if `node` is a call to `name` (subprocess.run / .Popen / .check_output ...)."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr == name
    return False


def has_timeout(node):
    return any(k.arg == "timeout" for k in node.keywords)


def enclosing_blocks(tree):
    """map child node -> parent, plus set of nodes inside a try-with-finally."""
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    return parent


def scan():
    out = {"A_mutable_default": [], "B_open_no_ctx": [], "C_subprocess_no_timeout": [],
           "D_lock_no_finally": [], "E_index_after_filter": [], "files_scanned": 0,
           "lines_scanned": 0}
    for path in files():
        src = open(path, encoding="utf-8").read()
        lines = src.splitlines()
        out["files_scanned"] += 1
        out["lines_scanned"] += len(lines)
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            out.setdefault("parse_errors", []).append(f"{rel(path)}:{exc.lineno}")
            continue
        parent = enclosing_blocks(tree)

        for node in ast.walk(tree):
            # A) mutable default args
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in list(node.args.defaults) + list(node.args.kw_defaults):
                    if isinstance(d, MUTABLE) and d.elts:
                        out["A_mutable_default"].append({
                            "loc": f"{rel(path)}:{d.lineno}",
                            "fn": node.name,
                            "default": ast.dump(d)[:120],
                            "src": lines[d.lineno - 1].strip()[:160]})
            # B) bare open() assigned or used outside a with
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                cur = node
                in_with = False
                while cur in parent:
                    cur = parent[cur]
                    if isinstance(cur, ast.With) or isinstance(cur, ast.AsyncWith):
                        items = getattr(cur, "items", [])
                        if any(node in list(ast.walk(it.context_expr)) for it in items):
                            in_with = True
                            break
                if not in_with:
                    out["B_open_no_ctx"].append({
                        "loc": f"{rel(path)}:{node.lineno}",
                        "src": lines[node.lineno - 1].strip()[:160]})
            # C) subprocess without timeout
            if seg_calls(node, "run") or seg_calls(node, "check_output") or seg_calls(node, "check_call") \
                    or seg_calls(node, "Popen"):
                # The rule is about `subprocess.*`; an attribute named `run` on anything else
                # (hook.run(), self.run()) is not a subprocess call. First draft of this rule
                # matched those too and reported 2 phantom sites, so the receiver is checked now.
                receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
                if not (isinstance(receiver, ast.Name) and receiver.id in SUBPROCESS_NAMES):
                    continue
                if seg_calls(node, "Popen"):
                    out["C_subprocess_no_timeout"].append({
                        "loc": f"{rel(path)}:{node.lineno}",
                        "call": "Popen (needs communicate/wait timeout)",
                        "src": lines[node.lineno - 1].strip()[:160]})
                elif not has_timeout(node):
                    out["C_subprocess_no_timeout"].append({
                        "loc": f"{rel(path)}:{node.lineno}",
                        "call": ast.unparse(node.func),
                        "src": lines[node.lineno - 1].strip()[:160]})
            # D) lock acquire without try/finally release
            if seg_calls(node, "acquire"):
                cur = node
                guarded = False
                while cur in parent:
                    cur = parent[cur]
                    if isinstance(cur, ast.Try) and any(node in list(ast.walk(t)) for t in cur.body) \
                            and cur.finalbody:
                        guarded = True
                        break
                if not guarded:
                    out["D_lock_no_finally"].append({
                        "loc": f"{rel(path)}:{node.lineno}",
                        "src": lines[node.lineno - 1].strip()[:160]})
            # E) [0] on a comprehension/filter result
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                    and node.slice.value == 0 and isinstance(node.value, ast.ListComp):
                out["E_index_after_filter"].append({
                    "loc": f"{rel(path)}:{node.lineno}",
                    "src": lines[node.lineno - 1].strip()[:160]})
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    res = scan()
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep4_classes.json")
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"scanned {res['files_scanned']} files / {res['lines_scanned']} lines -> {rel(dest)}")
    for k in ("A_mutable_default", "B_open_no_ctx", "C_subprocess_no_timeout",
              "D_lock_no_finally", "E_index_after_filter"):
        print(f"{k}: {len(res[k])}")
        for item in res[k]:
            print(f"   {item['loc']}  {item['src'][:90]}")


if __name__ == "__main__":
    main()
