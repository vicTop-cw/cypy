# Cypy · FIST 收敛记忆（target）

## T0r61 审计修复轮（2026-09-25，namespace cron-cypy，16/16 任务已完成）

判据（非 LLM 外部锚点，服务端 run_check 真实 spawn 并落库）：
- `bash scripts/e2e_golden.sh` → PASS=22 FAIL=0 UNREG/RUNFAIL=0 WARN=1，exit 0
- `python Find_BUG/audit_2026q3/repro_gate.py <前缀> fixed` → 31 个自门控复现脚本全部 exit=0（5 簇 4/6/9/8/4）
- `bash scripts/run_tests.sh` → Total 47 / Passed 47 / Failed 0
- `python -m pytest -q tests test_suite` → 基线 1466 → 1681 passed / 0 failed

五簇结论：
1. 增量编译链（dependency_graph / ast_differ）：节点标识符归一化 + blake2b 递归结构摘要，位置信息不再污染 diff；摘要禁用 builtin `hash()`（PYTHONHASHSEED 逐进程随机）。
2. 前端（preprocessor / macro_expander / indent_detector / type_checker）：include 路径用 realpath+normcase 做包含校验并抛 IncludeError 族；宏替换改 token 级，字面量序列化后再插值；`Type.__eq__` 纳入 `union_members` 且显式 `__hash__ = None`。
3. 运行时桥接（cypy_bridge/*）：指针/defer/nogil/memory/union/meta 语义与所有权对齐。
4. 代码生成与产物（cypy_hook/hook.py、cypyc/cli.py、project_compiler.py）：产物后缀由 `sysconfig EXT_SUFFIX` 推导（不再硬编码 `-win_amd64.pyd`）；构建超时 60→180s；`run_run` 判据改为 `success and not errors`；缺入口函数抛 `FunctionNotFoundError`（模块级程序不再被误判为失败）。
5. 测试基建（test_suite/*、sync_demo.py）：`Suite.current_test`、`skipped` 计数改名落地，`Check.has_failures()` 真正计数；9 个 orphan demo 清理、5 个先前无法同步的 legacy demo 补齐。

可复用资产：`Find_BUG/audit_2026q3/`（29 个自门控复现脚本 + 三模式门禁 `repro_gate.py`：scripts / reproduce / fixed）与 `scripts/fist.py`（FIST-Mbt stdio 驱动：自动注入 namespace/project_dir、spawn 前自动补 ESM shim、服务端死亡时回吐 stderr）。
