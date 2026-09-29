"""R1-验证 law4：CLI 与构建启动自检（四命令 + 导入身份探针）。

为什么要有这一条：模块「可导入」不等于「入口可用」，也不等于跑的是**这棵树**的代码——
既往实测过已安装孪生静默顶掉兄弟源码树。故除了跑 CLI，还要钉 `cypyc.__file__` 落在仓库内。
四条判据全部走子进程实测，不用 import 侧的假绿。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")

SRC = 'def main() -> int:\n    let a: int = 3\n    let b: float = a\n    print(f"v {b}")\n    return 0\n'


def run(cmd: list) -> tuple:
    p = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    refuse = []
    doc = {}
    tmp = Path(tempfile.mkdtemp(prefix="cypy_cli_r1_"))
    src = tmp / "cli_check.cypy"
    src.write_text(SRC, encoding="utf-8", newline="\n")

    rc, out = run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            "import cypyc, cypyc.cli, pathlib;" "print(pathlib.Path(cypyc.__file__).resolve())",
        ]
    )
    ident = out.strip().splitlines()[-1] if out.strip() else ""
    doc["identity"] = {"rc": rc, "cypyc_file": ident}
    if rc != 0:
        refuse.append(f"判据4.0 cypyc 导入失败：{ident or out[:200]}")
    elif not Path(ident).resolve().is_relative_to((ROOT / "cypyc").resolve()):
        # 上一版拿 `str(ROOT/'cypyc') not in ident.replace('\\','/')` 比——一边是反斜杠一边被换成
        # 正斜杠，永远不相等，把**本来正确**的身份判成越界（判据坏，不是产品坏）。
        refuse.append(
            f"判据4.0 导入的是**别的树**：{ident}（应落在 {(ROOT / 'cypyc').resolve()} 下）"
        )

    # 反例对照：同一判据必须能把「一定不该通过」的路径判出来，否则身份探针是恒绿的
    neg = Path(sys.executable).resolve()
    doc["identity_negative_control"] = {
        "probe_path": str(neg),
        "flagged": not neg.is_relative_to((ROOT / "cypyc").resolve()),
    }
    if neg.is_relative_to((ROOT / "cypyc").resolve()):
        refuse.append(
            "判据4.0 反例对照失效：解释器路径被判在本仓 cypyc 树内 ⇒ 这条判据咬不住任何东西"
        )

    for name, args in (
        ("help", ["--help"]),
        ("transpile", ["transpile", str(src), "-o", str(tmp / "t"), "--emit-cython"]),
        ("compile", ["compile", str(src), "-o", str(tmp / "c")]),
        ("run", ["run", str(src)]),
    ):
        rc, out = run([sys.executable, "-X", "utf8", "-m", "cypyc", *args])
        doc[name] = {"rc": rc, "tail": out.strip().splitlines()[-2:], "stdout": out[:4000]}
        if rc != 0:
            refuse.append(f"判据4 `cypyc {' '.join(args[:1])}` rc={rc}：{doc[name]['tail']}")
        if "Traceback" in out:
            refuse.append(f"判据4 `{name}` 输出里有 Traceback：{doc[name]['tail']}")

    if doc["run"]["rc"] == 0:
        # 真值判据：`let b: float = a` 必须浮点化（BUG-30 端到端口径），CLI 跑出来应是 `v 3.0`；
        # 只看末两行会被 CLI 自己的横幅挤掉，故在完整 stdout 里找。
        seen = doc["run"]["stdout"]
        if "v 3.0" not in seen:
            got = [l for l in seen.splitlines() if l.strip().startswith("v ")] or [
                "(没有 v 开头的输出行)"
            ]
            refuse.append(
                f"判据4 `cypyc run` 没打印 `v 3.0`（BUG-30 未打到 CLI 路径），实际看到：{got}"
            )

    art = sorted(p.name for p in (tmp / "t").glob("*")) if (tmp / "t").exists() else []
    doc["transpile_artifacts"] = art
    if not art:
        refuse.append("判据4 transpile --emit-cython 没产出文件")

    (HERE / "verify_cli_r1.json").write_text(
        json.dumps({"refuse": refuse, **doc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "identity": doc["identity"],
                "run": doc["run"],
                "help_rc": doc["help"]["rc"],
                "artifacts": art,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
