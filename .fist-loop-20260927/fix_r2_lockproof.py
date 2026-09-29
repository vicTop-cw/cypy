#!/usr/bin/env python3
"""R2-修复：证明 6 条锁**各自承重**——只回退某一单，它的锁必须红，别人的锁必须绿。

树不是从 HEAD 来的：本仓 HEAD(17d68b4) 之后有 09-26 轮与 R1 轮的**未提交**改动，
HEAD 码跑不动当前 tests。所以底树 = 当前工作树的**必要子集**，回退 = 在本脚本里
对每单做「修复后文本 → 修复前文本」的精确替换（每处 `count==1` 才落，锚点错了直接 REFUSE）。

四条判据（与 R1-推进同款，另加一条归因分离）：
1. 回退 X ⇒ X 的锁至少 1 条红（否则锁不承重）；
2. 回退 X ⇒ 其他单的用例全绿（混因 ⇒ 判据在测同一件事，或回退串了）；
3. 完整树（不回退）全绿且 18 条全被收集；
4. 回退 X ⇒ X 自己的**对照**用例仍绿（对照是"必然不误抓"的那半边）。

已知并刻意消除的耦合（否则判据 2 会误报）：BUG-46 的对照探针走 `cypy_hook.hook`
而不是包级 API（包级再导出属 BUG-47）；BUG-35 的夹具用**顶层 defer**（其越域诊断
本轮之前就有）而不是顶层 return（那是 BUG-39 新加的守卫）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
TESTS = "tests/test_loop_20260927_fix_r2.py"

GEN = "cypyc/codegen/cython_generator.py"
PARSER = "cypyc/parser/parser.py"
HOOK = "cypy_hook/hook.py"
CLI = "cypyc/cli.py"
PKG = "cypy_hook/__init__.py"
DOC = "docs/USAGE.md"

LOCKS = {
    "bug44": [
        "test_bug44_struct_selfless_methods_drop_injected_self",
        "test_bug44_at_cli_product_is_transpiled_without_self",
    ],
    "bug45": [
        "test_bug45_implicit_default_desugars_to_typed_call",
        "test_bug45_implicit_default_without_annotation_is_diagnosed",
    ],
    "bug39": [
        "test_bug39_toplevel_return_is_diagnosed_at_cli",
        # 这条名字里有 control，但它断言的是「守卫真的在拦」⇒ 归 bug39 的锁，
        # 回退守卫时它必须红（放进对照会让"回退必转红"的判据漏掉一半）。
        "test_bug39_control_fragment_without_body_scope_still_rejected",
    ],
    "bug35": ["test_bug35_parse_diagnosis_is_not_bucketed_as_read_error"],
    "bug46": [
        "test_bug46_install_and_status_agree_on_process_scope",
        "test_bug46_usage_doc_matches_the_narrowed_claim",
    ],
    "bug47": [
        "test_bug47_package_level_hook_api_exists",
        "test_bug47_in_process_install_then_uninstall",
    ],
    # 反过收窄面：守卫吃掉宏体 return 会红这三条（全量套件抓到过一次真回归）。
    # 它不参与逐单回退（回退 BUG-39 的守卫本身不会让它红），只参与混因与收集检查。
    "macro_exemption": [
        "test_bug39_macro_body_return_stays_legal",
        "test_bug39_expanded_fragment_return_stays_legal",
    ],
}
CONTROLS = {
    "bug44": ["test_bug44_control_bound_struct_method_keeps_self_and_binding"],
    "bug45": ["test_bug45_control_ordinary_default_untouched"],
    "bug39": ["test_bug39_control_return_inside_function_still_builds"],
    "bug35": ["test_bug35_control_missing_file_still_reports_read_error"],
    "bug46": ["test_bug46_fresh_process_reports_not_active"],
    "bug47": [],
    "macro_exemption": [],
}

# 每单：[(文件, 修复后文本, 修复前文本), ...]
REVERTS = {
    "bug44": [
        (
            GEN,
            "        # 检查方法是否已经有 self 参数\n"
            "        # @staticmethod/@classmethod 不绑定实例：视作「已带 self」以跳过自动注入"
            "（struct 路径）\n"
            "        selfless = self._is_selfless_method(node)\n"
            '        has_self = (bool(node.params) and node.params[0].name == "self")'
            " or selfless\\n",
            "        # 检查方法是否已经有 self 参数\n"
            "        has_self = node.params and node.params[0].name == 'self'\n",
        ),
        (
            GEN,
            "                # 在访问方法之前添加优化装饰器；binding(False)"
            " 只对绑定方法有意义（BUG-44）\n"
            "                if not self._is_selfless_method(method):\n"
            '                    self._write("@cython.binding(False)")\n',
            "                # 在访问方法之前添加优化装饰器\n"
            '                self._write("@cython.binding(False)")\n',
        ),
    ],
    "bug45": [
        (
            GEN,
            '                param_str = f"{param_str}={self._param_default_str(param)}"',
            '                param_str = f"{param_str}={self._expr_to_str(param.default_value)}"',
        ),
        (
            PARSER,
            "                    default_value = self._parse_expression()\n"
            "                    if (\n"
            '                        getattr(default_value, "id", None) == "__implicit_default__"\n'
            "                        and type_annotation is None\n"
            "                    ):\n"
            "                        raise ValueError(\n"
            '                            "__implicit_default__ default needs a parameter type'
            ' to desugar to, "\n'
            '                            f"found at {name_token.line}:{name_token.col}"\n'
            "                        )\n",
            "                    default_value = self._parse_expression()\n",
        ),
    ],
    "bug39": [
        (
            PARSER,
            "        token = self._consume(TokenType.RETURN)\n"
            '        self._require_function_scope("return", token)\n',
            "        self._consume(TokenType.RETURN)\n",
        ),
    ],
    "bug35": [
        (
            HOOK,
            "            try:\n"
            '                with open(source_path, "r", encoding="utf-8") as f:\n'
            "                    source = f.read()\n"
            "            except OSError as read_err:\n"
            "                # 只有 I/O 失败才归入「读取文件错误」：解析/生成异常此前也被写成本桶，\n"
            "                # 用户看到的首行会是「读取文件错误: Expected ...」这类与文件无关的诊断\n"
            '                result.errors.append(f"读取文件错误: {read_err}")\n'
            "                return result\n",
            '            with open(source_path, "r", encoding="utf-8") as f:\n'
            "                source = f.read()\n",
        ),
        (
            HOOK,
            '                    result.errors.append(f"生成.pyx文件错误: {write_err}")\n'
            "                    return result\n"
            "\n"
            "            return result\n"
            "\n"
            "        except Exception as e:\n"
            '            result.errors.append(f"编译错误: {e}")\n',
            '                    result.errors.append(f"生成.pyx文件错误: {write_err}")\n'
            "                    return result\n"
            "\n"
            "            return result\n"
            "\n"
            "        except Exception as e:\n"
            '            result.errors.append(f"读取文件错误: {e}")\n',
        ),
    ],
    "bug46": [
        (
            CLI,
            '            print("[OK] Cypy import hook registered for the current process")\n'
            '            print("  Nothing is written to disk: the hook dies with this process.")\n'
            '            print("  To enable it in your own process, call'
            ' cypy_hook.install_hook() at startup.")\n',
            '            print("[OK] Cypy import hook installed successfully")\n'
            "            print(\"  Now you can import .py files with '#!bin cypy' header"
            ' directly")\n',
        ),
        (
            CLI,
            '            print("[OK] Cypy import hook unregistered for the current process")',
            '            print("[OK] Cypy import hook uninstalled successfully")',
        ),
        (
            CLI,
            '                print("[OK] Cypy import hook is active in the current process")',
            '                print("[OK] Cypy import hook is installed")',
        ),
        (
            CLI,
            '                print("[INFO] Cypy import hook is not active in the current'
            ' process")\n'
            '                print("  Cypy writes no persistent registration:")\n'
            '                print("  the hook lives or dies with the process that installed'
            ' it.")\n',
            '                print("[FAIL] Cypy import hook is not installed")\n',
        ),
        (
            DOC,
            "cypyc hook install        # 在**当前进程**内注册 import hook（不写盘、不跨进程生效）\n"
            "cypyc hook uninstall      # 在当前进程内注销\n"
            "cypyc hook status         # 报告当前进程内是否已注册\n",
            "cypyc hook install        # 安装 import hook（写入用户 sitecustomize / 注册）\n"
            "cypyc hook uninstall      # 卸载\n"
            "cypyc hook status         # 查看是否已安装\n",
        ),
    ],
    "bug47": [
        (
            PKG,
            "from .hook import CypyHook, install_hook, is_hook_installed, uninstall_hook\n"
            '\n__all__ = ["CypyHook", "install_hook", "uninstall_hook", "is_hook_installed"]\n',
            'from .hook import CypyHook\n\n__all__ = ["CypyHook"]\n',
        ),
    ],
}

COPY_ITEMS = ["cypyc", "cypy_hook", "cypy_bridge", "docs", "pyproject.toml", "setup.cfg"]


def build_tree(base: Path, who: str | None) -> Path:
    tree = base / f"tree_{who or 'full'}"
    tree.mkdir(parents=True, exist_ok=True)
    for item in COPY_ITEMS:
        src = ROOT / item
        if not src.exists():
            continue
        dst = tree / item
        if src.is_dir():
            shutil.copytree(
                src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyd"), dirs_exist_ok=True
            )
        else:
            shutil.copy2(src, dst)
    (tree / "tests").mkdir(exist_ok=True)
    shutil.copy2(ROOT / TESTS, tree / TESTS)
    if who:
        for rel, new, old in REVERTS[who]:
            path = tree / rel
            text = path.read_text(encoding="utf-8")
            hits = text.count(new)
            if hits != 1:
                raise AssertionError(f"回退锚点不唯一：{who} {rel} count={hits} for {new[:50]!r}")
            path.write_text(text.replace(new, old), encoding="utf-8", newline="\n")
        # 回退后必须真的回到「修复前」文本，否则替换根本没生效
        for rel, _new, old in REVERTS[who]:
            if old not in (tree / rel).read_text(encoding="utf-8"):
                raise AssertionError(f"回退未生效：{who} {rel} 找不到修复前文本")
    return tree


def run_tests(tree: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tree)
    r = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            TESTS,
            "-v",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "-o",
            "addopts=",
        ],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    out = (r.stdout or "") + (r.stderr or "")
    (HERE / f"fix_r2_lockproof_{tree.name}.log").write_text(out, encoding="utf-8", newline="\n")
    per_line = re.findall(r"^\S+::(\w+)\s+(PASSED|FAILED)", out, flags=re.M)
    failed = sorted(
        {n for n, s in per_line if s == "FAILED"}
        | set(re.findall(r"^FAILED \S+::(\w+)", out, flags=re.M))
    )
    passed = sorted({n for n, s in per_line if s == "PASSED"})
    summary = [
        ln for ln in out.splitlines() if " passed" in ln or " failed" in ln or " error" in ln
    ]
    return {
        "rc": r.returncode,
        "failed": failed,
        "passed": passed,
        "collected": len(failed) + len(passed),
        "line": summary[-1][:160] if summary else out[-200:],
    }


def main() -> int:
    refuse = []
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        full = run_tests(build_tree(base, None))
        if full["rc"] != 0 or full["collected"] < 18:
            REFUSE_NOTE = f"判据3 完整树不绿或收集不足：{full}"
            refuse.append(REFUSE_NOTE)
        for who in REVERTS:
            res = run_tests(build_tree(base, who))
            red = [t for t in LOCKS[who] if t in res["failed"]]
            if not red:
                refuse.append(f"判据1 回退 {who} 后其锁没转红（锁不承重）：{res}")
            others = [
                t for k in LOCKS if k != who for t in LOCKS[k] + CONTROLS[k] if t in res["failed"]
            ]
            if others:
                refuse.append(f"判据2 回退 {who} 时别单的用例也红了（混因）：{others}")
            own_controls = [t for t in CONTROLS[who] if t in res["failed"]]
            if own_controls:
                refuse.append(f"判据4 回退 {who} 时本单对照也红了（对照不干净）：{own_controls}")
            missing = [
                t for t in LOCKS[who] + CONTROLS[who] if t not in res["failed"] + res["passed"]
            ]
            if missing:
                refuse.append(f"判据5 回退 {who} 的树上本单用例未被收集：{missing}")
            print(
                json.dumps(
                    {"who": who, "red_locks": red, "collected": res["collected"]},
                    ensure_ascii=False,
                )
            )
            (HERE / f"fix_r2_lockproof_revert_{who}.json").write_text(
                json.dumps(
                    {
                        "who": who,
                        "red_locks": red,
                        "mixed_cause": others,
                        "own_controls_red": own_controls,
                        "tree_result": res,
                    },
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
                newline="\n",
            )
    out = {"refuse": refuse, "full_tree": full}
    (HERE / "fix_r2_lockproof.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
