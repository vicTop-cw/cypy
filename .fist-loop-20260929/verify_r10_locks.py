"""R10 验证腿：变异矩阵 —— 证明新锁与 Ω-spec 是**承重的**，不是自我循环的绿灯。

六格（每格一棵独立树，树名带 pid 防并发掏空）：
 L0 live 树（本轮修复后）           ⇒ 期望 pytest 0 红、gate 14/14 rc=0
 L1 三处全部退回修复前               ⇒ 期望两把尺子都红
 L2 只退解析器（含 Call 字段与调用点块）⇒ 期望多实参/擦除/元数那几支红
 L3 只退分析器（删 _bind_explicit_type_args）⇒ 期望元数/非泛型/代入那几支红
 L4 只把产物改回 `(类型名(), f(x))[1]` 形态 ⇒ 期望四条擦除锁红（运行期危害面）
 L5 只改注释（语义逐字不变）          ⇒ 期望 0 红：尺子没在数我的散文

承重判定：L1..L4 每格至少 1 红（单变量摘除仍红 ⇒ 那一处确实在承重），L5 必须 0 红。
红行按形状解析（`FAILED <nodeid>` 与 `N failed in` 汇总行），并断言解析到的数与汇总数一致。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP = ["cypyc", "cypy_bridge", "scripts", "corpus", "tests", "examples", "SYNTAX", "PROJECT-SPEC"]
LOCK_FILE = "tests/test_generic_callsite_r10.py"

CG_NEW = """        # 类型实参在产物里必须**擦除**（SYNTAX/11「调用点的类型实参」规则 4）：
        # 过去的写法是 `(类型名(), f(args))[1]` —— 那是把类型名当零参函数调用一次，
        # 对 `int`/`str` 只是侥幸能跑，对带必填字段的 struct/class 必然在运行期抛 TypeError，
        # 且类型检查与产物生成都不报错（静默错误产物）。静态代入由分析器负责，产物只留调用本身。
        func_node = node.func"""
CG_OLD = """        # 如果有调用时的 checker，在调用前调用 checker
        # 使用逗号表达式：(checker(), func(args))[1] 获取函数调用结果
        if node.checker:
            return f"({node.checker}(), {self._expr_to_str(node.func)}({args}))[1]"

        func_node = node.func"""
CG_TUPLE = """        if getattr(node, "type_args", None):
            _ta0 = self._type_to_str(node.type_args[0])
            return f"({_ta0}(), {self._expr_to_str(node.func)}({args}))[1]"

        func_node = node.func"""

PA_NEW = """class Call(ASTNode):
    def __init__(
        self, func: Any, args: List[Any], type_args: Optional[List[Any]] = None,
        line: int = 0, col: int = 0
    ):
        super().__init__("Call", line, col)
        self.func = func
        self.args = args
        # SYNTAX/11「调用点的类型实参」：`f<A, B>(…)` 尖括号里的类型实参表（可为空）。
        self.type_args = type_args or []"""
PA_OLD = """class Call(ASTNode):
    def __init__(
        self, func: Any, args: List[Any], checker: Optional[str] = None, line: int = 0, col: int = 0
    ):
        super().__init__("Call", line, col)
        self.func = func
        self.args = args
        self.checker = checker  # 调用时指定的 <checker> 参数检查站名称"""

PB_NEW_HEAD = """        # 记录调用点的类型实参（SYNTAX/11「调用点的类型实参」）
        type_args_for_call: List[Any] = []"""
PB_OLD_HEAD = """        # 记录 checker 名称（用于 func<checker>(args) 或 func<checker>[generic](args)）
        checker_name_for_call = None"""
PC_NEW = """                    type_args_for_call,
                    getattr(func, "line", 0),
                    getattr(func, "col", 0),
                )
                # 实参表只属于紧邻的这一次调用（链式 `f<T>(a)(b)` 的第二段不继承）
                type_args_for_call = []"""
PC_OLD = """                    checker_name_for_call,
                    getattr(func, "line", 0),
                    getattr(func, "col", 0),
                )"""

AA_NEW_HEAD = """            explicit_binding = self._bind_explicit_type_args(node, func_name)
            if func_name in self.func_defs:"""
