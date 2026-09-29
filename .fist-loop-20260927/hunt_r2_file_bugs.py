#!/usr/bin/env python3
"""R2-寻虫 入账：把三条确诊的静默缺陷写成 bug 单，并从 bug_list 回读自证。

入账口径（沿用 R1 的裁定）：
 - 只有"调用面 rc=0 且带成功横幅，但事实与声明相反"的静默型才占号；
 - 显式报错/未实现的功能缺失只转结，不占号；
 - 每条 detail 必带：可复跑命令、file:line 来历、成对对照（什么现象**不算**证明）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

D46 = """现象（一次跑完，全在调用面）：
  1) `python -m cypyc hook install`   → rc=0，打印 `[OK] Cypy import hook installed successfully`
  2) `python -m cypyc hook status`    → rc=0，打印 `[FAIL] Cypy import hook is not installed`
  3) 新进程 `python -c "import cypy_hook; cypy_hook.is_hook_installed()"` → AttributeError（见 BUG-47）
文档声明：docs/USAGE.md:121 `cypyc hook install  # 安装 import hook（写入用户 sitecustomize / 注册）`。

来历（file:line）：cypyc/cli.py:357-360 的 install 分支只是调用 `install_hook()` 后无条件打印 [OK]；
而 cypy_hook/hook.py:1136-1141 的 `install_hook()` 只把 finder 插进**当前进程**的 `sys.meta_path`，
既不写 sitecustomize 也不写任何注册文件。CLI 进程一退出，"安装"就消失了。
同一个原因让 status 永远为假：cypyc/cli.py:371-375 在自己的新进程里调 `is_hook_installed()`，
而它读的 `_cypy_finder` 是模块级全局（hook.py:1133），新进程里必然是 None ⇒ 状态栏恒 [FAIL]。

影响：按手册装完 hook 的用户，之后任何 `import xxx`（带 `#!bin cypy` 头的 .py / .cypy）都不会被接管，
而 install 的横幅与 rc=0 会让 CI 以为装上了；status 又永远报"未安装"，两个命令互相否定。

不算证明的现象（避免误判成已修）：只在同一条 python 会话里 `install_hook()` 后立刻
`is_hook_installed()==True` 是**设计如此**（in-process API），不能用来宣告这条已闭环；
必须让 install 与 status 各起一个新进程，且 install 之后新进程仍报已装（或 status 读的是持久化状态）。

修法（交修复轮，二选一即可但要说清选了哪个）：
 a) 真做持久化注册：按文档写用户 sitecustomize（或 .pth）并让 status 读该落盘状态；
 b) 收窄声明：install 改为"只输出可复制的注册片段"，status 改为报告"当前进程内是否已装"，
    并同步 docs/USAGE.md:121-124 的措辞。"""

D47 = """现象：`python -c "import cypy_hook; cypy_hook.install_hook()"` →
  AttributeError: module 'cypy_hook' has no attribute 'install_hook'
  （`is_hook_installed` / `uninstall_hook` 同样 AttributeError；`CypyHook` 可用。）

文档声明：docs/USAGE.md:134 —— "`cypy_hook`：核心集成包，暴露 `CypyHook`（编程接口）及
`install_hook` / `uninstall_hook` / `is_hook_installed` 等"。

来历：cypy_hook/__init__.py 只有一行 `from .hook import CypyHook` 与 `__all__ = ["CypyHook"]`；
三个函数确实存在，但只在 cypy_hook.hook（hook.py:1136/1144/1152）——包级再导出没做。

影响：手册给出的编程接口路径全部不可用，用户按文档写集成代码会在导入期就炸；
这也是 BUG-46 的排查里"第三个探针无输出"的直接原因（我的判据一开始把空 stdout 当成了
'没有安装'的证据，实际是子进程 AttributeError——见本轮报告 §判据自缺陷）。

不算证明：`from cypy_hook.hook import install_hook` 能用 ≠ 这条已修，文档承诺的是包级暴露。
修法：__init__.py 增补再导出并把 `__all__` 补齐（或改文档到 `cypy_hook.hook.*` 的真实路径）。"""

D48 = """现象：`python -m cypyc watch <dir> --debounce 0.2` 起得来（横幅打印Watching directory / Output
directory: output），随后：
  - 改动已在监控目录里的 a.cypy → 等 8s：目录里没有任何 .pyx/.pyd 产出，stdout 无变更事件；
  - 新增 b.cypy → 再等 8s：同样没有任何产物，也没有一行日志；
  两种触发形状都试过，全部 rc=0、进程活着、无报错。
文档声明：docs/USAGE.md:107 "### 2.5 `watch` —— 热重载开发服务器"；
SYNTAX/00-introduction.md:56 "热重载 - 不中断应用运行更新代码"。

来历（待修复轮确认，我只给到调用面事实与形状）：cypyc/cli.py:655-690 的 run_watch 构造
HotReloadEngine(hook) 后调用 `engine.start([args.source])`，**没有传 on_reload 回调**
（hot_reload.py:540 的签名是 `start(self, watch_dirs, on_reload: Optional[...] = None)`）。
即"检测到变更 → 由谁去重编译"这一段在 CLI 路径上是空的；库路径大概有回调，但 CLI 没用。

影响：`cypyc watch` 是一个只会打印横幅的常驻进程；按手册用它做开发循环的人得不到任何重编译，
且因为不报错，很容易把"没触发"当成"我的文件没被 recognized"。

不算证明：只测"新增文件"这一种触发形状不足以确认（我已同时测了 modify 与 add）；
修复后必须在**新进程**里看到 output/ 下出现对应 .pyx，并且 stdout 有事件行。"""

ITEMS = [
    (
        "hook install 打印 [OK] 但不做任何持久化，紧接着 status 在另一进程里报未安装（两命令互相否定）",
        D46,
        "high",
    ),
    (
        "docs 声明的 cypy_hook 包级 API（install_hook/uninstall_hook/is_hook_installed）"
        "未再导出，导入即 AttributeError",
        D47,
        "medium",
    ),
    (
        "cypyc watch 只打印横幅：改动或新增被监控文件后 16s 内无任何重编译产物与事件日志，rc 始终 0",
        D48,
        "high",
    ),
]


def main() -> int:
    c = lfist_lib.Client(timeout=180)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    c._recv(1, 60)
    filed = []
    for title, detail, sev in ITEMS:
        r = c.call(
            "report_bug",
            {
                "summary": title,
                "detail": detail,
                "severity": sev,
                "project_dir": ".",
                "reported_by": "cypy-hunter",
                "now": lfist_lib.utc_now(),
            },
        )
        filed.append({"summary": title[:50], "severity": sev, "resp": r})
        print(
            json.dumps(
                {"bug_id": r.get("bug_id"), "task": r.get("task_id"), "title": title[:56]},
                ensure_ascii=False,
            )
        )
    bl = c.call("bug_list", {"project_dir": ".", "limit": 80, "now": lfist_lib.utc_now()})
    rows = bl.get("bugs") or bl.get("items") or bl
    tail = []
    if isinstance(rows, list):
        for b in rows:
            tail.append(
                {
                    "id": b.get("id"),
                    "status": b.get("status"),
                    "summary": (b.get("summary") or b.get("title") or "")[:70],
                }
            )
    doc = {"filed": filed, "bug_list_tail": tail[-8:], "bug_total_in_list": len(tail)}
    (HERE / "hunt_r2_file_bugs.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1)[:900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
