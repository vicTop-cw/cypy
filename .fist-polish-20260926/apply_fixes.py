import re, sys
sys.stdout.reconfigure(encoding="utf-8")

def patch(path, old, new, count=1):
    with open(path, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    old_n, new_n = old.replace("\n", nl), new.replace("\n", nl)
    hits = src.count(old_n)
    assert hits == count, f"{path}: 期望 {count} 处，实到 {hits} 处"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(src.replace(old_n, new_n))
    print(f"OK {path}")

# BUG-5: hot_reload 快照/回滚不再静默
p = "cypyc/incremental/hot_reload.py"
patch(p, "class CypyProxyModule:",
      'def _warn_state(action: str, name: str, exc: BaseException) -> None:\n'
      '    """缺了状态的热重载模块会带着空洞继续跑，失败必须可见。"""\n'
      '    import sys\n'
      '    print(f"[cypy][warn] 热重载状态{action}跳过 {name}: {exc}", file=sys.stderr)\n'
      '\n'
      '\n'
      'class CypyProxyModule:')
patch(p, """                        self._state_cache[name] = value
                except Exception:
                    pass""",
      """                        self._state_cache[name] = value
                except Exception as exc:
                    _warn_state("快照", name, exc)""")
patch(p, """                        setattr(self._actual_module, name, value)
                except Exception:
                    pass""",
      """                        setattr(self._actual_module, name, value)
                except Exception as exc:
                    _warn_state("回滚", name, exc)""")

# BUG-6: file_monitor 首行按字节解码，读不到时告警
patch("cypyc/incremental/file_monitor.py", """        if file_path.endswith(".py"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    return first_line == "#!bin cypy"
            except Exception:
                pass""",
"""        if file_path.endswith(".py"):
            # 按字节读首行：文本模式遇到 BOM/非法编码会抛异常，把 Cypy 入口文件
            # 静默归类成「不是 Cypy 文件」，热重载因此漏编译。
            try:
                with open(file_path, "rb") as f:
                    first_line = f.readline().decode("utf-8-sig", errors="replace").strip()
            except FileNotFoundError:
                return False
            except OSError as exc:
                import sys
                print(f"[cypy][warn] 无法读取 {file_path} 首行，按非 Cypy 文件处理: {exc}",
                      file=sys.stderr)
                return False
            return first_line == "#!bin cypy\"""")

# BUG-4: 递归收集移出静默 try
pat = re.compile(
    r"( *)try:\n\1    value = getattr\(node, attr_name\)\n"
    r"\1    if isinstance\(value, ASTNode\):\n\1        self\._collect_(\w+)\(value\)\n"
    r"\1    elif isinstance\(value, list\):\n\1        for item in value:\n"
    r"\1            if isinstance\(item, ASTNode\):\n\1                self\._collect_\2\(item\)\n"
    r"\1except \(AttributeError, TypeError\):\n\1    pass")
repl = (r"\1try:\n\1    value = getattr(node, attr_name)\n"
        r"\1except (AttributeError, TypeError):\n\1    continue\n"
        r"\1if isinstance(value, ASTNode):\n\1    self._collect_\2(value)\n"
        r"\1elif isinstance(value, list):\n\1    for item in value:\n"
        r"\1        if isinstance(item, ASTNode):\n\1            self._collect_\2(item)")
for mod in ("defer", "enum", "generic", "struct", "trait"):
    path = f"cypyc/transformer/{mod}_transformer.py"
    with open(path, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    body = src.replace(nl, "\n")
    new_body, n = pat.subn(repl, body)
    assert n == 1, f"{path}: 匹配 {n} 处"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new_body.replace("\n", nl))
    print(f"OK {path}")
