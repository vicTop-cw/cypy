"""`python -m cypyc` 入口。

必须把 cli.main() 的返回码传播成进程退出码：此前这里是裸 `main()`，
丢弃返回值 -> 即便 `run` 子命令打印了 `[FAIL] Execution failed:`（run_run 返回 1），
`python -m cypyc` 仍然 exit 0。外部判据 scripts/e2e_golden.sh 的 RUNFAIL 分支
只看进程退出码，于是「编译/运行失败但正常返回」全部藏在绿灯里（LINK-1）。
"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