AA_OLD_HEAD = """            if func_name in self.func_defs:"""
AA_NEW_IF = """                if generic_params:
                    if explicit_binding:
                        inferred_types = explicit_binding
                    else:
                        # 双向检查：尝试从上下文获取期望类型辅助推断
                        expected = self._get_expected_type_from_context(node)
                        if expected:
                            # 使用期望类型辅助推断
                            inferred_types = self._infer_generic_types_with_expected(
                                func_def, node.args, generic_params, expected
                            )
                        else:
                            # 使用统一化算法推断泛型参数类型
                            inferred_types = self._infer_generic_types(func_def, node.args, generic_params)"""
AA_OLD_IF = """                if generic_params:
                    # 双向检查：尝试从上下文获取期望类型辅助推断
                    expected = self._get_expected_type_from_context(node)
                    if expected:
                        # 使用期望类型辅助推断
                        inferred_types = self._infer_generic_types_with_expected(
                            func_def, node.args, generic_params, expected
                        )
                    else:
                        # 使用统一化算法推断泛型参数类型
                        inferred_types = self._infer_generic_types(func_def, node.args, generic_params)"""

AB_METHOD_MARK = "    def _bind_explicit_type_args(self, node: Call, func_name: str)"
AB_METHOD_END_MARK = "    def _visit_Call(self, node: Call) -> Optional[Type]:"


LT_UNIQUE = "                saved_pos = self.pos"
OLD_CALLSITE_BLOCK = '''            # 检查是否是 func<checker> 模式
            if self._current().type == TokenType.LT:
                # 查看后面是否是标识符 + >
                next_token = self._peek()
                if next_token and next_token.type == TokenType.IDENTIFIER:
                    # 预看第三个 token 是否是 >
                    peek_gt = self._peek_ahead(2)
                    if peek_gt == TokenType.GT:
                        # 这是 func<checker> 模式
                        self._consume()  # consume <
                        checker_name_for_call = self._consume(TokenType.IDENTIFIER).value
                        self._consume()  # consume >
                        # 继续循环处理后续的 [generic] 或 (args)
                        continue

'''


def revert_parser(text: str) -> str:
    """把调用点那一整块试探逻辑换回修复前的单标识符形态。

    锚点纪律（既往轮的教训：`index()` 命中更早的同名行 ⇒ 剪错区间、文件被毁）：
    起始锚必须用**本环亲笔**的唯一行，切点用"锚之后第一个" LPAREN 行，切完必须能 compile。
    """
    for anchor in (PA_NEW, PB_NEW_HEAD, PC_NEW, LT_UNIQUE):
        assert text.count(anchor) == 1, f"锚点命中 {text.count(anchor)} 次（应为 1）：{anchor[:46]!r}"
    lines = text.splitlines(keepends=True)
    # 逐字（含缩进）匹配：`saved_pos = self.pos` 在 parser.py 里另有 12 空格缩进的同名行（:3074 区），
    # 按 strip() 取"第一个命中"会切错区间 ⇒ 这里要求全文件只有一个 16 空格形态。
    hits = [k for k, ln in enumerate(lines) if ln.rstrip("\n") == LT_UNIQUE]
    assert len(hits) == 1, f"LT 锚行命中 {len(hits)} 次（应为 1）"
    i = hits[0]
    j = i - 1
    # 往上把本环写的注释块 + LT 分支行一并吃掉，停在 `while True:`（它既非注释也非 LT 行）
    while j >= 0 and (lines[j].lstrip().startswith("#")
                      or lines[j].strip().startswith("if self._current().type == TokenType.LT:")):
        j -= 1
    k = next(m for m in range(i, len(lines))
             if lines[m].strip() == "if self._current().type == TokenType.LPAREN:")
    assert j + 1 < i < k, f"区间异常 j={j} i={i} k={k}"
    assert k - (j + 1) < 40, f"待替换区间 {k - (j + 1)} 行，远超本环那一块 ⇒ 锚点找错，拒绝改树"
    out = "".join(lines[:j + 1]) + OLD_CALLSITE_BLOCK + "".join(lines[k:])
    out = out.replace(PA_NEW, PA_OLD).replace(PB_NEW_HEAD, PB_OLD_HEAD).replace(PC_NEW, PC_OLD)
    assert out.count("checker_name_for_call = self._consume(TokenType.IDENTIFIER).value") == 1
    assert "type_args_for_call" not in out
    compile(out, "parser_reverted", "exec")  # 复原出来的必须是合法 Python，否则是尺子坏了
    return out


