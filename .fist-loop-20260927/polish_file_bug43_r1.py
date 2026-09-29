"""入账 BUG-43：项目声明的 mypy strict 门在测试树上**根本跑不起来**（python_version=3.9 与依赖冲突）。

判据形状：不是"我看到代码形状觉得会坏"，而是当场跑到调用面并把服务端原文贴回来。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

CMD = [
    sys.executable,
    "-X",
    "utf8",
    "-m",
    "mypy",
    "tests/test_loop_20260927_fix.py",
    "cypyc/codegen/cython_generator.py",
    "cypyc/parser/lexer.py",
    "cypy_bridge/types.py",
    "cypy_bridge/__init__.py",
]
r = subprocess.run(
    CMD, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace"
)
raw = (r.stdout or "") + (r.stderr or "")
tail = raw.strip().splitlines()[-3:]
aborted = "errors prevented further checking" in raw
if not aborted:
    print(
        "REFUSE — 复现不成立（mypy 没中断），这条主张不能入账。原文：",
        json.dumps(tail, ensure_ascii=False),
    )
    raise SystemExit(1)

DETAIL = f"""现象：pyproject 的 `[tool.mypy]` 声明 `python_version = \"3.9\"` + `strict = true`，
但本机依赖（pytest）自身带 3.10 的 `match` 语法 ⇒ mypy 一旦跟随导入进到 site-packages 就**整轮中断**，
连项目自己的文件都不再检查。这不是"存量 error 多"，而是**这道门当前跑不起来**。

调用面原文（{__file__.split(chr(92))[-1]} 当场实跑，命令与退出码一起给出）：
  $ {' '.join(CMD[:5])} tests/test_loop_20260927_fix.py cypyc/codegen/cython_generator.py \\
      cypyc/parser/lexer.py cypy_bridge/types.py cypy_bridge/__init__.py
  rc={r.returncode}
  {chr(10).join('  ' + l for l in tail)}

对照：去掉那个 import pytest 的测试文件后（`mypy cypyc/parser/lexer.py cypy_bridge/types.py`），
mypy 不中断而是报出成片的存量 error（R1-验证 记的是 950 条/37 文件）⇒
同一个配置在"产品码输入"与"含测试输入"两种口径下给出完全不同形状的结果，
说明 `python_version=3.9` 这条声明与实际运行环境（CPython {sys.version.split()[0]}）已经不一致。

影响：PROJECT-SPEC 的静态检查口径无法在测试树上执行；CI 若照声明跑 `mypy`，
会在中断的情况下只拿 1 条 error 当作「基本干净」（本轮扫描器就差点这么写——它输出了
`total_errors=1`，而真相是"检查被中止"）。任何以这个数字立论的门禁都建在沙上。

修法（交裁决，本环不动配置）：a) `[[tool.mypy.overrides]]` 对第三方模块
（`pytest.*` 等）设 `ignore_missing_imports=true` / `follow_imports=\"silent\"`；
b) 把 `python_version` 抬到实际支持的最低版本（若项目确实要支持 3.9，则该声明与 pytest 版本
需要一起裁决）；c) 让包装脚本把「中断」与「N 条 error」区分开（`errors prevented further checking`
必须判为未跑成，而不是计数 1）。"""

c = lfist_lib.Client(timeout=240)
c._send(
    "initialize",
    {
        "protocolVersion": lfist_lib.PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": lfist_lib.CLIENT_INFO,
    },
)
resp = c.call(
    "report_bug",
    {
        "project_dir": ".",
        "summary": "[静态检查配置] mypy 按声明的 python_version=3.9 跑测试树会整轮中断"
        "（依赖里有 3.10 语法），strict 门形同不存在",
        "detail": DETAIL,
        "severity": "medium",
        "publish_task": True,
        "now": lfist_lib.utc_now(),
    },
)
print("report_bug:", json.dumps(resp, ensure_ascii=False)[:300])
bl = c.call("bug_list", {"project_dir": "."})
ids = [b.get("id") for b in (bl.get("bugs") or [])]
print("count:", len(ids), "tail:", ids[-3:])
c.close()
raise SystemExit(0 if resp.get("bug_id") else 1)
