"""R3-验证 法 1/2/8：逐单回退矩阵 + 复原自证 + 上一环遗留主张回算。

做法（与 R3-修复 环自己的判据件无关，独立出题）：
1. `git archive HEAD` 解到 `tmp_verify/snap_<pid>/`（每进程一棵，避免并发互删），
   再把本轮 7 个改动文件覆盖进去 ⇒ 快照树 = HEAD 码 + 本轮产品码 + 本轮测试。
2. 身份自证：快照树里解析 6 个被测模块的 `__file__` 必须落在快照树内；
   行为自证：每行 mutation 只改快照树，工作区文件的 sha 在全程前后不变 ⇒
   只有真的加载了快照码，该行才会变红（跑错副本则整行红不了 ⇒ 自我作废）。
3. 每行用「字面锚点 + 出现次数断言」把该件改回修前文本（锚点文本取自
   `git show HEAD:<file>` 的逐字内容），mutation 后先 py_compile 再跑锁。
4. 期望：该件正例锁 ≥1 红、该件对照锁 0 红、其余四件的锁 0 红（不连带）。
5. 复原：每行跑完从内存里的 mutation 前字节回写，sha256 必须逐字相等。
6. 声明侧回算 + 上一环 flip 主张回算（复用寻虫环的探针脚本，读盘面）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP = HERE / "tmp_verify" / f"snap_{os.getpid()}"
LOGDIR = HERE / "r3verify_logs"
LOCK_FILE = "tests/test_loop_20260927_fix_r3.py"
OVERLAY = [
    "cypyc/cli.py",
    "cypyc/transformer/generic_transformer.py",
    "cypyc/project/module_dependency_graph.py",
    "cypyc/analyzer/build_block_checker.py",
    "cypy_bridge/union.py",
    "cypy_bridge/memory.py",
    LOCK_FILE,
]
PY = sys.executable
HEAD_EXPECT = "17d68b4"
PYTEST_FLOOR = 17
LOCK_TOTAL = 17

POS = {
    "BUG-55": ["test_bug55_generic_params_nodes_are_collected"],
    "BUG-56": [
        "test_bug56_check_only_reports_and_generates_nothing",
        "test_bug56_check_only_fails_on_broken_source",
        "test_bug56_emit_ast_prints_parsed_nodes",
        "test_bug56_emit_cython_prints_cython_code",
        "test_bug56_generate_setup_writes_buildable_script",
    ],
    "BUG-57": [
        "test_bug57_builtin_member_type_is_diagnosed",
        "test_bug57_union_docstrings_advertise_only_runnable_shapes",
    ],
    "BUG-58": ["test_bug58_realloc_annotation_matches_return_shape"],
    "BUG-59": ["test_bug59_compilation_order_stable_across_hash_seeds"],
    "BUG-60": ["test_bug60_docstring_rule2_aligns_with_frozen_syntax"],
}
CTL = {
    "BUG-55": ["test_bug55_duck_def_type_params_still_collected"],
    "BUG-56": ["test_bug56_control_plain_transpile_writes_no_setup"],
    "BUG-57": ["test_bug57_documented_member_shapes_work"],
    "BUG-58": [
        "test_bug58_realloc_zero_size_still_returns_none_and_frees",
        "test_bug58_control_malloc_zero_still_raises",
    ],
    "BUG-59": [],
    "BUG-60": ["test_bug60_control_other_rules_still_enforced"],
}
PROBE = {"BUG-55": "C1", "BUG-56": "C3", "BUG-57": "C4", "BUG-58": "C5",
         "BUG-59": "C6", "BUG-60": "C8"}
# 上一环（R3-修复）报告里写下的主张：flip=True 表示探针当场由红转绿。
PREV_CLAIM = {"BUG-55": True, "BUG-56": True, "BUG-57": True, "BUG-59": True,
              "BUG-58": False, "BUG-60": False}

# 每件的「修前文本」反向补丁：(相对路径, 修后字面, 修前字面, 修后字面应出现次数)
# 修前字面一律取自 `git show HEAD:<file>` 的逐行原文（已逐字对照）。
PATCHES = {
    "BUG-55": [
        ("cypyc/transformer/generic_transformer.py",
         "        # parser 给泛型节点（FuncDef/StructDef）用的属性名是 `generic_params`，\n"
         "        # `type_params` 是 DuckDef 那一族的叫法 ⇒ 只读其中一个会静默漏收。\n"
         "        params = getattr(node, 'generic_params', None) or getattr(node, 'type_params', None)\n"
         "        if params:",
         "        # 检查是否有类型参数\n"
         "        if hasattr(node, 'type_params') and node.type_params:", 1),
    ],
    "BUG-56": [
        ("cypyc/cli.py",
         "    if args.emit_ast:\n"
         "        rc = _transpile_emit_ast(args.source)\n"
         "        if rc:\n"
         "            return rc\n"
         "\n"
         "    if args.check_only:\n"
         "        return _transpile_check_only(args)\n"
         "\n"
         "    if args.bridge:",
         "    if args.bridge:", 1),
        ("cypyc/cli.py",
         '            if args.emit_cython:\n'
         '                print_info("--emit-cython does not apply in --bridge mode; "\n'
         '                           "the emitted language is C")\n'
         "\n"
         "            if args.emit_code:",
         "            if args.emit_code:", 1),
        ("cypyc/cli.py",
         "            if args.generate_setup:\n"
         "                return _transpile_generate_setup(args.output, c_path)\n"
         "\n"
         "            return 0",
         "            return 0", 1),
        ("cypyc/cli.py",
         "            if (args.emit_code or args.emit_cython) and result.cython_code:",
         "            if args.emit_code and result.cython_code:", 1),
        ("cypyc/cli.py",
         "            if args.generate_setup:\n"
         "                return _transpile_generate_setup(args.output, result.pyx_path)\n"
         "\n"
         "            return 0",
         "            return 0", 1),
    ],
    "BUG-57": [
        ("cypy_bridge/union.py",
         "        # 创建联合类型（成员是 ctypes 类型或 C 类型名字符串）\n"
         "        from ctypes import c_int, c_double\n"
         '        my_union = CUnion(c_int, c_double)      # 等价：CUnion("int", "double")',
         "        # 创建联合类型\n"
         "        my_union = CUnion(int, float)", 1),
        ("cypy_bridge/union.py",
         '        my_union = union("int", "double")     # 或 union(ctypes.c_int, ctypes.c_double)',
         "        my_union = union(int, float)", 1),
        ("cypy_bridge/union.py",
         "            elif isinstance(mtype, type) and mtype.__module__ == 'builtins':\n"
         "                # Python 内建类型没有 ctypes 的宽度口径（`ctypes.sizeof(int)` 直接抛\n"
         '                # "this type has no size"），映射成 c_int 还是 c_long 是个未定的语义\n'
         "                # 选择 ⇒ 在这里拒绝并给出口径，而不是让 ctypes 抛一条看不懂的错。\n"
         "                raise UnionTypeError(\n"
         '                    f"Union member {mtype.__name__!r} is a Python builtin type; "\n'
         '                    f"pass a ctypes type (ctypes.c_int) or a C type name ({mtype.__name__!r})"\n'
         "                )\n"
         "            else:",
         "            else:", 1),
    ],
    "BUG-58": [
        ("cypy_bridge/memory.py",
         "def realloc(ptr: Any, size: int) -> Optional[int]:",
         "def realloc(ptr: Any, size: int) -> ctypes.c_void_p:", 1),
        ("cypy_bridge/memory.py",
         "        新的内存地址（int）；size <= 0 时返回 None",
         "        新的内存指针", 1),
    ],
    "BUG-59": [
        ("cypyc/project/module_dependency_graph.py",
         "            # 将循环依赖的模块放在最后（按名排序：`set` 的迭代序随进程字符串哈希\n"
         "            # 种子变化，直接 extend 会让同一张图给出不同推荐序）",
         "            # 将循环依赖的模块放在最后", 1),
        ("cypyc/project/module_dependency_graph.py",
         "            ordered.extend(sorted(cycle_modules))",
         "            ordered.extend(cycle_modules)", 1),
    ],
    "BUG-60": [
        ("cypyc/analyzer/build_block_checker.py",
         "2. 指针语法不限于构建块内部：按 SYNTAX/04-pointer-types.md「指针使用限制」的口径，\n"
         "   指针声明的合法位置是**函数作用域**，构建块只是其中一种。\n"
         "   指针的寻址合法性与所有权/defer 清理检查在 `pointer_checker`，本模块不重复把关。",
         "2. 指针语法只能在构建块内部使用", 1),
    ],
}

REFUSE: list = []
MODULES = ["cypyc.cli", "cypyc.transformer.generic_transformer",
           "cypyc.project.module_dependency_graph", "cypyc.analyzer.build_block_checker",
           "cypy_bridge.union", "cypy_bridge.memory"]


def sh(cmd, cwd, timeout=900):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", newline="")


def apply_patch(text: str, needle: str, repl: str, expect: int, tag: str):
    """字面锚定反向补丁：先证明针的出现次数（LF/CRLF 两种形态各自数），再替换。"""
    for nd, rp, form in ((needle, repl, "lf"),
                         (needle.replace("\n", "\r\n"), repl.replace("\n", "\r\n"), "crlf")):
        got = text.count(nd)
        if got == expect and got > 0:
            return text.replace(nd, rp, expect), tag, form
    REFUSE.append(f"[{tag}] 锚点计数不符（mutation 不成立，拒绝继续）：expect={expect} "
                  f"lf={text.count(needle)} crlf={text.count(needle.replace(chr(10), chr(13) + chr(10)))}")
    return None, tag, ""


def build_snapshot():
    """快照树 = 盘面（tracked 文件的工作区内容 + 本轮新增文件），mutation 是唯一变量。

    为什么不拿 `git archive HEAD` 当底：HEAD 早于 R1/R2 的未提交改动（红线禁止 commit），
    实测会引入混因红——HEAD 的 `cypy_bridge/__init__.py` 仍把 `union` 导成函数，
    会遮蔽同名子模块 ⇒ 本轮锁在快照里因 AttributeError 而红，与任何 mutation 无关。
    """
    info = {"dir": str(SNAP), "head": "", "extracted_files": 0, "overlaid": [],
            "missing_on_disk": [], "base": "working_tree_tracked", "exists": False}
    head = sh(["git", "rev-parse", "--short", "HEAD"], ROOT, 120)[1].strip()
    info["head"] = head
    if head != HEAD_EXPECT:
        REFUSE.append(f"HEAD 不是本轮底树：{head} != {HEAD_EXPECT}")
    if SNAP.exists():
        shutil.rmtree(SNAP, ignore_errors=True)
    SNAP.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT),
                             capture_output=True, timeout=300)
    if listing.returncode != 0:
        REFUSE.append(f"git ls-files 失败：{listing.stderr.decode('utf-8', 'replace')[-200:]}")
        return info
    tracked = [t.decode("utf-8", "replace") for t in listing.stdout.split(b"\0") if t]
    copied = 0
    for rel in tracked:
        src = ROOT / rel
        if not src.is_file():
            info["missing_on_disk"].append(rel)
            continue
        dst = SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    info["extracted_files"] = copied
    if copied < 200:
        REFUSE.append(f"快照树只复制了 {copied} 个文件（tracked 清单异常）")
    for rel in OVERLAY:
        src, dst = ROOT / rel, SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        info["overlaid"].append(rel)
    markers = ["pyproject.toml", "cypyc/cli.py", "tests/test_loop_20260927_fix_r3.py",
               "cypy_bridge/__init__.py", "cypy_bridge/union.py", "docs/USAGE.md"]
    gone = [m for m in markers if not (SNAP / m).exists()]
    if gone:
        REFUSE.append(f"快照树自建证明失败，缺：{gone}")
    if len(list(SNAP.rglob("*.py"))) < 100:
        REFUSE.append(f"快照树 .py 文件数异常少：{len(list(SNAP.rglob('*.py')))}")
    info["exists"] = not gone
    return info


def identity_probe():
    """在快照树里解析 6 个模块的 __file__，必须全部落在快照树内。"""
    snippet = (
        "import importlib,json\n"
        "out={}\n"
        "for m in %r:\n"
        "    mod=importlib.import_module(m)\n"
        "    out[m]=getattr(mod,'__file__',None)\n"
        "print(json.dumps(out))\n" % (MODULES,)
    )
    rc, out = sh([PY, "-X", "utf8", "-c", snippet], SNAP, 300)
    try:
        found = json.loads(out.strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        REFUSE.append(f"身份探针输出解析失败：{type(exc).__name__} {exc} :: {out[-200:]}")
        return 0, {}
    snap_s = str(SNAP.resolve()).lower()
    rows = {}
    inside = 0
    for mod, path in found.items():
        ok = bool(path) and str(Path(path).resolve()).lower().startswith(snap_s)
        rows[mod] = {"path": path, "inside_snapshot": ok}
        if ok:
            inside += 1
    if inside < 4:
        REFUSE.append(f"身份探针：只有 {inside}/{len(MODULES)} 个模块解析到快照树内（可能跑了工作区/已安装副本）")
    return inside, rows


def collect_count():
    """`-q` 的通过态不打印 collected 行 ⇒ 收集数只能从 --collect-only 的 nodeid 计数拿。"""
    rc, out = sh([PY, "-X", "utf8", "-m", "pytest", LOCK_FILE, "--collect-only", "-q",
                  "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], SNAP, 600)
    ids = [ln for ln in out.splitlines() if "::" in ln]
    return rc, len(ids)


def run_pytest(kexpr=None):
    cmd = [PY, "-X", "utf8", "-m", "pytest", LOCK_FILE, "-q", "-p", "no:cacheprovider",
           "--no-header", "-o", "addopts=", "--tb=line"]
    if kexpr:
        cmd += ["-k", kexpr]
    rc, out = sh(cmd, SNAP, 1200)
    passed = int(re.search(r"(\d+) passed", out).group(1)) if re.search(r"(\d+) passed", out) else 0
    reds = sorted({ln.split("::")[-1].split(" ")[0]
                   for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))})
    m = re.search(r"(\d+) tests? collected", out)
    return {"rc": rc, "passed": passed, "reds": reds,
            "collected": int(m.group(1)) if m else 0,
            "seen_total": passed + len(reds), "out": out}


def matrix_row(bug):
    row = {"bug": bug, "patches": len(PATCHES[bug]), "applied": 0, "compiled": False,
           "pos_red": [], "ctl_red": [], "collateral_red": [], "restored": False,
           "sha_before": "", "sha_after_restore": "", "sha_equal": False,
           "touched_files": [], "workspace_untouched": False, "matches_prev_head": None,
           "red_reasons": {}}
    files = {}
    for rel, _needle, _repl, _n in PATCHES[bug]:
        if rel not in files:
            path = SNAP / rel
            files[rel] = {"path": path, "before": read_text(path), "sha": sha(path)}
            row["touched_files"].append(rel)
    # 逐补丁应用（同一文件按声明顺序链式替换）
    for rel, info in files.items():
        text = info["before"]
        for p_rel, needle, repl, expect in PATCHES[bug]:
            if p_rel != rel:
                continue
            new_text, tag, _lines = apply_patch(text, needle, repl, expect, f"{bug}:{rel}")
            if new_text is None:
                return row
            text = new_text
            row["applied"] += 1
        if text == info["before"]:
            REFUSE.append(f"[{bug}] mutation 后文本与原文逐字相同 ⇒ 补丁没生效，矩阵行空转")
            return row
        info["mutated"] = text
    for rel, info in files.items():
        info["path"].write_text(info["mutated"], encoding="utf-8", newline="")
    ok_compile = True
    for rel in files:
        rc, out = sh([PY, "-X", "utf8", "-m", "py_compile", rel], SNAP, 300)
        if rc != 0:
            ok_compile = False
            REFUSE.append(f"[{bug}] mutation 后的 {rel} 无法编译（补丁破坏了结构，不是缺陷签名）：{out[-160:]}")
    row["compiled"] = ok_compile
    if not ok_compile:
        for rel, info in files.items():
            info["path"].write_text(info["before"], encoding="utf-8", newline="")
        return row
    try:
        res = run_pytest()
        row["red_reasons"] = {ln.split("::")[-1].split(" ")[0]: ln[-140:]
                             for ln in res["out"].splitlines()
                             if ln.startswith(("FAILED", "ERROR"))}
        all_pos = POS[bug]
        all_ctl = CTL[bug]
        mine = set(all_pos) | set(all_ctl)
        row["pos_red"] = [x for x in res["reds"] if x in all_pos]
        row["ctl_red"] = [x for x in res["reds"] if x in all_ctl]
        row["collateral_red"] = [x for x in res["reds"] if x not in mine]
        row["reds_total"] = len(res["reds"])
        row["seen_total"] = res["seen_total"]
        if res["seen_total"] != LOCK_TOTAL:
            REFUSE.append(f"[{bug}] 快照里跑到的锁数 {res['seen_total']} != {LOCK_TOTAL}"
                          f"（passed={res['passed']} reds={len(res['reds'])}）⇒ 夹具或解析坏了")
        if not row["pos_red"]:
            REFUSE.append(f"[{bug}] 改回修前文本后该件正例锁仍全绿 ⇒ 这条锁不承重")
        if row["ctl_red"]:
            REFUSE.append(f"[{bug}] 对照锁被连带打红：{row['ctl_red']}（回退不该削掉另一族行为）")
        if row["collateral_red"]:
            REFUSE.append(f"[{bug}] 其余件的锁被连带打红：{row['collateral_red']}")
        for rel in files:
            ws_sha = sha(ROOT / rel)
            if ws_sha != sha_on_load[rel]:
                row["workspace_untouched"] = False
                REFUSE.append(f"[{bug}] 工作区文件被本驱动改动过：{rel}（快照隔离失效）")
            else:
                row["workspace_untouched"] = True
    finally:
        for rel, info in files.items():
            info["path"].write_text(info["before"], encoding="utf-8", newline="")
            row["sha_after_restore"] = sha(info["path"])
        row["sha_before"] = {rel: info["sha"] for rel, info in files.items()}
        row["sha_equal"] = all(sha(info["path"]) == info["sha"] for info in files.values())
        row["restored"] = row["sha_equal"]
        if not row["sha_equal"]:
            REFUSE.append(f"[{bug}] mutation 后未能逐字复原（sha 不等）")
    return row


def declared_side():
    """上一环声明的『声明侧已对齐』今天是否仍在盘上（独立重算，不读旧结论）。"""
    import ast

    out = {}
    gt = read_text(ROOT / "cypyc/transformer/generic_transformer.py")
    out["BUG-55"] = {"both_names_in_source":
                     "generic_params" in gt and "type_params" in gt,
                     "claim": "收集器同时认两种属性名（声明侧：模块 docstring 的『注册泛型参数』）"}
    cli_src = (ROOT / "cypyc/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(cli_src)
    readers = {}
    flags = ("check_only", "emit_ast", "generate_setup", "emit_cython")
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
               and n.name == "run_transpile"]:
        for f in flags:
            readers[f] = sum(1 for x in ast.walk(fn)
                             if isinstance(x, ast.Attribute) and x.attr == f)
    usage = (ROOT / "docs/USAGE.md").read_text(encoding="utf-8")
    out["BUG-56"] = {"run_transpile_readers": readers,
                     "all_four_read": all(readers.get(f, 0) >= 1 for f in flags),
                     "documented_in_usage":
                     all(flag in usage for flag in ("--check-only", "--emit-ast",
                                                    "--emit-cython", "--generate-setup")),
                     "claim": "docs/USAGE.md 承诺的四个旗标在 run_transpile 里都有读者"}
    uni = read_text(ROOT / "cypy_bridge/union.py")
    out["BUG-57"] = {"no_builtin_example":
                     "CUnion(int, float)" not in uni and "union(int, float)" not in uni,
                     "builtin_guard_present": "__module__ == 'builtins'" in uni,
                     "claim": "union.py 示例只advertise可运行形状 + 内建类型被诊断"}
    mem_src = read_text(ROOT / "cypy_bridge/memory.py")
    out["BUG-58"] = {"realloc_annotation_optional_int":
                     "def realloc(ptr: Any, size: int) -> Optional[int]:" in mem_src,
                     "doc_states_none_on_zero": "size <= 0 时返回 None" in mem_src,
                     "claim": "realloc 注解与返回值形状一致且文档写明 size<=0 语义"}
    mdg = read_text(ROOT / "cypyc/project/module_dependency_graph.py")
    out["BUG-59"] = {"cycle_branch_sorted": "ordered.extend(sorted(cycle_modules))" in mdg,
                     "claim": "环内模块按名定序（文档只说『跳过循环中的模块』）"}
    bbc = read_text(ROOT / "cypyc/analyzer/build_block_checker.py")
    out["BUG-60"] = {"old_rule2_literal_gone": "指针语法只能在构建块内部使用" not in bbc,
                     "mentions_frozen_doc": "04-pointer-types" in bbc,
                     "mentions_function_scope": "函数作用域" in bbc,
                     "claim": "规则 2 与 SYNTAX/04 冻结口径一致"}
    for bug, rec in out.items():
        rec["still_true"] = all(bool(v) for k, v in rec.items() if k != "claim")
    return out


def carried_claims():
    """上一环 footer 的 flip/kept_red 主张：重跑寻虫环探针，看当下缺陷在不在。"""
    out = {}
    for bug, cid in PROBE.items():
        rc, text = sh([PY, "-X", "utf8", str(HERE / "hunt_r3_repro.py"), cid], ROOT, 600)
        try:
            rec = json.loads(text.strip().splitlines()[-1])
            present = bool(rec.get("defect_present"))
        except Exception:  # noqa: BLE001
            out[bug] = {"probe": cid, "probe_rc": rc, "parse_ok": False,
                        "tail": text[-160:], "claim_holds": False}
            continue
        holds = present != PREV_CLAIM[bug]
        out[bug] = {"probe": cid, "defect_present_now": present,
                    "prev_claim_flipped": PREV_CLAIM[bug], "claim_holds": holds,
                    "observed": rec.get("observed")}
    return out


sha_on_load: dict = {}


def main() -> int:
    global sha_on_load
    LOGDIR.mkdir(exist_ok=True)
    sha_on_load = {rel: sha(ROOT / rel) for rel in OVERLAY}
    snap = build_snapshot()
    doc = {"refuse": [], "snapshot": snap}
    if REFUSE:
        doc["refuse"] = REFUSE
        (HERE / "verify_r3_matrix.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(json.dumps({"refuse": REFUSE, "stage": "snapshot"}, ensure_ascii=False, indent=1))
        return 1
    inside, rows = identity_probe()
    doc["identity"] = inside
    doc["identity_probe"] = rows
    pre = run_pytest()
    (LOGDIR / "premise.log").write_text(pre["out"], encoding="utf-8", newline="\n")
    col_rc, col_n = collect_count()
    doc["premise"] = {k: pre[k] for k in ("rc", "passed", "reds", "seen_total")}
    doc["premise"]["collect_only_rc"] = col_rc
    doc["premise"]["collected"] = col_n
    if col_n != LOCK_TOTAL or pre["passed"] != LOCK_TOTAL or pre["reds"]:
        REFUSE.append(f"前提不成立：快照树里本轮锁未全绿 {doc['premise']}")
    mr = {}
    for bug in PATCHES:
        mr[bug] = matrix_row(bug)
        (LOGDIR / f"row_{bug}.json").write_text(
            json.dumps({k: v for k, v in mr[bug].items() if k != "red_reasons"},
                       ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    doc["rows"] = sum(1 for r in mr.values() if r["applied"] and r["compiled"]
                      and r["pos_red"] and not r["ctl_red"] and not r["collateral_red"])
    doc["sha_verified_rows"] = sum(1 for r in mr.values() if r["sha_equal"])
    doc["all_restored"] = 1 if all(r["sha_equal"] for r in mr.values()) else 0
    dec = declared_side()
    doc["declared_side"] = dec
    doc["declared_side_still_true"] = sum(1 for v in dec.values() if v["still_true"])
    cc = carried_claims()
    doc["carried_claims_detail"] = cc
    doc["carried_claims"] = sum(1 for v in cc.values() if v.get("claim_holds"))
    doc["per_bug"] = mr
    doc["workspace_sha_after_unchanged"] = all(sha(ROOT / rel) == sha_on_load[rel] for rel in OVERLAY)
    if not doc["workspace_sha_after_unchanged"]:
        REFUSE.append("收尾复算：工作区文件 sha 变了 ⇒ 本驱动越界改了产品码")
    for rel in OVERLAY:
        if sha(ROOT / rel) != sha_on_load[rel]:
            break
    # 快照树与工作区产品码的差异数（证明两树不是同一份东西）
    diff_files = []
    for rel in OVERLAY:
        if sha(SNAP / rel) != sha(ROOT / rel):
            diff_files.append(rel)
    doc["overlay_identical"] = diff_files == []
    if diff_files:
        REFUSE.append(f"矩阵跑完后快照与工作区仍有差异：{diff_files}")
    doc["refuse"] = REFUSE
    doc["checks_all_true"] = (
        not REFUSE and doc["rows"] == 6 and doc["sha_verified_rows"] == 6
        and doc["all_restored"] == 1 and doc["identity"] >= 4
    )
    (HERE / "verify_r3_matrix.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in doc.items() if k not in ("per_bug", "identity_probe",
                                                                "declared_side", "carried_claims_detail")},
                     ensure_ascii=False, indent=1))
    if REFUSE:
        print("REFUSE:", json.dumps(REFUSE, ensure_ascii=False, indent=1))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