def copy_tree(dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in KEEP:
        shutil.copytree(ROOT / name, dst / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("pytest.ini", "pyproject.toml", "setup.py", "conftest.py", "mypy.ini"):
        if (ROOT / f).exists():
            shutil.copy(ROOT / f, dst / f)


def apply_mut(dst: Path, faces) -> list:
    """faces 里每个面是一组 (相对路径, old, new)；返回逐条替换自证清单。"""
    log = []
    for face in faces:
        for rel, old, new in face:
            p = dst / rel
            t = p.read_text(encoding="utf-8")
            n = t.count(old)
            assert n == 1, f"锚点 {rel} 命中 {n} 次（必须恰好 1 次）：{old[:60]!r}"
            p.write_text(t.replace(old, new, 1), encoding="utf-8", newline="\n")
            assert new in p.read_text(encoding="utf-8")
            log.append({"file": rel, "needle": old[:48]})
    return log


def run_pytest(dst: Path) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", LOCK_FILE,
                        "tests/regression/test_corpus_pairs.py", "-p", "no:cacheprovider",
                        "--tb=no", "-rf"],
                       cwd=str(dst), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env)
    out = r.stdout + r.stderr
    failed = sorted({m for m in re.findall(r"(?m)^FAILED (\S+)", out)})
    summary = re.findall(r"=+ .*(?:failed|passed|error).*?=+", out)
    # rc=2/3/4 是 pytest 自己没跑起来（收集期 ImportError 等）⇒ 那是"树坏了"，不能读成"0 红"
    return {"rc": r.returncode, "failed_ids": failed, "n_failed": len(failed),
            "crash": r.returncode not in (0, 1),
            "collect_errors": len(re.findall(r"(?m)^ERROR ", out)),
            "summary_line": (summary[-1] if summary else ""),
            "stdout_tail": out[-300:]}


