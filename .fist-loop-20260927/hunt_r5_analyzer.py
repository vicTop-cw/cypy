"""R5-寻虫 的批量分析入口：一次子进程吃一批源，逐档回观察，并钉死「跑的是哪棵树」。

只在上一环那份 cards 里留下与「怎么测」相关的部分——候选表本身是 R4 形状的（arity 那批缺陷
R4-修复已经改掉），继续带着它们会让观察永远对不上，所以这张表连同它的对照集一起移出了本轮。

口径：
- `run_batch` 必须在返回前证明子进程导入的是被测树的 type_checker，否则「跑了」与「跑对了地方」
  是两件事（孪生安装件静默顶掉兄弟源码树这一坑上一轮踩过）；
- 行数不齐 ⇒ 直接抛，不静默截断成「后面几条没观察」；
- `observed_kind` 只把错误归成形状，不做结论；结论由各电池自己配对照来下。
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
IMPORTABLE = ("cypyc", "cypy_hook", "cypy_bridge")

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
    p = subprocess.run(
        [PY, "-X", "utf8", "-c", RUNNER, target],
        cwd=target,
        input=json.dumps(sources, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if p.returncode != 0:
        raise RuntimeError(f"批量分析器 rc={p.returncode}: {(p.stdout + p.stderr)[-400:]}")
    got = json.loads(p.stdout.strip().splitlines()[-1])
    want = (
        str(Path(target) / "cypyc" / "analyzer" / "type_checker.py").replace("\\", "/").lower()
    )
    got_norm = Path(got["ident"]).as_posix().replace("\\", "/").lower()
    if got_norm != want:
        raise RuntimeError(f"跑的不是目标树：期望 {want} 实得 {got_norm}")
    if len(got["rows"]) != len(sources):
        raise RuntimeError(f"回的行数 {len(got['rows'])} ≠ 送出的源 {len(sources)}")
    return {"ident": got_norm, "rows": got["rows"]}


def observed_kind(errs: list) -> dict:
    """把一次观察归成可对照的形状：报了什么类别、有没有内部 repr 外泄。"""
    return {
        "errors": errs,
        "arity": any(ARITY in e for e in errs),
        "mismatch": any(MISMATCH in e for e in errs),
        "any_type_error": any(MISMATCH in e or ARITY in e for e in errs),
        "leaks_internal_repr": any("tuple[" in e or "generic_params" in e for e in errs),
    }


def satisfies(obs: dict, spec: str) -> bool:
    """`spec` 是这一档「应当观察到什么」；满足=今天行为正确。"""
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
    batch = run_batch([DECL + "def f(cb: Callback) -> str:\n    return cb(1, 2)\n"])
    print(
        json.dumps(
            {
                "ident": batch["ident"],
                "importable_declared": list(IMPORTABLE),
                "probe_observed": observed_kind(batch["rows"][0]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
