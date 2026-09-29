"""R4-寻虫 的候选表与被测树的批量跑入口——所有 hunt_r4_*.py 共用这一份，避免各处重打字面量。

三条口径写在这里：
- `expect` 是「文档声明的语义应当怎样」，不是「今天怎样」；观察与期望不符 = 候选缺陷。
- `needs_arity_check` 只标「今天这条**现象本身就是那一行判定产出的**」（假阳性），
  假阴性今天没走判定 ⇒ 变异树不会让它变化，标 True 就是在造一条必红的假对照。
- 每条候选必须带一条 `ctl`：**同族里今天行为正确**的形状。ctl 今天就不对 ⇒ 这一条只能记 UNSURE
  （ neighbourhood 整体坏了，不能归因到某个具体检查上）。
- 批量跑：一次子进程吃全部源，逐档回 `{'ident':…, 'errors':[…]}`；身份探针与观察同一批产出。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
ARITY = "Callable arity mismatch"
MISMATCH = "mismatch"
DECL = "type Callback = Callable[[int], str]\n"
ONE = "def one(a: int) -> str:\n    return \"\"\n\n"
BASE = DECL + ONE + "def mk(cb: Callback, n: int) -> Callback:\n    return cb\n\n"
NEEDLE = "                        self._check_callable_arity(node, args)\n"
IMPORTABLE = ("cypyc", "cypy_hook", "cypy_bridge")
CALL_G = lambda body: BASE + "def g() -> None:\n    " + body + "\n"  # noqa: E731

# 今天行为正确、用来做归属对照的形状（ctl 集）
CTLS = {
    "return_mismatch_reported": ("def mk() -> int:\n    return \"\"\n", "mismatch"),
    "alias_identity_clean": (DECL + "def mk(cb: Callback) -> Callback:\n    return cb\n", "clean"),
    "callback_arity_reported": (DECL + "def a(cb: Callback) -> str:\n    return cb(1, 2)\n", "arity"),
    "assignment_mismatch_reported":
        ("def g() -> int:\n    let x: int = \"s\"\n    return x\n", "mismatch"),
    "local_let_flows_to_return": ("def f() -> str:\n    let n: int = 1\n    return n\n", "mismatch"),
    "int_field_as_int_clean": ("struct S:\n    n: int\n\n    def f(self) -> int:\n        return self.n\n",
                               "clean"),
    "plain_message_shape_ok": ("def g() -> None:\n    let x: int = \"s\"\n    return\n", "clean_message"),
}

# 12 条候选，按根因分四组（RC-1..RC-4）
CANDIDATES = [
    {"id": "C01", "rc": "RC1_func_symbol_typed_as_return", "family": "F1",
     "case": "correct_two_arg_call_of_local_function", "src": CALL_G("mk(one, 1)"),
     "want": "clean", "kind": "false_positive",
     "phenomenon": "正确程序被判「Callable arity mismatch: expected 1, got 2」",
     "ctl": "return_mismatch_reported", "needs_arity_check": True},
    {"id": "C02", "rc": "RC1_func_symbol_typed_as_return", "family": "F1",
     "case": "missing_arg_call_of_local_function", "src": CALL_G("mk(one)"),
     "want": "error", "kind": "false_negative",
     "phenomenon": "少传一个实参的调用完全静默",
     "ctl": "return_mismatch_reported", "needs_arity_check": False},
    {"id": "C03", "rc": "RC1_func_symbol_typed_as_return", "family": "F1",
     "case": "function_with_matching_signature_returned_as_alias",
     "src": DECL + ONE + "def mk() -> Callback:\n    return one\n",
     "want": "clean", "kind": "false_positive",
     "phenomenon": "签名相符的函数被当成它的返回类型（got str）而拒绝",
     "ctl": "alias_identity_clean", "needs_arity_check": False},
    {"id": "C04", "rc": "RC1_func_symbol_typed_as_return", "family": "F2",
     "case": "plain_fn_called_with_extra_arg",
     "src": "def mk() -> int:\n    return 1\n\ndef g() -> int:\n    return mk(1, 2)\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "普通函数多传实参不判（只有形参声明为 Callable 时才判元数）",
     "ctl": "callback_arity_reported", "needs_arity_check": False},
    {"id": "C05", "rc": "RC1_func_symbol_typed_as_return", "family": "F2",
     "case": "plain_fn_called_with_missing_arg",
     "src": "def mk(k: int) -> int:\n    return k\n\ndef g() -> int:\n    return mk()\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "普通函数少传实参不判",
     "ctl": "callback_arity_reported", "needs_arity_check": False},
    {"id": "C06", "rc": "RC2_no_argument_type_check", "family": "F3",
     "case": "wrong_signature_passed_to_callback_param",
     "src": DECL + "def three(a: int, b: int) -> str:\n    return \"\"\n"
     "def apply(f: Callback) -> str:\n    return f(1)\n"
     "def g() -> str:\n    return apply(three)\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "两参函数被传给 Callable[[int], str] 形参不判",
     "ctl": "assignment_mismatch_reported", "needs_arity_check": False},
    {"id": "C07", "rc": "RC2_no_argument_type_check", "family": "F3",
     "case": "non_callable_passed_to_callback_param",
     "src": DECL + "def apply(f: Callback) -> str:\n    return f(1)\n"
     "def g() -> str:\n    return apply(42)\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "整型字面量被传给 Callable 形参不判",
     "ctl": "assignment_mismatch_reported", "needs_arity_check": False},
    {"id": "C08", "rc": "RC2_no_argument_type_check", "family": "F3",
     "case": "str_arg_to_annotated_int_param",
     "src": "def apply(n: int) -> int:\n    return n\n\ndef g() -> int:\n    return apply(\"s\")\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "字符串实参传给 int 形参不判（同族 `let x: int = \"s\"` 却报）",
     "ctl": "assignment_mismatch_reported", "needs_arity_check": False},
    {"id": "C09", "rc": "RC3_struct_field_type_unresolved", "family": "F4",
     "case": "int_field_returned_from_str_method",
     "src": "struct S:\n    n: int\n\n    def f(self) -> str:\n        return self.n\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "struct 成员的声明类型在方法体里不被解析（同族局部变量却解析）",
     "ctl": "local_let_flows_to_return", "needs_arity_check": False},
    {"id": "C10", "rc": "RC3_struct_field_type_unresolved", "family": "F4",
     "case": "nested_field_wrong_type",
     "src": "struct Inner:\n    n: int\nstruct Outer:\n    i: Inner\n\n"
     "    def f(self) -> str:\n        return self.i.n\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "嵌套成员链的类型同样不被解析",
     "ctl": "local_let_flows_to_return", "needs_arity_check": False},
    {"id": "C11", "rc": "RC3_struct_field_type_unresolved", "family": "F4",
     "case": "field_used_with_wrong_arity_call",
     "src": DECL + "struct S:\n    cb: Callback\n\n    def f(self) -> str:\n        return self.cb(1, 2)\n",
     "want": "error", "kind": "false_negative",
     "phenomenon": "成员当回调调用时元数不判（局部变量同形状会判）",
     "ctl": "callback_arity_reported", "needs_arity_check": False},
    {"id": "C12", "rc": "RC4_internal_repr_in_message", "family": "F5",
     "case": "alias_mismatch_message_is_source_shape",
     "src": DECL + "def g() -> int:\n    let x: Callback = 1\n    return x\n",
     "want": "clean_message", "kind": "message_shape",
     "phenomenon": "用户可见文案写的是 `Callable[tuple[int], str]`，不是源语法 `Callable[[int], str]`",
     "ctl": "plain_message_shape_ok", "needs_arity_check": False},
]

RUNNER = (
    "import sys, json\n"
    "root = sys.argv[1]\n"
    "sys.path.insert(0, root)\n"
    "from cypy_hook.hook import CypyHook\n"
    "import cypyc.analyzer.type_checker as tc\n"
    "hook = CypyHook()\n"
    "rows = []\n"
    "for src in json.loads(sys.stdin.read()):\n"
    "    try:\n"
    "        _, e = hook.analyze_only(src)\n"
    "        errs = list(e)\n"
    "    except Exception as exc:\n"
    "        errs = ['RUNNER-EXC ' + type(exc).__name__ + ': ' + str(exc)]\n"
    "    rows.append(errs)\n"
    "print(json.dumps({'ident': tc.__file__, 'rows': rows}, ensure_ascii=False))\n"
)


def run_batch(sources: list, tree: Path | None = None) -> dict:
    """一次子进程跑一批源；返回 {'ident':…, 'rows':[…]}，rows 与 sources 同序。"""
    target = str(tree or ROOT)
    p = subprocess.run([PY, "-X", "utf8", "-c", RUNNER, target], cwd=target,
                       input=json.dumps(sources, ensure_ascii=False),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"批量分析器 rc={p.returncode}: {(p.stdout + p.stderr)[-400:]}")
    got = json.loads(p.stdout.strip().splitlines()[-1])
    want = str(Path(target) / "cypyc" / "analyzer" / "type_checker.py").replace("\\", "/").lower()
    got_norm = Path(got["ident"]).as_posix().replace("\\", "/").lower()
    if got_norm != want:
        raise RuntimeError(f"跑的不是目标树：期望 {want} 实得 {got_norm}")
    if len(got["rows"]) != len(sources):
        raise RuntimeError(f"回的行数 {len(got['rows'])} ≠ 送出的源 {len(sources)}")
    return {"ident": got_norm, "rows": got["rows"]}


def observed_kind(errs: list) -> dict:
    """把一次观察归成可对照的形状：报了什么类别、有没有内部 repr 外泄。"""
    return {"errors": errs,
            "arity": any(ARITY in e for e in errs),
            "mismatch": any(MISMATCH in e for e in errs),
            "any_type_error": any(MISMATCH in e or ARITY in e for e in errs),
            "leaks_internal_repr": any("tuple[" in e or "generic_params" in e for e in errs)}


def defect_seen(obs: dict, cand: dict) -> bool:
    """现象现形的**正面**定义（不是「与期望不符」的取反）；两套编码由 confirm 环互校。"""
    if cand["kind"] == "false_positive":
        return obs["any_type_error"]
    if cand["kind"] == "false_negative":
        return not obs["any_type_error"]
    if cand["kind"] == "message_shape":
        return obs["any_type_error"] and obs["leaks_internal_repr"]
    raise ValueError(f"未知 kind {cand['kind']}")


def satisfies(obs: dict, spec: str) -> bool:
    """`spec` 是这一档「应当观察到什么」；满足=今天行为正确（对候选来说=不满足才算现象现形）。"""
    if spec == "clean":
        return not obs["any_type_error"]
    if spec == "error":
        return obs["any_type_error"]
    if spec == "mismatch":
        return obs["mismatch"]
    if spec == "arity":
        return obs["arity"]
    if spec == "clean_message":
        return obs["any_type_error"] and not obs["leaks_internal_repr"]
    raise ValueError(f"未知 spec {spec}")


def main() -> int:
    print(json.dumps({"candidates": len(CANDIDATES), "ctl_library": len(CTLS),
                      "root_causes": sorted({c["rc"] for c in CANDIDATES})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