def run_gate(dst: Path) -> dict:
    r = subprocess.run([sys.executable, "-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.callsite"],
                       cwd=str(dst), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    m = re.search(r"CONCLUSION specs=(\d+) cases=(\d+) passed=(\d+) failed=(\d+) refused=(\d+)", out)
    conc = [ln for ln in out.splitlines() if ln.startswith("CONCLUSION")]
    return {"rc": r.returncode, "conclusion": conc[-1] if conc else out[-260:],
            "parsed": list(map(int, m.groups())) if m else None}


def identity(dst: Path) -> dict:
    pa = (dst / "cypyc/parser/parser.py").read_text(encoding="utf-8")
    cg = (dst / "cypyc/codegen/cython_generator.py").read_text(encoding="utf-8")
    tc = (dst / "cypyc/analyzer/type_checker.py").read_text(encoding="utf-8")
    return {"parser_has_type_args": "self.type_args = type_args or []" in pa,
            "parser_has_checker": "checker_name_for_call = self._consume(TokenType.IDENTIFIER).value" in pa,
            "codegen_has_tuple": "if node.checker:" in cg or "_ta0" in cg,
            "analyzer_has_binding": AB_METHOD_MARK in tc}


def main() -> int:
    cases = {}
    live = {"faces": [], "label": "L0 live（修复后）"}
    cases["L0"] = live
    cases["L1"] = {"label": "L1 三处全退", "faces": [
        [("cypyc/codegen/cython_generator.py", CG_NEW, CG_OLD)],
        [("cypyc/analyzer/type_checker.py", AA_NEW_HEAD, AA_OLD_HEAD),
         ("cypyc/analyzer/type_checker.py", AA_NEW_IF, AA_OLD_IF)],
    ], "parser_full_revert": True, "drop_binding_method": True}
    cases["L2"] = {"label": "L2 只退解析器", "faces": [], "parser_full_revert": True}
    cases["L3"] = {"label": "L3 只退分析器", "faces": [
        [("cypyc/analyzer/type_checker.py", AA_NEW_HEAD, AA_OLD_HEAD),
         ("cypyc/analyzer/type_checker.py", AA_NEW_IF, AA_OLD_IF)],
    ], "drop_binding_method": True}
    cases["L4"] = {"label": "L4 产物退回零参调用形态", "faces": [
        [("cypyc/codegen/cython_generator.py", CG_NEW, CG_TUPLE)]]}
    cases["L5"] = {"label": "L5 只改注释（语义不变，对照格）", "faces": [
        [("cypyc/codegen/cython_generator.py",
          "        # 且类型检查与产物生成都不报错（静默错误产物）。静态代入由分析器负责，产物只留调用本身。",
          "        # 且检查与出码两侧都不报错。代入归分析器，产物只留调用。")]]}

    rep = {"pid": os.getpid(), "cases": {}}
    base = ROOT / f".lockproof_r10_{os.getpid()}"
    for key, spec in cases.items():
        dst = base / key
        copy_tree(dst)
        log = []
        if spec.get("parser_full_revert"):
            p = dst / "cypyc/parser/parser.py"
            t = p.read_text(encoding="utf-8")
            p.write_text(revert_parser(t), encoding="utf-8", newline="\n")
            log.append({"file": "cypyc/parser/parser.py", "needle": "full revert (3 hunks + lookahead block)"})
        if spec.get("drop_binding_method"):
            p = dst / "cypyc/analyzer/type_checker.py"
            t = p.read_text(encoding="utf-8")
            i = t.index(AB_METHOD_MARK)
            j = t.index(AB_METHOD_END_MARK)
            assert i < j
            p.write_text(t[:i] + t[j:], encoding="utf-8", newline="\n")
            log.append({"file": "cypyc/analyzer/type_checker.py", "needle": "drop _bind_explicit_type_args"})
        log += apply_mut(dst, spec["faces"])
        pt, gt = run_pytest(dst), run_gate(dst)
        rep["cases"][key] = {"label": spec["label"], "mutations": log, "identity": identity(dst),
                             "pytest": pt, "gate": gt}
        print(f"[{key}] {spec['label']} | pytest rc={pt['rc']} red={pt['n_failed']} crash={pt['crash']} "
              f"| gate {gt['conclusion'][:78]} | ident={json.dumps(rep['cases'][key]['identity'])}")
        for fid in pt["failed_ids"]:
            print("     RED", fid)
        if pt["crash"]:
            print("     CRASH-TAIL", pt["stdout_tail"][:240].replace("\n", " / "))

    # 承重门
    cs = rep["cases"]
    gates = {
        "L0_pytest_green": cs["L0"]["pytest"]["n_failed"] == 0 and cs["L0"]["pytest"]["rc"] == 0,
        "L0_gate_100": bool(cs["L0"]["gate"]["parsed"]) and cs["L0"]["gate"]["parsed"][3:5] == [0, 0],
        "no_ruler_crash_in_any_case": all(not c["pytest"]["crash"] for c in cs.values()),
        "L1_load_bearing": cs["L1"]["pytest"]["n_failed"] >= 1 and cs["L1"]["gate"]["rc"] == 1,
        "L2_parser_only_red": cs["L2"]["pytest"]["n_failed"] >= 1 and cs["L2"]["gate"]["rc"] == 1,
        "L3_analyzer_only_red": cs["L3"]["pytest"]["n_failed"] >= 1,
        "L4_erasure_only_red": cs["L4"]["pytest"]["n_failed"] >= 1,
        "L5_comment_control_green": cs["L5"]["pytest"]["n_failed"] == 0,
        "identity_mutations_landed": (
            cs["L0"]["identity"] == {"parser_has_type_args": True, "parser_has_checker": False,
                                     "codegen_has_tuple": False, "analyzer_has_binding": True}
            and cs["L2"]["identity"]["parser_has_type_args"] is False
            and cs["L2"]["identity"]["parser_has_checker"] is True
            and cs["L3"]["identity"]["analyzer_has_binding"] is False
            and cs["L3"]["identity"]["parser_has_type_args"] is True
            and cs["L4"]["identity"]["codegen_has_tuple"] is True),
    }
    rep["gates"] = gates
    rep["conclusion_ok"] = all(gates.values())
    Path(__file__).with_name("verify_r10_locks.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(base, ignore_errors=True)
    print("GATES", json.dumps(gates, ensure_ascii=False))
    print(f"CONCLUSION cases={len(rep['cases'])} gates_pass={sum(1 for v in gates.values() if v)}/"
          f"{len(gates)} ok={rep['conclusion_ok']}")
    return 0 if rep["conclusion_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
