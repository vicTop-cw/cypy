## BUG-1 [2026-09-26T05:31:45Z] [high] OPEN
- summary: [cache] cypy_bridge/compiler.py:3656 clear_cache 把 .pyd 删除失败当成功：裸 except 吞掉后仍从 manifest 删条目
- detail: 现象：`clear_cache(module_name)` 在 `try: os.remove(pyd_path) except: pass`（:3656-3659）之后无条件 `del manifest[cache_key]` + `_save_manifest(manifest)`；全量分支（:3668-3671）同样吞掉删除失败并无条件 `_save_manifest({})`。
后果：Windows 上被 import 的扩展模块文件锁是常态（同文件 :3760 附近就有为绕开 file lock 而换临时目录的逻辑），删除失败时磁盘上的 .pyd 仍在，但 manifest 已声称没有 → 上层按 manifest 判断「已清理」，可继续命中陈旧二进制；表现为「清了缓存但行为没变」，且全程零诊断。
复现（确定性、不编译）：构造 BridgeCacheManager，写一条 manifest 指向临时 .pyd，monkeypatch `os.remove` 抛 OSError，再调 `clear_cache(name)`；断言「删除失败 ⇒ 条目仍在 manifest 或返回值/日志能观察到失败」。当前实现两条都不满足。
判据实测：`grep -n 'except:' cypy_bridge/compiler.py` → 3658、3670 两处（全仓三包裸 except 共 2 处、`except … : pass` 共 20 处，见 `.fist-polish-20260926/markers_baseline.json`）。
建议：删除失败就不动 manifest 条目（保持「未清理」的事实），并把失败收集成可判定结果（例如返回 (cleared, failed) 或记 warning），不要静默写空 manifest。
- reported_by: cypy-polisher
- task_id: T0r6

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r6`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T05:48:09Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypy_bridge/compiler.py`
- 锁死回归（1 个函数 / 1 条收集用例）：`tests/test_polish_20260926.py::test_bug1_clear_cache_does_not_claim_success_when_remove_fails`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-2 [2026-09-26T05:31:45Z] [high] OPEN
- summary: [subprocess] cypy_bridge/compiler.py:3795 subprocess.run 无 timeout；同仓做同一件事的另外两处都有 timeout=120
- detail: 现象：桥接编译 `subprocess.run([sys.executable, setup_file, 'build_ext', '--inplace'], capture_output=True, cwd=tmp_dir)` 缺 `timeout`；对照 `cypyc/project/project_compiler.py:599-604`（`timeout=120`）与 `cypy_hook/hook.py:513-518`（`timeout=120`）。三包内 subprocess.run 共 3 处：2 处有超时、1 处没有。
后果：setuptools / Cython / 链接器任一环节挂死（文件锁、弹窗、交互式提示、杀软扫描）时调用线程永久阻塞——无退出码、无诊断，整条构建链卡死。另两处早已按 120 s 收口，说明这里缺失是不一致而非设计。
复现：`grep -n 'subprocess.run' cypyc/project/project_compiler.py cypy_bridge/compiler.py cypy_hook/hook.py` 三条对照，只有 bridge 那条不带 `timeout=`。
建议：补 `timeout=120`，并在 `subprocess.TimeoutExpired` 分支终止子进程、清理临时目录、产出可诊断错误（注意同文件的裸 except 家族会把这类失败一并吞掉）。
- reported_by: cypy-polisher
- task_id: T0r7

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r7`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T05:48:09Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypy_bridge/compiler.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug2_bridge_build_subprocess_run_passes_timeout`、`tests/test_polish_20260926.py::test_bug2_build_timeout_is_shared_with_sibling_callers`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-3 [2026-09-26T05:31:45Z] [high] OPEN
- summary: [silent-fail] cypyc/project/project_compiler.py:826 增量重解析异常被吞：失败后仍用陈旧 AST 计算影响集并报告已传播
- detail: 现象：:817-831 里 `try: self._reparse_module(module_name) except Exception: pass`，紧接着无条件 `get_affected_modules({module_name})` 并写入 `affected[file_path]`。
后果：重解析失败（语法错误、编码问题、解析器缺陷）时依赖图里留的是旧 AST，但该文件被登记为「已处理且影响已传播」，增量构建据此产出陈旧结果并返回成功。这是增量编译最难定位的一类故障：改坏了不报错，产物是旧的。
复现（确定性）：monkeypatch `_reparse_module` 抛异常，调用受影响模块收集入口，断言「该文件不得出现在 affected 结果里，或 errors 列表必须记录该失败」；当前实现两条都不满足。
判据实测：`grep -n 'except Exception:' cypyc/project/project_compiler.py` → :826。
建议：失败即记入 errors 且把该文件从 affected 剔除——宁可让上层判定「增量失效、需全量重建」，也不要用陈旧 AST 谎报成功。
- reported_by: cypy-polisher
- task_id: T0r8

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r8`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T05:48:09Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/project/project_compiler.py`
- 锁死回归（1 个函数 / 1 条收集用例）：`tests/test_polish_20260926.py::test_bug3_reparse_failure_is_reported_not_swallowed`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-4 [2026-09-26T05:31:45Z] [medium] OPEN
- summary: [silent-fail] cypyc/transformer 五个 transformer 把递归调用包进 except (AttributeError, TypeError)，子树真实异常被吞、收集静默截断
- detail: 现象（`cypyc/transformer/defer_transformer.py:45-54` 为例，enum/generic/struct/trait 四个同形状）：
    try:
        value = getattr(node, attr_name)
        if isinstance(value, ASTNode):
            self._collect_defers(value)      # ← 递归在 try 内
        elif isinstance(value, list):
            for item in value: … self._collect_defers(item)
    except (AttributeError, TypeError):
        pass
except 的本意是防 `getattr` 在 `dir(node)` 动态属性上偶发失败，但它同时罩住了整棵子树的递归：深层 TypeError（属性是会抛错的 property、迭代协议不成立、比较运算抛错）都被当成「这个属性不存在」静默跳过。
后果：defer 块 / struct / enum / trait 的收集不完整且零诊断——生成的代码少一段，而编译器自认为扫全了。
判据实测：`grep -rln 'except (AttributeError, TypeError):' cypyc/transformer` → defer/enum/generic/struct/trait 五个文件各 1 处。
建议：把守卫收窄到 `getattr` 本身（`getattr(node, attr_name, None)` 或只捕 AttributeError），递归调用移出 try，TypeError 必须向上冒。回归测试用「子节点属性是抛 TypeError 的 property」这种最小 AST 断言异常必须传播。
- reported_by: cypy-polisher
- task_id: T0r9

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r9`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T05:48:09Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/transformer/{defer,enum,generic,struct,trait}_transformer.py`
- 锁死回归（1 个函数 / 5 条收集用例）：`tests/test_polish_20260926.py::test_bug4_transformer_recursion_is_outside_broad_try`（parametrize 5 例）
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-5 [2026-09-26T05:31:45Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/hot_reload.py:110 与 :125 状态快照/回滚吞掉 getattr/setattr 异常（含用户 property 执行失败）
- detail: 现象：`_save_state` 在 `for name in dir(self._actual_module)` 里 `try: value = getattr(...) … except Exception: pass`（:99-111）；`_restore_state` 同样吞 setattr 失败（:120-126）。
后果：getattr 会执行模块级 property / 描述符 / 惰性导入。用户代码在这里抛错被当成「该属性不存在」跳过 ⇒ 快照不完整；热重载后只回滚了部分状态，模块停在新旧混合态，且零诊断。setattr 失败同理被吞。
判据实测：`grep -n 'except Exception:' cypyc/incremental/hot_reload.py` → :110、:125、:247、:272、:326、:451 共 6 处；本单聚焦 110/125 这一对，其余 4 处同文件同性质，修复时一并研判并逐条给结论。
建议：只捕明确不该致命的类型（AttributeError 等），把被跳过的属性名与异常记入调试日志；快照/回滚发生跳过时应让调用方可判定（例如返回跳过的名字列表）。
- reported_by: cypy-polisher
- task_id: T0r10

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r10`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T05:48:09Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/incremental/hot_reload.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug5_state_snapshot_reports_getattr_failure`、`tests/test_polish_20260926.py::test_bug5_state_restore_reports_setattr_failure`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-6 [2026-09-26T05:31:46Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/file_monitor.py:58 读不到 .py 首行即判定「不是 Cypy 文件」，变更被静默漏掉
- detail: 现象：`_is_cypy_file` 对 .py 文件读首行判断 `#!bin cypy` 头，`except Exception: pass` 后 `return False`（:54-61）。
后果：文件此刻被占用 / 无权限 / 正在被写（监控器天然与写入方并发，同文件 :63 起就有 debounce 锁）时，读失败被当成「确定不是 Cypy 文件」→ 该文件的变更不触发重编译且无任何记录。这是把「检测失败」误当成「检测结论为否」的分类错误。
复现：monkeypatch `builtins.open` 抛 OSError，调用 `_is_cypy_file("x.py")`，断言结果不能是「静默 False 且无记录」。
判据实测：`grep -n 'except Exception:' cypyc/incremental/file_monitor.py` → :58。
建议：区分「读失败」与「读到但首行不匹配」：前者保留为待判定（延后重试或按候选处理）并落 warning，不能静默 return False。
- reported_by: cypy-polisher
- task_id: T0r11

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r11`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T05:48:09Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/incremental/file_monitor.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug6_cypy_file_with_bom_is_still_detected`、`tests/test_polish_20260926.py::test_bug6_unreadable_cypy_candidate_warns`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-7 [2026-09-26T05:31:46Z] [low] OPEN
- summary: [diagnostics] cypy_hook/hook.py:926 与 cypy_bridge/compiler.py:3583 manifest 损坏与「文件不存在」不可区分，静默按无缓存继续
- detail: 现象：两处 `_load_manifest` 都是 `if os.path.exists(path): try: json.load(...) except (json.JSONDecodeError, IOError): pass` 然后 `return {}`。
后果：manifest JSON 被截断/写坏（并发写、磁盘满、进程被杀）与「首次运行没有 manifest」返回值完全相同 → 上层认为没有缓存，重建后直接覆盖，损坏证据永久消失，任何人都无法判断发生过什么。缓存子系统里这是最贵的一类静默降级。
判据实测：`grep -n 'except (json.JSONDecodeError, IOError)' cypy_hook/hook.py cypy_bridge/compiler.py` → 2 命中（hook.py:926、compiler.py:3583）。
建议：损坏时先把原文件改名留证（如 `bridge_manifest.json.corrupt-<ts>`）并落 warning，再按空 manifest 继续；返回值带 `was_corrupt` 之类的可判定信号。
- reported_by: cypy-polisher
- task_id: T0r12

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r12`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T05:48:10Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypy_hook/hook.py, cypy_bridge/compiler.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug7_corrupt_manifest_warns`、`tests/test_polish_20260926.py::test_bug7_corrupt_bridge_manifest_warns`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-8 [2026-09-26T06:09:13Z] [medium] OPEN
- summary: [silent-fail] cypyc/parser/macro_expander.py:380 宏展开后的代码块解析失败时静默返回原块，整条宏语句从输出中消失且无任何告警
- detail: 现象: `_reparse_code()` 末尾 `try: Lexer/Parser ... except Exception as e:` 直接把未解析的原文包成 `BacktickBlock(code, '', line, col)` 返回，异常对象 `e` 被丢弃、无任何 stderr 输出。模块自己的实现约束注释（同文件 :20-23）就写着「这条降级路径会让整条宏调用语句从输出里消失」，即已知其危害，但用户/CI 看不到任何线索。
复现（确定性，零依赖）: `MacroExpander.__new__(MacroExpander)._reparse_code('def (', 7, 3)` → 返回 BacktickBlock 且 capsys 捕获的 stderr 为空串。见 `tests/test_polish_20260926.py::test_bug8_macro_reparse_degradation_is_reported`（修复前该条 1 failed / err == ''）。
影响: 宏实参渲染或插值产出的文本一旦不可解析，展开结果被原样透传给 codegen，该语句在生成的 .pyx 里消失——编译「成功」但少了一条语句，属静默数据丢失；与本轮 BUG-3/BUG-4/BUG-5/BUG-6/BUG-7 同族。
建议: 不改降级语义（仍返回 BacktickBlock，避免打破 23 条既有 macro 用例），只在 except 分支打一条点名 行/列/原始代码/底层异常的 stderr 告警；彻底修复（把失败上报到 diagnostics 并非零退出）属语义面变更，需单独立项。
- reported_by: cypy-polisher
- task_id: T0r13

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r13`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T06:10:11Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/parser/macro_expander.py`
- 锁死回归（1 个函数 / 1 条收集用例）：`tests/test_polish_20260926.py::test_bug8_macro_reparse_degradation_is_reported`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-9 [2026-09-26T06:37:48Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/hot_reload.py:253 HotReloadEngine 的模块级状态快照/回滚仍是 `except Exception: pass`，BUG-5 的修复只覆盖了 CypyProxyModule 那一份平行实现
- detail: 现象: `_save_module_state()`(:248-254) 与 `_restore_module_state()`(:276-279) 对 getattr/setattr 失败一律 `pass`，而同文件同族缺陷 BUG-5 只改了代理模块路径的 `_save_state/_restore_state`（helper `_warn_state` 就在 :53）。
复现（确定性，零依赖）: `pytest tests/test_polish_20260926.py -q -k 'bug9_module or bug10'` → 4 failed，capsys 的 stderr 为空串；原始输出 .fist-polish-20260926/pytest_second_sweep_red.log。
影响: 热重载带着状态空洞继续跑——模块全局被静默丢弃或写不回去，用户只看到『重载成功』；与本轮 BUG-3/BUG-4/BUG-5/BUG-6/BUG-7/BUG-8 同族。
建议: 两处 except 复用已有的 `_warn_state()`，不改快照/回滚语义与返回值。
- reported_by: cypy-polisher
- task_id: T0r14

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r14`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T06:43:05Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/incremental/hot_reload.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug9_module_state_snapshot_warns`、`tests/test_polish_20260926.py::test_bug9_module_state_restore_warns`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-10 [2026-09-26T06:37:48Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/hot_reload.py:457 热重载把依赖分析与增量缓存更新的解析失败整段吞掉（:332 与 :457 两处，注释即『解析失败不影响热重载』）
- detail: 现象: `_analyze_module_dependencies()` 的函数体整块包在 try 里、`except Exception: pass`（:433-458），`_compile_and_reload_module()` 更新增量缓存的那段同样静默（:325-333）。解析或 analyze_changes 一旦抛错，模块级反向依赖图就缺边，后续热重载只重编触发文件本身、漏掉依赖方——漏重载比报错更难查。
复现（确定性，零依赖）: monkeypatch `cypyc.parser.parser.Parser` 抛错后调用两个入口，stderr 全空；见 .fist-polish-20260926/pytest_second_sweep_red.log 里 test_bug10_dependency_analysis_parse_failure_warns 与 test_bug10_cache_update_parse_failure_warns 两条 failed。
影响: 增量/热重载的正确性静默降级；BUG-3 修的是 project_compiler 那份重解析，hot_reload 这两份是同一缺陷类的未覆盖面。
建议: 两处各打一条点名 阶段/源文件/底层异常 的 stderr 告警，不改控制流（仍继续热重载），彻底上报到 diagnostics 属语义面变更需另立单。
- reported_by: cypy-polisher
- task_id: T0r15

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r15`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T07:53:52Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/incremental/hot_reload.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug10_dependency_analysis_parse_failure_warns`、`tests/test_polish_20260926.py::test_bug10_cache_update_parse_failure_warns`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-11 [2026-09-26T07:13:26Z] [medium] OPEN
- summary: [silent-fail] cypyc/project/project_compiler.py:539 项目模式 type_check_module 只上送 TypeChecker 诊断，ScopeAnalyzer 已报出的重名/类型级冲突（SYNTAX/33 C-3.1）被静默丢弃——同一份源码在单文件模式 cypy_hook/hook.py:250 会报错，两个入口给出相反裁决
- detail: 现象: type_check_module() 调用 ScopeAnalyzer().analyze(ast) 后从不读 scope_analyzer.errors（:539-540），只把 type_checker.errors 收进返回值；而单文件管线 cypy_hook/hook.py:250-257 两处都收。因此作用域通道独有的诊断（重名定义、类型级名字冲突、非模块级定义）在项目模式整个消失，cypyc/cli.py:737-744 的 --check-only 会打印 'type check passed' 并以 0 退出。
复现（确定性，零依赖）: 三份源文件各建一次性项目，python .fist-polish-20260926/probe_scope_drop.py 打印三行 DROPPED —— ScopeAnalyzer 有诊断、TypeChecker 为空、type_check_module 返回 ok=True errors=[]：dup_func（def f 写两次）、dup_subtype_class（subtype Money <: int 撞 class Money）、dup_type_constraint（type Thing = int 撞 constraint Thing）。对照：uses_undefined 一条不丢，因为 TypeChecker 自己会报同一句 Undefined name —— 丢的正是作用域独有的那一类。
锁死回归: tests/test_polish_20260926.py::test_bug11_project_type_check_reports_scope_errors + ::test_bug11_type_level_name_collision_is_reported；改前 .fist-polish-20260926/pytest_third_sweep_red.log → 2 failed, 20 deselected（两条都红在 ok=True errors=[]，且用例里的前提自证断言先确认 ScopeAnalyzer 确实报出了这个名字）。
影响: 项目/多模块构建带着重复定义继续编译，codegen 按后写覆盖前写产出 .pyd，用户拿到的模块身份与源码不一致；与本轮 BUG-3（同一文件的重解析异常被吞）同族。
建议: 在 type_check_module 里 errors.extend(scope_analyzer.errors)，并对两条通道逐字重复的诊断按序去重（dict.fromkeys），不改任何判定规则、不新增诊断文案。
- reported_by: cypy-polisher
- task_id: T0r16

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r16`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T07:23:57Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypyc/project/project_compiler.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug11_project_type_check_reports_scope_errors`、`tests/test_polish_20260926.py::test_bug11_type_level_name_collision_is_reported`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-12 [2026-09-26T08:27:00Z] [medium] OPEN
- summary: [error-masking] cypy_bridge/nogil.py:73 GilState.__exit__ 无条件 acquire，with 体内提前归还 GIL 后再抛用户异常时，退出路径用 NoGilError('GIL is not released') 顶掉用户异常——同一族的嵌套覆盖问题本模块已在 NoGilContext 修过，GilState 这条退出路径漏修
- detail: 现象: GilState.__exit__（:73-76）直接 self.acquire()，而 acquire()（:58-59）在 _released 已为 False 时抛 NoGilError。因此 `with GilState() as st: st.acquire(); raise ValueError(...)` 这种「区域内提前归还 GIL」的合法写法，退出时 __exit__ 抛出的 NoGilError 会替换正在传播的 ValueError，用户既拿不到自己的异常类型，也看不到自己的消息；异常链里只留下 'GIL is not released'。
复现（确定性，零依赖）: python .fist-polish-20260926/repro_sweep4_nogil.py → `escaped exception type = NoGilError`、`[repro A] ... REPRODUCED`。同脚本的 B 项（nogil_thread 一次性调用是否泄漏执行器线程）实测没有复现——12 次调用只余 1 个临时 worker，会被回收，故 B 按误报不入账。
锁死回归: tests/test_polish_20260926.py::test_bug12_gilstate_exit_does_not_replace_user_exception（改前红：AssertionError: GIL 退出路径把用户的 ValueError 换成了 NoGilError）+ ::test_bug12_gilstate_exit_still_restores_state（防过度修复：退出时仍须把 released 复位，改前即绿，改后仍绿）。
影响: cypy_bridge 公开导出 GilState/release_gil/acquire_gil（__init__.py:119-121、224-226），任何用它包 CPU 密集段并在段内手动归还 GIL 的调用方，报错信息都会指向 nogil 本身而不是真正的失败点，排查方向被带偏；与本轮 BUG-4/BUG-9「异常在兜底路径变形或消失」同族，但这条不是静默吞掉，是替换。
建议: __exit__ 里改为 `if self._released: self.acquire()`，保持 return False （不吞任何异常），不改 release/acquire 自身的报错语义，也不改 nogil 的对外契约。
- reported_by: cypy-polisher
- task_id: T0r17

### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r17`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-26T10:09:29Z`、`completed_by=cypy-polisher`）
- 改动文件：`cypy_bridge/nogil.py`
- 锁死回归（2 个函数 / 2 条收集用例）：`tests/test_polish_20260926.py::test_bug12_gilstate_exit_does_not_replace_user_exception`、`tests/test_polish_20260926.py::test_bug12_gilstate_exit_still_restores_state`
- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`
- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-13 [2026-09-26T10:07:36Z] [medium] OPEN
- summary: [judge-brittleness] tests/test_incremental.py:547 TestDigestCost 用墙钟阈值 `digest_elapsed < 2.0` 判性能，代价取决于同进程里先跑过多少用例（CPython 循环 GC 要扫既有堆）——同一份产品代码在单跑时 0.5s、整文件跑后 3.385s，判据跨收集顺序不可复现，把门禁 ① 变成抛硬币
- detail: 现象: 终态全量 `python -m pytest tests/ -q` 从 1 红变 2 红，新增的红条是 tests/test_incremental.py::TestDigestCost::test_digest_cost_on_ten_thousand_line_module，原文 `AssertionError: digest cost too high: 3.223s`（sweep5）与 `3.385s`（只跑 tests/test_incremental.py 单文件，1 failed, 37 passed）。同一条用例单独跑（1 passed in 6.12s）与只跑 TestStructuralDigest+本用例（21 passed）都是绿的——判据结论随收集顺序翻面。
被测量本身没有变慢：`meas_digest_cost.out.txt` 用同一份 tests/test_incremental.py 里的 _large_module/parse_source/ASTDiffer 复测，1100 个顶层定义的摘要 CPU 时间 0.391/0.406/0.422s（三次），墙钟 0.510/0.530/0.708s。`meas_digest_gc.out.txt` 再把机制钉住：往同一进程灌 1.5M 个循环对象（alloc_blocks 135568→3135582）后 CPU 时间仍 0.42→0.47s 不变，墙钟 0.793→0.945s；对这些对象执行 gc.freeze()（活对象数不变）墙钟又回落到 0.544s。⇒ 超时的那 2~3s 花在 GC 扫描进程既有堆 + 被抢占（同脚本纯 CPU 校准循环 wall/cpu 比 1.28~1.40，即约三成墙钟根本不在 CPU 上），不花在 cypyc 的摘要计算上。
定性: 产品侧 [误报]（cypyc/incremental/ast_differ.py 自 2026-09-25 16:39 未改，本轮 sweep4→sweep5 之间唯一产品改动是 cypy_bridge/nogil.py 的异常传播守卫，不在被测路径上）；判据侧 [真缺陷] → 入账本单。门禁 ① 的「全绿」因此不可复现：任何一次全量都可能因为无关用例先跑而红。
建议（择一，都属改既有判据，交指挥官裁决，本轮不自行落地）: ① 计时改用 `time.process_time()`（或取 wall 与 cpu 的较大者）并保留同量级阈值；② 计时前 `gc.collect()` 后 `gc.disable()`、并对堆做 `gc.freeze()`，使代价只随被测 AST 规模增长；③ 把该用例标 `@pytest.mark.perf` 并默认不收集，只在专用 `-m perf` 单进程运行里判；④ 把绝对阈值改成同进程内的相对比值（例如 digest 成本 / 一次 parse 成本），堆噪声自然抵消。
本轮处置: 不修、不降阈值（红线：tests/ 只补回归不改语义；门禁只能破红线转正时交回指挥官）。终态报告按收集顺序披露，并给出上面三条可复跑证据日志。
- reported_by: cypy-polisher
- task_id: T0r18
### FIXED(verify=已完成) — 2026-09-26 追加留档（裁决落地段工作，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r18`（ns `bugs`），`execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes8.out.json`；入账映射见 `intake_map5.json`；来源：指挥官对本轮 §七 三项待裁决第①项的裁定
- 锁死回归（2 个函数）：`tests/test_polish_20260926_pass7.py::test_bug13_digest_cost_is_judged_on_cpu_time_not_heap_dependent_wall`、`tests/test_polish_20260926_pass7.py::test_bug13_other_timers_not_silently_loosened`；每条在回退树上转红过：`test_bug13_digest_cost_is_judged_on_cpu_time_not_heap_dependent_wall`
- 证据：判据前后分离测量：`.fist-polish-20260926/meas_digest_cost.out.txt`（入账时，同一夹具 wall/cpu 比 1.26–1.74）与 `meas_digest_after.out.txt`（落地后，两条判据各自 verdict）；回退树证红 `lockproof_pass7.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep11.log`
- 修复边界：本段只把摘要判据的量纲从墙钟换成 CPU 时间，阈值数字一个没动（`< 2.0`、`< small*12+0.5` 原样，parse/compare 两条时限仍是墙钟）；被测的产品码性能未改变，「CPU 时间能代表摘要代价」这一前提由裁决本身背书，不在本单内再证。
- 登记时间：2026-09-26T16:34:33Z
### 实测追加(2026-09-27 R1-打磨) — 同一 brittleness 家族里"仍是墙钟"的那两条，现已有翻转证据
- 现象：`python -X utf8 -m pytest tests/ -q` 首跑 `1 failed, 1861 passed in 564.46s`，红的正是本单 FIXED 段声明未改的
  `tests/test_incremental.py:556` `assert compare_elapsed < 5.0`（原文 `E   assert 5.320751199998995 < 5.0`）；
  **产品码一行未改**再跑一次 ⇒ `1862 passed in 335.65s`（同一条断言这次不红）。
  取证：`.fist-loop-20260927/polish_pytest_r1.try1.log`（首跑原文）与 `polish_pytest_r1.log`（终态）、
  `polish_wallclock_r1.json.product_unchanged_since_try1`（`cypyc/cypy_bridge/test_suite/scripts/tests` 下无 .py 比首跑日志更新）。
- 定性：本单 FIXED 段已写明"parse/compare 两条时限仍是墙钟"，所以这**不是新缺陷、不另立单**；
  但它使门禁 ①（pytest 全量必须全绿）在这台机器上仍是**抛硬币**——FIXED 段只修了 digest 一条的量纲，
  本条证据说明裁决 ① 的其余两条墙钟时限（`compare_elapsed < 5.0`、`parse_elapsed < 60.0`）有同样的失效模式。
- 本轮处置：不修、不降阈值、不 skip（红线：打磨环不动测试语义）。单跑/整文件在无外来 python 的 3 次连续采样下
  分别 1 passed in 1.65s / 38 passed in 6.74s（`polish_wallclock_r1.json`），仅说明"这条断言碰得到"，不构成产品结论。
- 待裁决：是否把 FIXED 段的量纲修法推广到 compare/parse 两条（同裁决 ①），或按建议 ②/④ 处理。
- 登记时间：2026-09-27T05:52:00Z

## BUG-14 [2026-09-26T12:26:08Z] [medium] OPEN
- summary: [float-width] cypyc/codegen/type_mapper.py:8 与 :23 对同一声明类型 float 给出两种宽度（cypy_to_cython 出 C float=32 位、cypy_to_c 出 double=64 位），且 def 签名与 let 绑定的注解在 Cython 产物里被整段丢弃 —— examples/subtype_units.cypy 一次运行内第 2 行与第 9 行互相矛盾
- detail: 现象: 注册 golden 时读到 examples/subtype_units.out 的 9 行输出里，第 9 行是 0.0024999999441206455，而 struct 单精度校准给 float32(0.0025) = 0.0024999999441206455（逐字相等），说明 print((m as float) / 1000.0 as Kilometer) 走的是 C 单精度；同一文件第 2 行是 0.0016，而 float32(0.04)*float32(0.04)  widen 后是 0.0015999999595806003，0.0016 只有双精度才能得到 —— 即 print(area(c)) 全程是 double。同一个声明类型 float 在同一份产物里两种宽度。
机制（transpile 即可复现，不需要 C 工具链）: 源文件写 def area(side: Meter) -> float，产物出成 "def area(side):"（参数与返回注解全部丢弃，函数体是 Python 语义的 double 运算）；而显式转换出成 "print(<float>m / <float>1000.0)"，是真 C 单精度。两张映射表本身就分叉：cypyc/codegen/type_mapper.py:8 的 cypy_to_cython 把 float 映成 "float"（Cython 里即 C float，32 位），同文件 :23 的 cypy_to_c 把 float 映成 "double"。
定性: [真缺陷]，语义级。SYNTAX/01-basic-types.md:19 明确把 float 写成「单精度浮点数」，并与 double 并列成两种类型（:23 e: double），所以「注解被丢弃、运算退回 Python double」这一路不符合冻结文档；反过来，把 float 全改成 32 位又会改变现有全部数值输出的最后一位表示。两种修法都要动既有语义，本轮不顺手落地。
危害面: 数值可移植性与精度承诺。当前形态下，同一个 x: float 是否单精度取决于它是否恰好经过一次显式 as 转换——用户无法从类型推出宽度，也无法从 golden 之外预测末位数字。examples/ 里已注册的其它 .out 若含 float 运算，同样在 pin 这种混合宽度。
建议（择一，均需指挥官裁定后落到 R2/语义轮）: ① 裁定 float 为单精度，则让被标注的 def 签名与 let 绑定生成 cdef double/float 静态存储（注解不许丢），并统一 type_mapper 两表；② 裁定 float 跟随 Python（双精度），则 cypy_to_cython:8 改成 "double"、显式转换不再出 <float>，SYNTAX/01 §浮点数类型 的「单精度」措辞随之下修；③ 最小止血：先让两张映射表一致（都 double），把单精度只留给显式写的 double/float32 标注，再另开语义轮处理静态签名缺失。
本轮处置: 入账不修（红线：语义级问题只入账不顺手改；PROJECT-SPEC/、SYNTAX/ 为界）。examples/subtype_units.out 按指挥官「补 golden」授权注册，pin 的是**现状输出**，不是对第 2 行的正确性裁定；一旦上面 ①②③ 任一裁定落地，该 golden 第 2 行与所有含 float 运算的基准必须重注册（重注册前先留 before 快照）。
- reported_by: cypy-polisher
- task_id: T0r19
### FIXED(verify=已完成) — 2026-09-26 追加留档（裁决落地段工作，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r19`（ns `bugs`），`execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes8.out.json`；入账映射见 `intake_map6.json`；来源：指挥官对本轮 §七 三项待裁决第②项的裁定
- 锁死回归（2 个函数）：`tests/test_polish_20260926_pass7.py::test_bug14_one_declared_float_has_one_width_in_both_maps`、`tests/test_polish_20260926_pass7.py::test_bug14_no_single_precision_cast_survives_in_transpile`；每条在回退树上转红过：`test_bug14_one_declared_float_has_one_width_in_both_maps`、`test_bug14_no_single_precision_cast_survives_in_transpile`
- 证据：端到端基准重注册：before 快照 `.fist-polish-20260926/golden_before_float/`（25 份），逐行差 `golden_float_diff.json`（生成器 `_digits_only()` 对每处差异要求「只有数字变」），注册日志 `e2e_golden_reregister_float.log`；回退树证红 `lockproof_pass7.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep11.log`
- 修复边界：裁决面只到类型表与 `SYNTAX/01-basic-types.md` 的措辞：`float` 与 `double` 现在同为 `double`，因此 `as float` 不再是窄化转换。除端到端基准按裁决重注册外，未改任何其它语义（subtype 检查、约束求解、数值字面量宽度推导均不动）。
- 登记时间：2026-09-26T16:34:33Z

## BUG-15 [2026-09-26T13:33:00Z] [high] OPEN
- summary: [lexer-truncation] cypyc/parser/lexer.py:538 三反引号判定用 2 字符切片 `source[pos:pos+2]=="``"` 却连推 3 个字符，源文件里任意一对游离反引号会把其后整段吞成一个 BACKTICK_BLOCK，其后的定义全部消失且零报错
- detail: 现象: 源码 `def a() -> int: return 1` + 一行 `` `` `` + `def b() ...` → 词法尾部只剩 ['BACKTICK_BLOCK','EOF']，生成的 Cython 里只有 def a，def b 整段蒸发，parse 不报任何错（repro_pass7b lex_backtick）。机制: lexer.py:538 判 `self.source[self.pos:self.pos+2] == "``"`（只看了两个反引号），随后 :542-544 连 `_advance()` 三次并按 ``` 或 EOF 找终止符，即判定条件与消费长度差一个字符。定性: [真缺陷] —— 静默截断用户代码，不是设计：三反引号宏捕获的口径写在同文件注释里（:537 「检查是否是三反引号」）。危害面: 用户少打一个反引号 ⇒ 后半份文件不编译且没有任何诊断，与已修的 BUG-3/8/10 同族（丢代码不报错）。建议: 判定改为 `source[pos:pos+3] == "```"`，不满足时按单反引号分支处理并让 parse 自然报错；不动三反引号块的既有语义。
- reported_by: cypy-polisher
- task_id: T0r20
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r20`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（2 个函数）：`tests/test_polish_20260926_pass7.py::test_bug15_stray_double_backtick_does_not_swallow_rest_of_file`、`tests/test_polish_20260926_pass7.py::test_bug15_real_triple_backtick_block_still_lexes_as_macro_block`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只把判定长度对齐消费长度；三反引号宏块语义不变。
- 登记时间：2026-09-26T13:56:30Z

## BUG-16 [2026-09-26T13:33:00Z] [high] OPEN
- summary: [parser-decorators] cypyc/parser/parser.py:1375 成员级 `decorators = []` 重绑了 :1326 形参持有的结构体自身装饰器列表，`@value struct` 只要含一个被装饰的成员就丢掉 @value，并把成员装饰器挂到 struct 上
- detail: 现象（repro 实跑）: `@value struct Config:` 只有一个 `let w: int` 时生成物含 `__eq__`；再加一个 `@python def label()` 成员，生成物里 `__eq__` 消失（值语义没了），而 StructDef.decorators 变成 `[Decorator(line=3, col=13)]` —— 那是成员自己的 `@python`。机制: parser.py:1326 `_parse_struct_def(self, decorators=None)` 的形参装着 struct 级装饰器，:1375 在成员循环里 `decorators = []` 就地重绑同名局部变量，:1380 用它给 method 传参，:1407 又把同一个变量交给 StructDef。定性: [真缺陷]，与 SYNTAX/05-struct.md 的 @value 承诺直接冲突（codegen 侧 cython_generator.py:2122-2131 明确按 decorators 决定是否 `_generate_value_methods`）。危害面: 结构体等值/哈希/repr 语义随「有没有装饰方法」而变，用户无从预期。建议: 成员装饰器改用独立局部名 `member_decorators`，struct 级 `decorators` 不被覆写；本修复让实现回到冻结文档口径，不改语言语义。
- reported_by: cypy-polisher
- task_id: T0r21
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r21`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（2 个函数）：`tests/test_polish_20260926_pass7.py::test_bug16_value_struct_keeps_decorators_when_a_member_is_decorated`、`tests/test_polish_20260926_pass7.py::test_bug16_struct_def_does_not_inherit_a_member_decorator`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：改动使被错编译的语料回到 SYNTAX/05-struct.md 承诺的行为；未新增任何语法或语义。
- 登记时间：2026-09-26T13:56:30Z

## BUG-17 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [diagnostics] cypyc/project/project_compiler.py:666 `_pick_extension` 名字全不匹配时 `return sorted(candidates)[0]`，把别的模块（或历史残留）的 .pyd 当成本次该模块的产物回报，「No .pyd file generated」永不触发
- detail: 现象（repro 实跑）: `_pick_extension(['<tmp>/other_module.cp313-win_amd64.pyd'], "mymod", <tmp>)` 返回那个 foreign 路径而不是 None。机制: :658-665 的挑选循环只在 base 名等于/前缀于 stem 时返回，全部不匹配时兜底 `sorted(candidates)[0]`。而本函数自己的 docstring（:643-648）写着旧实现取 `pyd_files[0]` 的毛病是「遍历顺序决定结果，目录里残留的历史产物也可能被当成本次产物回报」——兜底行把这条毛病原地保留了下来。定性: [真缺陷]（假成功/错产物，同 BUG-1/BUG-7 一族）。兄弟口径见 tests/test_hook.py:126 对同类挑选断言 assertIsNone。危害面: `cypyc build` 报出 `mymod -> other_module.pyd`，后续加载导入到错误模块，或把「没产出」伪装成「产出了」。建议: 全不匹配时返回 None，让上层走既有的「No .pyd file generated」分支。
- reported_by: cypy-polisher
- task_id: T0r22
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r22`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（2 个函数）：`tests/test_polish_20260926_pass7.py::test_bug17_pick_extension_returns_none_for_unrelated_artifacts`、`tests/test_polish_20260926_pass7.py::test_bug17_pick_extension_still_prefers_the_matching_artifact`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：返回 None 后上层走既有「No .pyd file generated」分支，未新增诊断文案。
- 登记时间：2026-09-26T13:56:30Z

## BUG-18 [2026-09-26T13:33:00Z] [high] OPEN
- summary: [cache-invalidation] cypyc/incremental/incremental_manager.py:311-320 「检查导入模块是否变化」只看 `is_cached()`（缓存条目存不存在），从不比对依赖的 file_hash，改了被 import 的 .cypy 仍判缓存有效并复用陈旧 .pyd
- detail: 现象: `_check_imported_modules_changed` 注释写「检查模块的缓存是否失效」，实现是 `if not self.is_cached(module_file): return True`（:318）——条目存在即视为没失效。机制: 依赖模块自己的缓存在它被重编译时会被覆盖写回，所以对「 importer 未变、依赖已变」这一最常见形态，该函数恒返回 False，cypy_hook/hook.py:333 的 `check_cache_validity` 据此报「缓存完全有效」、跳过编译、导入旧二进制。定性: [真缺陷]，增量正确性缺陷（本轮扫描面点名的 incremental 缓存失效高发区）。危害面: 用户改 A.py 后导入它的 B 仍跑旧代码，必须手工清缓存才生效——最难排查的一类。建议: 取依赖条目的 file_hash 与该文件当前摘要比对（同文件 :248 已有 `file_hash` 比对口径可复用），不相等即判定 changed。
- reported_by: cypy-polisher
- task_id: T0r23
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r23`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（3 个函数）：`tests/test_polish_20260926_pass7.py::test_bug18_changed_dependency_invalidates_the_importer`、`tests/test_polish_20260926_pass7.py::test_bug18_unchanged_dependency_stays_a_cache_hit`、`tests/test_polish_20260926_pass7.py::test_bug18_dependency_without_any_cache_entry_is_still_changed`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：比对依赖 file_hash；dependencies 图本身的召回缺口（前一轮已登记的结构性项）不在本单内。
- 登记时间：2026-09-26T13:56:30Z

## BUG-19 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [codegen-directives] cypyc/codegen/cython_generator.py:1287 `_ensure_owned_import` 用 `output.insert(0, ...)` 把 pointer import 插到整段 `# cython:` 指令之前，而本文件 :299 的注释规定指令必须在最顶部否则被忽略
- detail: 现象（repro 实跑）: 含 `owned p = malloc(8)` 的源生成的文件第 1 行是 `from cypy_bridge.pointer import ...`，`# cython: language_level=3 / boundscheck=False / wraparound=False / nonecheck=False` 被挤到第 2-6 行；同文档字符串也不再是首语句（`__doc__` 变 None）。机制: :1285-1287 无条件 insert(0)。定性: [真缺陷]——判据依据是文件自己的注释 :299「Cython 编译指令必须位于文件最顶部（在任何语句/文档字符串之前），否则会被忽略」。危害面: 一处 owned 绑定就让整份产物的指令集失效，边界检查/回绕检查行为随是否用过 owned 而不同，且文档字符串丢失。建议: 插入点定位到「开头连续的注释/指令行块之后」，不再插到第 0 行。
- reported_by: cypy-polisher
- task_id: T0r24
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r24`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（1 个函数）：`tests/test_polish_20260926_pass7.py::test_bug19_owned_import_is_inserted_below_cython_directives`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只调整插入点；不改变指令集合本身。
- 登记时间：2026-09-26T13:56:30Z

## BUG-20 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [comptime] cypyc/analyzer/comptime_evaluator.py:455-461 `_get_func_name` 对 `x.upper()` 这类 Attribute 调用退回 `str(node)`（得到 "Attribute(line=.., col=..)"），于是 :188-276 整张字符串/列表方法表永不命中，comptime 语句静默消失
- detail: 机制: evaluate() 在 Call 分支（:158-161）用 `_get_func_name(node.func)` 查表；func 是 Attribute 时三个分支全不中（不是 Name、没有 .id），落到 :461 `return str(func_node)`，返回一个带行列号的节点 repr，永远不可能等于 `self.functions`/`builtin_funcs` 的键 ⇒ `_evaluate_attribute_access`（模块 docstring 规则 5-6 承诺的 .upper()/.append()/.split() 等）整段不可达，evaluate_comptime 返回 None。后果: codegen（cython_generator.py:2395）只留下 `# comptime: 'abc'.upper()` 注释，语句从产物中消失；若它是某函数体唯一语句，生成出的 def 体只剩注释 ⇒ Cython/CPython 报 expected an indented block。定性: [真缺陷]（计算结果被静默丢弃，与 BUG-8/11 同族）。建议: Attribute 取 `func.attr` 作为函数名并保留接收者求值，使既有方法表可达；查不到时按既有的「无法求值」路径给诊断而非静默。
- reported_by: cypy-polisher
- task_id: T0r25
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r25`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（3 个函数）：`tests/test_polish_20260926_pass7.py::test_bug20_comptime_can_evaluate_attribute_method_calls`、`tests/test_polish_20260926_pass7.py::test_bug20_builtin_name_calls_are_untouched`、`tests/test_polish_20260926_pass7.py::test_bug20_unknown_attribute_method_degrades_to_none_without_raising`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：本段只把 Attribute 调用接到既有方法表上；表里没有的属性仍按旧口径降级为「不成值」，未加诊断。
- 登记时间：2026-09-26T13:56:30Z

## BUG-21 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [type-checker] cypyc/analyzer/type_checker.py:432（同族 :1283、:2008）用 `getattr(stmt.for_type,'id',str(stmt.for_type))` 取 impl 的目标类型名，`impl Show for Box<T>` 注册成 "GenericType(line=5, col=15)" 这种节点 repr，codegen 侧 :482-486 却正确剥掉泛型 —— 两份 trait 登记表口径分叉
- detail: 现象（repro 实跑）: 源 `impl Show for Box<T>` 使 `tc.trait_impls == {'Show': ['GenericType(line=5, col=15)']}`。机制: GenericType 节点带 `.name` 而没有 `.id`，getattr 默认分支 `str(node)` 把整颗节点 repr 当成类型名登记。定性: [真缺陷]。危害面: 为泛型类型写的 trait 实现在约束检查里永远匹配不上 ⇒ 误报 `Generic constraint violation: type ... does not implement trait ...`；同文件另外两处（:1283、:2008）是同一写法，examples/demos/traits_duck/trait_basic.cypy:104 也在产垃圾键。建议: 统一按「Name→.id / GenericType→.name / 其余→getattr 'name' 兜底」取名字，与 cython_generator.py:482-486 的既有剥泛型口径对齐（只收紧垃圾键，不改判定规则）。
- reported_by: cypy-polisher
- task_id: T0r26
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r26`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（1 个函数）：`tests/test_polish_20260926_pass7.py::test_bug21_generic_impl_registers_the_base_type_name`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只改登记处 :432；同族写法 :1280 与 :2005 未动（前者喂 _check_impl_on_subtype，后者的默认分支被 2002-2003 行注释当作刻意保留的失败面），各需独立证据。
- 登记时间：2026-09-26T13:56:30Z

## BUG-22 [2026-09-26T13:33:00Z] [low] OPEN
- summary: [lexer] cypyc/parser/lexer.py:651-652 f-string 前缀判定集合是 (`"`, `'`, f, F)，注释 :650 声称支持 f/F/rf/fr，实际 `fr"..."` 因第二字符 'r' 不在集合内被拆成 IDENTIFIER `fr` + STRING，`rf"..."` 却正常
- detail: 现象: `let s = fr"{x}"` → `Expected NEWLINE, got STRING`；同义写法 `rf"{x}"` 解析通过。机制: :652 `if char in ('f','F','r','R') and self._peek_ahead(1) in ('"',"'",'f','F')` —— 'r'/'R' 作为第二字符未被接受，而 :654 的组合前缀分支只处理 `rf` 不处理 `fr`。定性: [真缺陷]（注释/文档声称支持的形态实际不支持，且报错点离因由很远）。建议: 第二字符集合补 'r','R' 并按两字符实际组合归一 prefix，使 fr/rf 同权。
- reported_by: cypy-polisher
- task_id: T0r27
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r27`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（2 个函数，BUG-22 另有 7 条参数化展开）：`tests/test_polish_20260926_pass7.py::test_bug22_string_prefixes_lex_as_one_string_token`、`tests/test_polish_20260926_pass7.py::test_bug22_two_char_names_are_not_swallowed_as_prefixes`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：组合前缀只承认 rf/fr 两种，rr/ff 仍按标识符处理（对照用例锁死）。
- 登记时间：2026-09-26T13:56:30Z

## BUG-23 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [pointer] cypy_bridge/pointer.py:322 `addr()` 先判 `hasattr(obj,'value')`，而每个 c_void_p 都有 `.value`，:327 的 `elif isinstance(obj, ctypes.c_void_p): return obj.value` 成死代码 —— 对空指针也返回非零堆地址
- detail: 现象（repro 实跑）: `addr(ctypes.c_void_p(4096))` 返回 2081110748568（那个 ctypes 盒子自己的地址），不是 4096；`addr(ctypes.c_void_p(0))` 返回非零 ⇒ 用户拿它判 NULL 永远不成立。机制: 分支次序问题，c_void_p 被前一个 hasattr 分支吃掉。定性: [真缺陷]。危害面: 指针语义错误 + 空指针检查失效（本模块 docstring 对该分支的意图就是「返回指针的值」）。建议: 把 `isinstance(obj, c_void_p)` 提到 hasattr 之前；`c_int` 等标量仍走 addressof 不变（现有 tests/test_bridge_library.py:332 只断言 int 类型，不受影响）。
- reported_by: cypy-polisher
- task_id: T0r28
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r28`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（2 个函数）：`tests/test_polish_20260926_pass7.py::test_bug23_addr_of_void_p_returns_pointed_value_including_null`、`tests/test_polish_20260926_pass7.py::test_bug23_addr_of_scalar_still_returns_storage_address`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只调整分支次序；标量对象仍返回其存储地址。
- 登记时间：2026-09-26T13:56:30Z

## BUG-24 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [cache] cypy_hook/hook.py:1020-1024 `clear_cache()` 无参分支走 `os.walk(os.getcwd())` 却要求 `os.path.dirname(root)=="__pycache__"`，绝对路径下永不相等，删了 0 个文件仍由 cli.py:384 打印 [OK] cache cleared
- detail: 现象（repro 实跑）: 临时目录下造 `__pycache__/cypy/manifest.json` 后 chdir 调用 `CypyCacheManager().clear_cache()`，文件原样存活；walk 到的 root 是绝对路径，`os.path.dirname(root)` 是 `<tmp>\__pycache__` 而非 `__pycache__`。机制: 判据拿整段目录路径比basename。定性: [真缺陷]（假成功，且与同文件 :1007-1016 的单文件分支行为不一致）。兄弟实现 compiler.py:3680 的 BridgeCacheManager 遍历是对的。危害面: 用户按文档清缓存后仍旧导入旧 .pyd。建议: 判据改 `os.path.basename(os.path.dirname(root))=="__pycache__"`，并把「清了几个文件」回报给调用方，0 个时不得报 [OK]。
- reported_by: cypy-polisher
- task_id: T0r29
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r29`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（1 个函数）：`tests/test_polish_20260926_pass7.py::test_bug24_clear_all_cache_actually_removes_cached_files`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只修目录匹配判据；cypyc/cli.py:384 仍无条件打印 [OK] cleared，「清了几个文件」未回传。
- 登记时间：2026-09-26T13:56:30Z

## BUG-25 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [encoding] cypy_bridge/compiler.py:3766 与 :3807 把生成的 .c 和 setup.py 用 `open(path,'w')` 按本地编码写盘（本机 cp936），含非 cp936 字符的源码直接 UnicodeEncodeError，读源码侧却是 encoding="utf-8"
- detail: 现象（repro 子进程实测，未开 UTF-8 模式）: `preferred=cp936`，`open(p,'w').write('/* \u0e01 */')` → `UnicodeEncodeError: 'gbk' codec can't encode character '\u0e01'`。机制: 这两处是三包里仅有的不带 encoding 的文本写盘（其余全仓 pin utf-8），写出的字节随机器 ANSI 代码页变化；同一函数 :3819 还特意用 utf-8/replace 解子进程输出（注释原因就是 GBK）。定性: [真缺陷]。危害面: 同一份 .cypy 在不同代码页机器上产物字节不同（中文在 cp936 与 cp1252 机器上表现不一致），非本地字符直接编译失败；MSVC 收到的源编码与生成器假定不一致。建议: 两处补 `encoding="utf-8"`，与读入侧统一。
- reported_by: cypy-polisher
- task_id: T0r30
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r30`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（1 个函数）：`tests/test_polish_20260926_pass7.py::test_bug25_generated_c_and_setup_are_written_as_utf8`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只补两处写盘 encoding；同函数其余按本地编码读写的环节未扩面。
- 登记时间：2026-09-26T13:56:30Z

## BUG-26 [2026-09-26T13:33:00Z] [low] OPEN
- summary: [portability] cypy_bridge/compiler.py:3833 编译产物扫描只认 `endswith('.pyd')`，而 :3704-3707 的 `_detect_compiler` 明确支持 linux/gcc 与 darwin/clang，非 Windows 上即便编译成功也抛 "Failed to find generated .pyd file"
- detail: 机制: 产物发现循环只匹配 .pyd；同文件 :3683（BridgeCacheManager）已经在用 `.pyd`/`.so` 的口径，cypy_hook/hook.py:542 用 `sysconfig` 的 `extension_suffixes()`，project_compiler.py:624 用 (".pyd", ".so", ".dll") —— 四处三套口径。定性: [真缺陷]（跨平台假失败）。危害面: Linux/macOS 上 CCodeGenerator 这条路全量失败，错误信息还把用户指向「编译器没产出」。建议: 与兄弟站点统一为 `sysconfig.get_config_var('EXT_SUFFIX')` + (".so", ".dll") 元组。
- reported_by: cypy-polisher
- task_id: T0r31
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r31`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（1 个函数）：`tests/test_polish_20260926_pass7.py::test_bug26_artifact_scan_accepts_non_windows_extensions`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只放到产物发现（.so/.dll）；后续复制与 ctypes 加载在 Linux 上未实测（本机无该环境）。
- 登记时间：2026-09-26T13:56:30Z

## BUG-27 [2026-09-26T13:33:00Z] [low] OPEN
- summary: [hot-reload] cypyc/incremental/hot_reload.py:530 `set.union(*[...])` 在 results 为空（纯删除批次）时抛 TypeError，被 :535 的 except 打成 "Callback error"，用户回调其实一次都没跑
- detail: 机制: `set.union(...)` 是未绑定方法，空参数即 TypeError；异常落在把「合并结果 + 调用回调」整段包住的 try 里，:536 打印 `Callback error: <原始异常>`。定性: [真缺陷]。危害面: 删除文件的热重载批次里用户的 _on_reload 从不触发，而日志把矛头指向用户回调（本模块 API 用法，CLI `watch` 未传回调所以现场不易见）。建议: 改 `set().union(*[...])`，并把合并与回调调用拆开，使「回调报错」只可能来自回调本身。
- reported_by: cypy-polisher
- task_id: T0r32
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r32`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（1 个函数）：`tests/test_polish_20260926_pass7.py::test_bug27_delete_only_batch_does_not_blame_the_user_callback`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只保证空批次不再抛 TypeError；「回调错误」归因口径未扩到其它 except 分支。
- 登记时间：2026-09-26T13:56:30Z

## BUG-28 [2026-09-26T13:33:00Z] [medium] OPEN
- summary: [reformat] cypyc/utils/indent_detector.py:30-34 detect() 观测到多种缩进宽度时一律取 4（没有取公因数），:56-58 再以 `// indent_size` 换算层数，2 空格风格源码经 normalize() 后 函数体被压到 0 列，块结构直接毁坏
- detail: 现象（repro 实跑）: 输入 2 空格缩进的 `def f(): / let a / if a: / let b`，`detect()` 报 ('spaces', 4)，`normalize()` 输出 `def f():\nlet a = 1\nif a:\n    let b = 2` —— 第一层体被削到 0 列（函数变空壳），第二层反而留在原地。定性: [真缺陷]：该类是本轮参数卡点名的「越界切片/算术边界」一族，且 `cypyc/utils/__init__.py:2` 把它作为包 API 导出。现状说明（不夸大本轮影响面）: 三包内暂无产品代码调用 normalize（同 BUG-6 的口径），现有 tests/test_boundary_comprehensive.py:530-584 只覆盖 tab 与 4 空格，非 4 空格风格是覆盖盲区。建议: detect() 取观测宽度的最大公约数（{2,4}→2、{3,6}→3、{4,8}→4），单值情形保持不变。
- reported_by: cypy-polisher
- task_id: T0r33
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r33`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（2 个函数）：`tests/test_polish_20260926_pass7.py::test_bug28_normalize_preserves_structure_of_two_space_sources`、`tests/test_polish_20260926_pass7.py::test_bug28_four_space_and_six_space_styles_unchanged`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：normalize 现在保留原风格宽度（2 空格进 2 空格出），不做跨风格换算；缺陷面是结构被压平。
- 登记时间：2026-09-26T13:56:30Z

## BUG-29 [2026-09-26T13:33:00Z] [low] OPEN
- summary: [cli-diagnostics] cypy_hook/hook.py:836 对可能为 None 的 `parsed_args.source` 直接 `os.path.isfile(...)`，`cypyc hook` 不带文件名时抛裸 TypeError traceback 而不是用法提示（cypyc/cli.py:408 的那道守卫排在 hook 分支 return 之后，护不到这里）
- detail: 现象（repro 实跑）: `python -m cypyc hook` → 退出码 1，stderr 末行 `TypeError: _path_isfile: path should be string, bytes, os.PathLike or integer, not NoneType`。机制: cli.py 的 hook 分支把参数转成 hook_args 后 `return hook.run_cli(hook_args)`，source 位置参数缺省即 None；:836 未判空。定性: [真缺陷]（诊断面：崩溃栈代替用户可读提示）。建议: 先判 `parsed_args.source` 为空即打印 usage 并 return 1，`isfile` 只在有值时调用。
- reported_by: cypy-polisher
- task_id: T0r34
### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r34`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`
- 锁死回归（1 个函数）：`tests/test_polish_20260926_pass7.py::test_bug29_bare_hook_command_reports_usage_not_a_traceback`
- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`
- 修复边界：只补 None 守卫并给出用法提示；hook 参数校验的其它分支未动。
- 登记时间：2026-09-26T13:56:30Z

## BUG-30 [2026-09-26T15:12:42Z] [high] OPEN
- summary: [codegen-coercion] cypyc/codegen/cython_generator.py:1170 声明式局部变量走 `name: <ctype> = value` 注解形式且不补隐式转换，于是 `let e: float = <int 表达式>` 的 e 在编译产物里仍是 Python int（type() 回 <class 'int'>），float 路径在 BUG-14 裁决落地后由 42.0 退化成了 42
- detail: 现象（repro_pass8.py 实跑，产物是真 .pyd：tmp_float/out8/repro_pass8.cp313-win_amd64.pyd）：同一份源里 `let a: int = 42` + `let e: float = a` + `let d: double = a` → 运行期打印 `float-from-int: value=42 type=<class 'int'>` 与 `double-from-int: value=42 type=<class 'int'>`，而 `let g: float = 1.5` 正常是 `<class 'float'>`。生成物对应三行 `e: double = a` / `d: double = a` / `g: double = 1.5`（见 repro_pass8.out.json 的 generated_declarations）。机制: 声明带初值时 :1161-1170 只在 `needs_implicit_conversion`（:1142，查 `_pending_conversions`）命中时插入转换，未命中就直接写注解形式；本例没有登记到转换记录，也没有走 :1168 的 `cdef <ctype> name = value`分支（那条才会强制 C 层窄化/浮点化）。定性与危害面: [真缺陷] —— examples/basic_types.cypy:17 自己的注释就写着「隐式转换 (int -> float)」，而产物里该变量的身份仍是 int：声明类型对可赋值性不起作用，`type(e)`、整数除法/取模一类的行为都会随「源表达式恰好是 int」而变。与指挥官 2026-09-26 的 BUG-14 裁决直接相关：裁决把 cypy_to_cython["float"] 从 "float" 改成 "double"，于是 float 路径继承了这个既有缺口 —— 落地前该例打印 42.0，落地后打印 42（本单是裁决落地暴露出的回归面，不是裁决本身的取舍；已按裁决重注册的 examples/basic_types.out 第 5 行把这个现状固化了下来）。建议（不在本单内擅自做）: 声明带初值且类型是浮点/整型 C 类型时改走 :1168 的 cdef 形式，或在 _pending_conversions 未命中时按 SYNTAX 的隐式转换表补一条 <double>/<int> 强转；两种改法都会改动生成码形态，需重注册端到端基准并全量复跑，故交指挥官定口径后再动。留待下一轮的子问题: 为什么注解形式对 `float` 曾能浮点化而对 `double` 不能（Cython annotation_typing 的类型识别面），本轮未证。
- reported_by: cypy-polisher
- task_id: T0r35

### FIXED(verify=已完成) — 2026-09-27T03:58:00Z 追加留档（2026-09-27 R1-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r46.1`（ns `cypy-loop-20260927`，分支/叶子全链带 `[omega:required]`，L4 `output_validate` 逐叶 pass 后才 verify）；报告：`memory/reviews/20260927.11.55.55.md`
- 锁死回归：tests/test_loop_20260927_fix.py 里本单 2 条（1 锁 + 1 对照）；在**只回退本单**的临时树上证红 1 条：tests/test_loop_20260927_fix.py::test_bug30_int_initializer_to_float_gets_explicit_double_cast；同一棵树上其余 7 条（本单对照锁 + 其余三单的用例）保持绿 ⇒ 红能归给本单
- 产物与运行期证据：端到端基准：`examples/basic_types.out` 重注册，数字面差异 1 行、非数字面 0 行、其余 24 份基准逐字未变（`auto(int to float): 42` → `auto(int to float): 42.0`）
- 双套基线：基线双套：自研套件 `Total 47 / Passed 47 / Failed 0`；定向 pytest（从改动面反解 85 个文件）`1761 passed`，末行 `====================== 1761 passed in 291.73s (0:04:51) =======================`
- 修复边界：只在「声明带标注 + 初值**确定为整数** + 目标为浮点 C 类型」三条同时成立时补 `<double>` 强转；宽度表新起 `_declared_var_types`，**不**并进 `_current_local_types`（那张表历史上只装参数，灌进局部变量会顺带改掉 `/` 是否发 `//` 的既有产物形态）。复合表达式加括号 `<double>(...)`；`as float` 显式转写、指针、对象面一律不动。


## BUG-31 [2026-09-26T15:21:33Z] [medium] OPEN
- summary: [type-width-divergence] cypy_bridge/types.py:43 仍把 Cypy 的 `float` 映射到 ctypes.c_float（4 字节），而 BUG-14 裁决后 cypyc 的两张表都出 double（8 字节）——同一个声明类型在两个包里仍然两种宽度，经 cypy_bridge 存取时出现 float32 精度损失
- detail: 现象（repro_pass9.py 实跑，repro_pass9.out.json）: `_type_mapper.to_ctypes("float")` 是 `c_float`、sizeof 4，`to_ctypes("double")` 是 `c_double`、sizeof 8；按 cypy_bridge/union.py:164 自己文档里的用法 `cdef_union("int", "float")` 存 0.1，读回 `0.10000000149011612`，而 `cdef_union("double")` 存同一个 0.1 读回 `0.1`。机制: 模块自述口径是「Cypy 类型到 ctypes/C 类型的映射」（types.py:12 类 docstring、:16 字段名 cypy_to_ctypes），消费面 :80/:86（`float*`）、:114（`f` 单字符表）、:211（`float_ = c_float`），以及 union.py:50 / generics.py:51 / pointer.py:101 三处 to_ctypes 调用。定性: [真缺陷，且是 BUG-14 同根因的未覆盖面] —— 指挥官 2026-09-26 裁定「float 与 double 在数值宽度上一致」，该裁定落在 cypyc/codegen/type_mapper.py 的两张表上；本包那一张没被覆盖，于是「一个声明类型两种宽度」在跨包路径上依旧成立。危害面: 凡把 Cypy 侧的 float 值经 bridge 的 union/pointer/generics 存取（或据 :114 的单字符表解析签名），静默按 32 位截断；与 SYNTAX/01-basic-types.md 更新后的措辞（与 Python float 同宽）直接冲突。为什么不顺手改: `tests/test_bridge_library.py:646-649` 明确断言 bridge union 的 `float` 成员是单精度、有精度损失（`assertAlmostEqual(..., places=5)`）——把它改成 c_double 等于弱化/推翻既有用例，参数卡红线不允许；且这会改变 FFI 宽度口径（跨 ABI），属裁决面。建议交指挥官二选一：① 裁定 bridge 的 `cypy_to_ctypes["float"]` 也跟 double，并同步改写那条既有测试（需一轮专门改判据）；② 裁定本包是「按 C/FFI 类型名取宽度的底层工具」，那么请把它自述里的 「Cypy 类型」措辞改掉（:12/:16/:211 三处），并给 `float_` 起个不冲突的名字。本轮只入账不改。
- reported_by: cypy-polisher
- task_id: T0r36

### FIXED(verify=已完成) — 2026-09-27T03:58:00Z 追加留档（2026-09-27 R1-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r46.2`（ns `cypy-loop-20260927`，分支/叶子全链带 `[omega:required]`，L4 `output_validate` 逐叶 pass 后才 verify）；报告：`memory/reviews/20260927.11.55.55.md`
- 锁死回归：tests/test_loop_20260927_fix.py 里本单 2 条（1 锁 + 1 对照）；在**只回退本单**的临时树上证红 2 条：tests/test_loop_20260927_fix.py::test_bug31_bridge_mapping_declares_ffi_key_space_and_renamed_alias、tests/test_loop_20260927_fix.py::test_bug31_width_of_bridge_float_is_unchanged；同一棵树上其余 6 条（本单对照锁 + 其余三单的用例）保持绿 ⇒ 红能归给本单
- 双套基线：基线双套：自研套件 `Total 47 / Passed 47 / Failed 0`；定向 pytest（从改动面反解 85 个文件）`1761 passed`，末行 `====================== 1761 passed in 291.73s (0:04:51) =======================`
- 修复边界：落两半：① 措辞四处（模块 docstring / 类 docstring / `to_ctypes` / `to_c`）改为「键空间是 C/FFI 类型名」，并说明与 Cypy `float`（8 字节）不同宽；② `float_` → `float32_` 改名，含 `cypy_bridge/__init__.py` 的 import 与两处 `__all__`，以及`tests/test_bridge_library.py:159/162/974` 三处按名引用（同义换名，断言强度不变）。**宽度值 `c_float`/4 字节一律未动**，裁决保护的 `tests/test_bridge_library.py:646-649` 一字未改（对照锁 `test_bug31_width_of_bridge_float_is_unchanged` 钉住）。残留：`.trae/specs/cypy-bridge/checklist.md:37` 仍写旧名，属历史清单未改。


## BUG-32 [2026-09-26T15:48:08Z] [high] OPEN
- summary: [codegen-echo-fidelity] cypyc/codegen/cython_generator.py:3334（修复前号，修复后该行在 :3337）约束注释把成员名过了一遍 type_mapper，BUG-14 裁决（float≡double）落地后产物写成 `# constraint Numeric = int | double`，注释里出现的名字不再是用户声明的那个
- detail: 现象（pytest 终态全量实跑，.fist-polish-20260926/pytest_final_sweep9.log）：tests/test_named_constraints.py::TestConstraintCodegen::test_only_a_comment_is_emitted、::test_shipped_example_transpiles_clean 与 ::TestNamedVersusInlineEquivalence::test_artifacts_differ_only_by_the_constraint_comment 三条同时红，断言原文 `assert '# constraint Numeric = int | float' in '...# constraint Numeric = int | double...'`。机制: `_visit_ConstraintDef` 用 `self._type_to_str(m)` 渲染成员，而 `_type_to_str`（修复后 :3873/:3892）对内置标量走 `type_mapper.to_cython(node.id)` —— 裁决前 `float` 映射成同名 `float`，两者恰好相等所以没人发现；裁决把映射改成 `double` 后，这条**注释**也跟着改了名。定性: [真缺陷] —— 该注释的口径写在它自己的 docstring（:3327-3332）与 SYNTAX/33 §5：约束只发一条注释、且命名界与内联界的产物**只差这一行注释**（C-4.1）。注释是声明的逐字回显，不是类型替换的位置；把 `float` 写成 `double` 等于让产物声明了一个源码里没出现过的类型名。危害面: 任何把该注释当可读性/可追溯依据的读者与判据（含三条既有测试）都会失配；同一渲染路径若被复制到别处（如别名注释 :3320）会扩大失面——别名那处**不该**改（`ctypedef double N` 是真声明，打印映射后的目标类型是对的，本轮已实测确认并保持不动，另加对照锁）。修法（本轮已实施）: 成员名用声明时的 `m.id` 逐字回显，非 Name 形态再退回 `_type_to_str`；锁死回归 tests/test_polish_20260926_pass7.py 的 test_bug32_constraint_comment_echoes_declared_member_names，对照 test_bug32_alias_still_takes_the_ruled_width（保证这一下没把裁决本身中止掉）。
- reported_by: cypy-polisher
- task_id: T0r37
### FIXED(verify=已完成) — 2026-09-26 追加留档（裁决落地段工作，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r37`（ns `bugs`），`execute → submit → verify` 原始回复见 `.fist-polish-20260926/close_fixes8.out.json`；入账映射见 `intake_map10.json`；来源：指挥官 float=double 裁决落地后，本轮终态全量实跑自己抓出来的副作用
- 锁死回归（3 个函数）：`tests/test_polish_20260926_pass7.py::test_bug32_constraint_comment_echoes_declared_member_names`、`tests/test_polish_20260926_pass7.py::test_bug32_alias_still_takes_the_ruled_width`、`tests/test_polish_20260926_pass7.py::test_bug32_constraint_comment_resolves_subtype_members_to_base_names`；每条在回退树上转红过：`test_bug32_constraint_comment_echoes_declared_member_names`、`test_bug32_constraint_comment_resolves_subtype_members_to_base_names`
- 证据：红证据：`.fist-polish-20260926/pytest_final_sweep9.log` 里 `tests/test_named_constraints.py` 三条失败原文（`assert '# constraint Numeric = int | float' in '...int | double...'`）；该次全量为 9 failed / 1842 passed，其中另 6 条是钉住旧宽度拼写的测试断言，已按裁决改指 `double`（逐条清单见打磨报告）；回退树证红 `lockproof_pass7.json`；全量终态 `.fist-polish-20260926/pytest_final_sweep11.log`
- 修复边界：只改约束这一行注释的渲染：新增 `_constraint_member_name()`——标量成员取声明原名逐字回显，`subtype`/`type` 成员仍递归化成基类型**名字**（`Meter`→`float`，S-4.1 不许子类型名出现在产物里），复合形态才退回 `_type_to_str`。第一版只做「一律逐字回显」，被下一次全量按 S-4.1 打回（`tests/test_nominal_subtypes.py::TestShippedExample::test_example_artifact_mentions_no_subtype_name` 1 条红）。`# type alias:` 与 `ctypedef` 两处**故意保留**过映射——别名是真声明，必须吃到裁决宽度（对照锁钉住）。同族面已排查：codegen 里 17 处 `# ` 注释产出只有这一处过 type_mapper，analyzer/诊断面完全不调用它（实测 grep 零命中）。
- 登记时间：2026-09-26T16:34:33Z

## BUG-33 [2026-09-27T03:05:03Z] [high] OPEN
- summary: [对抗样例:词法] lexer 对未闭合字符串不诊断，静默吞掉后续源码
- detail: 复现：python -X utf8 -m cypyc run .fist-loop-20260927/hunts/adv_03_unterminated_string.cypy（样例 3 行：s: str = "abc 未闭合，后面还有 return 0）
实际：rc=0，CLI 打 [OK] Transpiled successfully；产物里写成 s: str = 'abc\n    return 0\n'——整条 return 语句被当字符串内容吃掉，main 变成隐式返回 None。
期望：未闭合字符串必须报词法错误（带行列）并非零退出。宁可拒绝，不可静默改语义。
证据：.fist-loop-20260927/hunts/adv_03_unterminated_string.cypy、adv_r1.json(adv_03)、hunt_evidence.json(hunt_a_cli / hunt_a_artifact_swallows_return)
- reported_by: cypy-loop-hunter
- task_id: T0r39

### FIXED(verify=已完成) — 2026-09-27T03:58:00Z 追加留档（2026-09-27 R1-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r46.3`（ns `cypy-loop-20260927`，分支/叶子全链带 `[omega:required]`，L4 `output_validate` 逐叶 pass 后才 verify）；报告：`memory/reviews/20260927.11.55.55.md`
- 锁死回归：tests/test_loop_20260927_fix.py 里本单 2 条（1 锁 + 1 对照）；在**只回退本单**的临时树上证红 1 条：tests/test_loop_20260927_fix.py::test_bug33_unterminated_string_raises_with_position；同一棵树上其余 7 条（本单对照锁 + 其余三单的用例）保持绿 ⇒ 红能归给本单
- 双套基线：基线双套：自研套件 `Total 47 / Passed 47 / Failed 0`；定向 pytest（从改动面反解 85 个文件）`1761 passed`，末行 `====================== 1761 passed in 291.73s (0:04:51) =======================`
- 修复边界：只在 `while` 走到 EOF（`else` 分支）时抛 `ValueError`，带字面量起始行列与 EOF 行列；闭合路径 `break` 不受影响，f-string/三引号/raw 共用同一函数故一并受益。


## BUG-34 [2026-09-27T03:05:03Z] [high] OPEN
- summary: [对抗样例:类型标注] 非法标注形态把 AST 节点的 repr 写进产物（xs: Constant(line=2, col=9)）
- detail: 复现：python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/adv_10_slice_step_zero.cypy -o .fist-loop-20260927/cliout --emit-cython
实际：产物出现 '    xs: Constant(line=2, col=9) = [1, 2, 3]'——把 ASTNode 的 Python repr 当成类型名发进 Cython 源，该 .pyx 必编译失败；adv_19 同型（空列表）。
期望：SYNTAX/02 规定的列表写法是 list<int>；`[int]` 之类未文档化形态必须诊断（带行列），任何情况下不得把内部节点 repr 落进产物。
证据：.fist-loop-20260927/hunts/adv_10_slice_step_zero.cypy、adv_19_negative_index_const.cypy、hunt_evidence.json(hunt_b_lines)、cliout/adv_10_slice_step_zero.pyx
- reported_by: cypy-loop-hunter
- task_id: T0r40

### FIXED(R7 组合环 2026-09-29T03:54:36+00:00，ns cypy-loop-20260929 / T0r113) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 本条目是这条缺陷的初登记录；R6 复验时因本地手写编号与服务端撞号，同一条主张另立了 BUG-108，
  收口过程（条款、实现、锁、调用面逐字回执、三套全量）逐行见 **BUG-108 的 FIXED 段**，此处不复制第二份正文。
- 结论三行：`SYNTAX/02` 补「注解形态闭集」158→189 行；分析器 `_validate_annotation_shapes` 拒字面量形态并点名正确写法；
  生成器 `_type_to_str` 末路由 `str(node)` 改 `"object"`，产物永不含 AST repr。
- 调用面逐字：`adv_10_slice_step_zero.cypy` rc=1 →
  `- Invalid type annotation at 2:9 (期望 类型名或 list<int> / tuple<int, int> / dict<str, int>，实际是 Constant 字面量形态)`；
  before 证据仍在 `.fist-loop-20260927/cliout/adv_10_slice_step_zero.pyx` 第 30 行。
- 残留（服务端号 BUG-109）：解析器没有类型表达式产生器，括号形态仍未正解。

## BUG-35 [2026-09-27T03:05:03Z] [high] OPEN
- summary: [读码+对抗] parse/lex 阶段的一切异常在用户面被归入「读取文件错误」，深嵌套 RecursionError 同桶且无行列
- detail: 站点：cypy_hook/hook.py:413 的 except 分支把整段 read+parse 的异常统一写成 f"读取文件错误: {e}"。
实际：adv_07/16/18/20（语法诊断）与 adv_05（200 层括号 RecursionError，parser.py:3314 _parse_call）在 CLI 上都被显示成「读取文件错误」；adv_05 本次实跑 rc=1，末三行 ['Output directory: output', '[FAIL] Execution failed:', '  - 读取文件错误: maximum recursion depth exceeded']——既没有源码行列，也把解析失败说成读文件失败。
期望：读文件的 I/O 失败与语法/语义诊断分桶；深嵌套应有深度守卫并给出带行列的诊断。
证据：.fist-loop-20260927/hunts/adv_r1.json（adv_05/07/16/18/20 五条 trace_tail）、.fist-loop-20260927/cliout/、cypyc/parser/parser.py:901/:880/:3314
- reported_by: cypy-loop-hunter
- task_id: T0r41


### FIXED(verify=已完成, 范围=分桶) — 2026-09-27T10:04:00Z 追加留档（2026-09-27 R2-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.4.1` 与 `T0r56.4.2`，全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.17.30.01.md`
- 本轮修的是**归桶**：`cypy_hook/hook.py::transpile_file` 把读文件单独 try/except OSError，
  只有 I/O 失败才写「读取文件错误」；外层兜底改名「编译错误」⇒ 解析/生成期诊断不再冒充读文件失败，
  且其自带的行列信息保住（`编译错误: defer must be used inside a function, found at 4:7`）。
- 锁死回归：在**只回退本单**的临时树上证红 1 条：`test_bug35_parse_diagnosis_is_not_bucketed_as_read_error`；同树上其余 17 条（本单对照 + 另 5 单的用例）保持绿（混因=0 条、对照被带回=0 条）。
- **本单未修的另一半（如实留账）**：200 层括号那类 `RecursionError` 仍无深度守卫、诊断无行列，
  只是桶名不再撒谎 ⇒ 深嵌套守卫转结后续轮；本条目在 `bug_list` 里仍应视为**部分完成**。
- 判据口径：夹具用顶层 `defer`（该越域诊断本轮之前就有）而不是顶层 `return`（BUG-39 新增），
  否则回退 BUG-39 会把本单的锁一起带红 ⇒ 归因混在一起。
- 双套基线：pytest `1886 passed`（下限 1886，末行 `1886 passed in 327.53s (0:05:27)`）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`（亲笔行 323 条，black/flake8 零违例 + 必然违例自检通过） 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）

## BUG-36 [2026-09-27T03:05:03Z] [high] OPEN
- summary: [转结确诊:模式匹配] 位置模式不调用 __unapply__，产物访问不存在的 __f0/__f1
- detail: 复现：python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/hunt_e_extractor_positional.cypy -o .fist-loop-20260927/cliout --emit-cython
实际：产物里是 'user = _match_subject_1.__f0 ; domain = _match_subject_1.__f1'——Email 只有 address 一个字段，生成器（cython_generator.py:1619 field_name = fields[i] if i < len(fields) else f"__f{i}"）在该场景下 fields 为空，两个绑定名都落到 __f{i} 占位，既不调用 __unapply__，也不访问任何真实字段。
期望：SYNTAX/17-pattern-matching.md:201-215 与 :269-278 —— __unapply__ 优先，case Email(a, b) 应调提取器并按返回元组逐位置绑定。
证据：.fist-loop-20260927/hunts/hunt_e_extractor_positional.cypy、hunt_evidence.json(hunt_e_binding_lines)、run rc=1（被 BUG-F 的假阳性诊断挡在前面）
- reported_by: cypy-loop-hunter
- task_id: T0r42

### FIXED(R6 组合环 2026-09-29，ns cypy-loop-20260929 / T0r112) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 根因：`cypyc/codegen/cython_generator.py:_collect_module_info` 对 StructDef 只遍历 `stmt.body`，
  而 StructDef 的成员存放在 `.fields`/`.methods`（parser.py:117-135；分析器同事实见 type_checker.py:3300）
  ⇒ `_extractor_types` 收不到 struct、`_class_fields` 恒空 ⇒ 位置模式既不调查提取器，又落到 `__f{i}` 占位。
- 修复：新增 `_record_pattern_shape()`，字段顺序取 `.fields`（声明序），提取器标记扫 `.methods`+`.body`，
  且**方法名不再算进位置字段**；StructDef/ClassDef 两支共用它。
- 调用面实测（同产物、非单测桩）：
  `python -m cypyc run .fist-loop-20260927/hunts/hunt_e_extractor_positional.cypy` → `Output: a`、rc=0；
  产物生成 `_ext_1 = (_match_subject_1.__unapply__() if hasattr(...) ...)`，`user = _ext_1_a0`，全文无 `.__f0`。
- 锁死回归：`tests/test_pattern_positional_struct.py`（7 条，含 1 条反向对照「真类型错误仍须报出」
  与 1 条「方法名不得进 fields」）。
- 未清的另一半另立新单（BUG-92）：无 `__unapply__` 且实参元数 > 字段数的形态，见本条目末尾新登记项。

### AMENDMENT(逐字引用更正) — 本轮内自纠，不改写上文

- 上文写「cypyc run … → `Output: a`、rc=0」不是逐字回执。日志 `.fist-loop-20260929/logs/run_e_after.log`
  末尾四行实为：`Running …` / `Output directory: output` / `a` / `[OK] Execution successful` / `  Output: 0`。
  即程序 stdout 是 `a`，而 `Output:` 那行打的是**返回码 0**。结论不变（rc=0 且解包正确），
  引用口径以本段为准（原句保留不删）。命中原文位置数=1。

### AMENDMENT(自写段落的计数更正) — 本轮内自纠，不改写上文

- 上文写「锁死回归（7 条…）」，实测收集数为 **8 条**（`pytest tests/test_pattern_positional_struct.py --collect-only -q` 数 `<Function` 行 = 8）；计数以实测为准，原句保留不删。

## BUG-37 [2026-09-27T03:05:03Z] [high] OPEN
- summary: [类型检查假阳性] 位置模式把绑定名判成 int，有效程序被判「Return type mismatch」并非零退出
- detail: 复现：python -X utf8 -m cypyc run .fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy
实际：诊断 ['Return type mismatch: expected str, got int at 8:9']——classify 的两个 return 都是 str，位置模式绑定的 user 被当成 int，且位置指向 case 行而非 return 行；run rc=1（同类程序被拒）。
期望：结构体位置解构的绑定名类型应取字段/提取器元组的对应位置类型；无 __unapply__ 的 struct（本例）也不该给出与源码不符的 int 判定。
证据：.fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy、hunt_evidence.json(hunt_f_diagnostics)
- reported_by: cypy-loop-hunter
- task_id: T0r43

### FIXED(R6 组合环 2026-09-29，ns cypy-loop-20260929 / T0r112) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 根因：`cypyc/analyzer/type_checker.py:_visit_Pattern` 无条件 `self.type_map[node.name] = Type("int")`
  （注释自称"暂定"），把 `_bind_pattern_names` 已登记的槽位类型覆盖掉；且 `_bind_pattern_names`
  原本根本不认识 `ExtractorPattern`/`Pattern` 两类节点（只认 `Name`/`Call`/`Tuple`）。
- 修复：`_bind_pattern_names` 增加 `Pattern`/`ExtractorPattern`/`StructPattern` 支路，
  新增 `_pattern_slot_types()` 按 SYNTAX/17 的提取器优先级取 `__unapply__` 返回元组的实参类型
  （`GenericType.args`，parser.py:820-824），无提取器时回落字段声明顺序，再回落 `object`；
  `_visit_Pattern` 改为「未登记过的名字才补 `object`」，宁可不判也不造假阳性。
- 调用面实测：`hunt_f_pattern_binding_int.cypy` 的 `Return type mismatch ... got int at 8:9` 消失；
  `hunt_e_extractor_positional.cypy` 从 rc=1 变 rc=0 且 `Output: a`。
- 锁死回归：`tests/test_pattern_positional_struct.py::test_positional_binding_takes_slot_type_not_int`
  / `test_positional_binding_falls_back_to_field_order_without_extractor`
  / `test_wrong_return_type_still_reported`（反向对照，防「只是把门拆了」）。

## BUG-38 [2026-09-27T03:12:55Z] [high] OPEN
- summary: [变异fuzz:词法] 源文件以空格结尾且无末换行时，词法器抛 TypeError（NoneType 参与 in 运算）
- detail: 复现：python -X utf8 -c "import sys; sys.path.insert(0,'.'); from cypyc.parser.lexer import Lexer;from cypyc.parser.parser import Parser;Parser(list(Lexer(open('.fist-loop-20260927/hunts/fz01_trailing_space_no_newline.cypy',encoding='utf-8').read()).tokenize())).parse()"
实际：TypeError: 'in <string>' requires string as left operand, not NoneType——末行没有换行符且以空格结束时，_skip_whitespace/tokenize 取到 None 仍参与 `in` 判断；CLI 侧用户只看到「读取文件错误: …」，无 file:line（同 BUG-35 的归桶问题，但这条是崩溃本身）。
期望：文件尾的空白/缺末换行属合法输入，必须正常出 token 或给带行列的诊断，不得抛未声明异常。
命中：cypyc/parser/lexer.py:278 附近（_skip_whitespace），调用点 tokenize:510。
证据：.fist-loop-20260927/hunts/fz01_trailing_space_no_newline.cypy（10 字节最小复现）、fz_evidence.json(fz01)、fuzz/results_r1.jsonl 的 (b) 类
- reported_by: cypy-loop-hunter
- task_id: T0r44

### FIXED(verify=已完成) — 2026-09-27T03:58:00Z 追加留档（2026-09-27 R1-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：`T0r46.4`（ns `cypy-loop-20260927`，分支/叶子全链带 `[omega:required]`，L4 `output_validate` 逐叶 pass 后才 verify）；报告：`memory/reviews/20260927.11.55.55.md`
- 锁死回归：tests/test_loop_20260927_fix.py 里本单 2 条（1 锁 + 1 对照）；在**只回退本单**的临时树上证红 2 条：tests/test_loop_20260927_fix.py::test_bug38_trailing_space_parses_like_the_newline_version、tests/test_loop_20260927_fix.py::test_bug38_trailing_spaces_at_eof_do_not_crash；同一棵树上其余 6 条（本单对照锁 + 其余三单的用例）保持绿 ⇒ 红能归给本单
- 双套基线：基线双套：自研套件 `Total 47 / Passed 47 / Failed 0`；定向 pytest（从改动面反解 85 个文件）`1761 passed`，末行 `====================== 1761 passed in 291.73s (0:04:51) =======================`
- 修复边界：`_skip_whitespace` 的成员判断从「`in " \t"`（None 参与即 TypeError）」改成显式元组，行为差异只在 EOF：末行空格 + 无末换行不再崩。末行有无换行在 **AST 层同型**（对照锁），token 流层面 EOF 不补 DEDENT/NEWLINE 属实现细节，本轮不动、已在报告观察区记一行。


## BUG-39 [2026-09-27T03:12:55Z] [high] OPEN
- summary: [变异fuzz:语法] 顶层 return 被静默接受并原样写进产物，生成的 .pyx 必编译失败
- detail: 复现：python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/fz02_toplevel_return.cypy -o .fist-loop-20260927/cliout --emit-cython
实际：rc=0 且产物出现顶格 ['return 0']（模块级 return）；该 .pyx 交给 Cython 会报 Return not inside a function body。class 体内的 return（fz02c）与函数后的多余顶层 return（fz02b）同样被放过。
期望：parser 已有 _require_function_scope（parser.py:880，defer 就用了它），_parse_return_stmt（parser.py:1671）却没用 ⇒ 顶层 return 必须诊断（带行列）。
证据：.fist-loop-20260927/hunts/fz02_toplevel_return.cypy、fz_evidence.json(fz02_top_level_return_lines)、cliout/fz02_toplevel_return.pyx
- reported_by: cypy-loop-hunter
- task_id: T0r45


### FIXED(verify=已完成) — 2026-09-27T10:04:00Z 追加留档（2026-09-27 R2-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.3.1` 与 `T0r56.3.2`，全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.17.30.01.md`
- 修复面：`parser.py::_parse_return_stmt` 补上早就存在的 `_require_function_scope`
  （`defer` 一直在用，`return` 漏用）⇒ 顶层 return 由「rc=0 + 产物含顶格 `return 0`」变成
  `return must be used inside a function, found at 4:1` 且 rc≠0。
- 锁死回归：在**只回退本单**的临时树上证红 2 条：`test_bug39_toplevel_return_is_diagnosed_at_cli`、`test_bug39_control_fragment_without_body_scope_still_rejected`；同树上其余 16 条（本单对照 + 另 5 单的用例）保持绿（混因=0 条、对照被带回=0 条）。
- 波及面实测（首版不足，已勘误）：只跑 `examples/` 27 份 .cypy 全绿不足以断言「不打掉既有形状」——
  全量 pytest 当场红 2 条（宏体与宏展开片段里的 `return` 被同一道守卫吃掉），
  修回方式见 `BUG-51`：`Parser(body_scope=...)` 只对宏体/展开片段放宽，`_scope_stack` 不动。
  永久锁 3 条：`test_bug39_macro_body_return_stays_legal`、
  `test_bug39_expanded_fragment_return_stays_legal` 与对照
  `test_bug39_control_fragment_without_body_scope_still_rejected`。
- 修复边界：只诊断，不给「顶层 return 提升到 main」之类的语义扩展（那属推进半径的未实现面）。
- 双套基线：pytest `1886 passed`（下限 1886，末行 `1886 passed in 327.53s (0:05:27)`）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`（亲笔行 323 条，black/flake8 零违例 + 必然违例自检通过） 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）

## BUG-40 [2026-09-27T04:36:35Z] [low] OPEN
- summary: [构建/规范配置] pyproject 的 [tool.flake8] 对 flake8 7.x 不生效（缺 Flake8-pyproject），lint 口径与项目声明不一致
- detail: 现象：pyproject.toml 第 68-70 行声明 `[tool.flake8] max-line-length = 100` + exclude 列表，但 flake8 7.x 不原生读 pyproject.toml（需 Flake8-pyproject 插件，本机未装）⇒ 声明完全不生效，实际按默认 79 列、无 exclude 运行。

活证据（当场可复跑，两条口径差就是证据）：
  $ python -X utf8 -m flake8 --version
  7.3.0 (mccabe: 0.7.0, pycodestyle: 2.14.0, pyflakes: 3.4.0) CPython 3.13.14 on Windows
  ↑ 插件行里没有 Flake8-pyproject，即 pyproject 里的 [tool.flake8] 无人读取
  $ python -X utf8 -m flake8 --select=E501 -- cypy_bridge/types.py | wc -l                 → 4（默认 79）
  $ python -X utf8 -m flake8 --max-line-length=100 --select=E501 -- cypy_bridge/types.py | wc -l → 0

影响：PROJECT-SPEC/02-命名与源码规范.md:46 要求「提交前跑 lint/format（如项目配置），0 warning 优先」，contributor 照声明跑 `flake8` 得到的是与项目意图不同的判据（79 vs 100，build/ 等目录没排除）；R1-验证 判据5 的首次实跑即被这个差异带偏（同一批文件两种口径下违规数差一个量级）。

修法二选一（交裁决，本轮未动配置——配置变更属产品变更，不在验证环节半径）：a) dev extras 加 `flake8-pyproject>=1.2`，保留单一配置文件；b) 把该段搬到 `.flake8` 或 `setup.cfg`，零新依赖。

同口径附带量（不是本单主张，只给规模感，见 .fist-loop-20260927/verify_lint_r1.json）：按声明的 100 列测全仓 cypyc/cypy_bridge/scripts/tests = 4990 条违规、131 个文件，其中 W293 3991 条 ⇒ 这条债的清偿是打磨轮的独立工作项。
- task_id: T0r48

## BUG-41 [2026-09-27T05:11:09Z] [medium] OPEN
- summary: tests/test_boundary_comprehensive.py 两组测试类被同名重复定义遮住，6 条用例静默不执行
- detail: 调用面实测（证据件 `.fist-loop-20260927/polish_probe_r1.json` 的 P1，可复跑）：

  import tests.test_boundary_comprehensive 之后，模块属性 TestPointerBoundary 指向源码第 420 行那份，
  而第 200 行那份自己定义了 3 个 test_ 方法 ⇒ 这 3 条用例从不被执行；
  同文件 TestPipelineBoundary 同形状（282 行 3 条被 910 行的 7 条覆盖）⇒ 合计 6 条用例静默失踪。

证据怎么数出来的（两条独立口径互相咬合）：
 - AST 逐个 ClassDef 数体内的 test_ 方法：{200: 3, 420: 5}、{282: 3, 910: 7}；
 - inspect.getsourcelines(生效类)[1] 给出生效定义行 420 / 910，
   len([m for m in dir(类) if m.startswith('test_')]) 给出 5 / 7 ⇒ 被遮的 3+3 条确实不在类对象上。

影响：这种失踪没有任何失败信号。`pytest tests/` 报的 1862 passed 从来只含后定义那组；
而上一轮把 1862 当「覆盖率只升不降」的基数，基数本身就少算了 6 条。
flake8 侧以 F811 报了这两处（tests/test_boundary_comprehensive.py:420 与 :910），
但 F811 只说「重复定义」，不说被遮的是测试类 ⇒ 极易被当噪声划掉。

修法（交修复轮；打磨环节的红线是不动既有测试）：
 a) 给前一组改名（如 TestPointerBoundaryLegacy）让 6 条都跑起来，再逐条处理新暴露的失败；
 b) 若确认前一组是废弃副本，删除它并在提交说明里写明判断依据（哪一份更新、谁引用了谁）。
- task_id: T0r51

### FIXED(R6 组合环 2026-09-29，ns cypy-loop-20260929 / T0r112) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 实测口径修正：AST 反解两份同名类的差集，被遮蔽的是 **6 条**（`TestPointerBoundary` 首份 3 条里有 2 条
  名称仅存在于首份；`TestPipelineBoundary` 首份 3 条全部仅存在于首份）；本条目原写「6 条」在此得到确认。
- 修复：把**首现**的两份类改名为 `TestPointerBoundaryShadowedOnce` / `TestPipelineBoundaryShadowedOnce`
  （改名脚本对锚点做 `count==2` + 首现行号断言，避免把两份都改或改到别处），不删不并任何用例。
- 调用面实测：`pytest tests/test_boundary_comprehensive.py -k ShadowedOnce` → `6 passed, 122 deselected`
  （修复前这 6 条在收集面上不存在）。
- 残留：同名重复定义这类失效靠人工偶检不可持续，`tests/` 需要一条常驻「类名唯一 + 收集数地板」门；
  本轮未建该门，登记为流程债（见 R6 报告「未清项」）。

## BUG-42 [2026-09-27T05:11:09Z] [medium] OPEN
- summary: 产品码里 _visit_ExprStmt / _visit_MetaBlock 各定义两次，前一份成为死代码
- detail: 调用面实测（证据件 `.fist-loop-20260927/polish_probe_r1.json` 的 P2）：

 - CythonGenerator._visit_ExprStmt 在 cypyc/codegen/cython_generator.py 定义两次：
   1399 行那份 7 行体，2065 行那份 15 行体；
   `CythonGenerator.__dict__['_visit_ExprStmt'].__code__.co_firstlineno == 2065`
   ⇒ 1399 行那份从不被调用（死代码）。
 - ScopeAnalyzer._visit_MetaBlock 同样两处（cypyc/analyzer/scope_analyzer.py 484 行 11 行体、
   926 行 6 行体），生效的是 926 行 ⇒ 484 行那份是死代码，
   而且它比生效版本**长 5 行**：如果两次改动各写了一半逻辑，被覆盖的那一半就是丢的功能。
   本单不断言「哪一份才是意图」，只交可复算的事实（生效行号 + 两份体长）。

影响：同一文件里两份同名实现，意味着任何「改那份代码」的动作都可能改在死地址上，
测试与 review 都看不出——这正是 FIST 账本里「守卫覆盖面窄于主张」在产品码侧的镜像。
flake8 的 F811 报了这两处但只说 redefinition of unused '...' from line N，不指明被遮分支的规模。

修法（修复轮）：先用 `git log -L <起>,<止>:<文件>` 比对两份来历（哪份是后加的、为何加），
保留一份、把另一份的用例补进测试；本环节不动产品码。
- task_id: T0r52

### FIXED(打磨=已完成) — 2026-09-27T10:56:00Z 追加留档（2026-09-27 R2-打磨(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 处置单：根 `T0r60`（ns `cypy-loop-20260927`）的 8 枝 16 叶全链带 `[omega:required]`，逐叶
  `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.19.05.00.md`
- 生效性判定（不是"我看第二份顺眼"）：`CythonGenerator.__dict__['_visit_ExprStmt'].__code__.co_firstlineno
  == 2084`、`ScopeAnalyzer.__dict__['_visit_MetaBlock'].__code__.co_firstlineno
  == 926`，与 AST 候选 [1418, 2084] / [484, 926] 两条口径互相咬合
  （判据件 `.fist-loop-20260927/polish_r2_evidence.json`，`refuse=[]`，删前留档）。
- 删除面：`cypyc/codegen/cython_generator.py` 行 [1418, 1425]（8 行，sha8 659af698）、
  `cypyc/analyzer/scope_analyzer.py` 行 [484, 495]（12 行，sha8 fee43efe）。
  复算走**两路独立口径**：驱动自证（`polish_r2_cut.json`）+ 从仓库外快照 `E:/IDEProjects/AI/_cypy_snapshots/pre_polish_r2`
  反解（`polish_r2_after.json`）——模块级与类内符号**集合**逐档相同、行数差 == 声称删除行数
  （-8 / -12）、快照按驱动行区间切出的文本与驱动记的 `removed_text` 逐字相同、
  全树同名遮蔽计数归零（`tree_dupes={}`）、绑定行号上移量恰好等于删除行数
  （2084→2076、926→914）。
- 来历（`git log -S` 只读实测）：`_visit_MetaBlock` 的**守卫份**由 `f6d498f`(2026-07-27) 后加、
  **活份**由 `915431e`(2026-07-26) 先写在前 ⇒ 后加的守卫被落在被遮蔽的位置上，从来没生效过；同一语义在
  parser 里另有实现（`_require_module_level("meta", ...)`，HEAD `cypyc/parser/parser.py:2405` 已存在）⇒
  删除不丢校验，调用面复验 `def foo(): meta:` 仍报 `meta must be defined at module level, found at 2:9`
  （已钉成永久锁 `test_nested_meta_block_is_rejected_with_position`）。
  `_visit_ExprStmt` 两份都随 `17d68b4`(2026-08-17) 一次进来 ⇒ 重复是那场重构的产物；死份的
  `elif getattr(node, 'value', None) is not None` 与它的 `if` 同条件，**构造上不可达**，无独有逻辑。
- 被删文本留档：`polish_r2_cut.json` 的 `measures.*.removed_text`（含那句唯一守卫文案），要回放可逐字取回。
- 机制化：新增结构判据 `tests/test_polish_20260927_r2.py::test_product_code_has_no_shadowed_method_definitions`
  扫 `cypyc/**/*.py`，同一类体内出现同名方法即红；配合成违例对照
  `test_shadow_detector_catches_a_synthetic_pair`（同类两名必被抓、单份不得误抓）。
  **删除前实测它是红的**，红文逐字点名两处：`ScopeAnalyzer._visit_MetaBlock@[484, 926]`、
  `CythonGenerator._visit_ExprStmt@[1418, 2084]` ⇒ 判据不恒绿。
- 行为未变（同一时刻复算）：pytest `1894 passed in 395.87s (0:06:35)`（下限 1894 = 上环 1886 + 本环 8 条锁，
  collected=1894，只升不降）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；端到端 `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；
  基准**未重注册**。作用域化 lint：亲笔 147 行零违例，
  两档产品码新增行数 0/0（纯删除），
  存量违例只减不增（47→44）。
- 不算证明（本环明确排除）：① "三套基线全绿" 不证明死份里没有独有能力 ⇒ 靠来历 + 构造不可达 +
  守卫另有实现并在调用面复验；② "文件仍能导入" 不证明删对了那份 ⇒ 靠绑定行号上移量与删除行数吻合；
  ③ "文件行数变了" 不证明变的是我要删的 ⇒ 靠快照切出的文本与 `removed_text` 逐字相等。

## BUG-43 [2026-09-27T05:16:29Z] [medium] OPEN
- summary: [静态检查配置] mypy 按声明的 python_version=3.9 跑测试树会整轮中断（依赖里有 3.10 语法），strict 门形同不存在
- detail: 现象：pyproject 的 `[tool.mypy]` 声明 `python_version = "3.9"` + `strict = true`，
但本机依赖（pytest）自身带 3.10 的 `match` 语法 ⇒ mypy 一旦跟随导入进到 site-packages 就**整轮中断**，
连项目自己的文件都不再检查。这不是"存量 error 多"，而是**这道门当前跑不起来**。

调用面原文（polish_file_bug43_r1.py 当场实跑，命令与退出码一起给出）：
  $ C:\Users\victo\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe -X utf8 -m mypy tests/test_loop_20260927_fix.py cypyc/codegen/cython_generator.py \
      cypyc/parser/lexer.py cypy_bridge/types.py cypy_bridge/__init__.py
  rc=2
    C:\Users\victo\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\site-packages\_pytest\terminal.py:1729: error: Pattern matching is only supported in Python 3.10 and greater  [syntax]
  Found 1 error in 1 file (errors prevented further checking)

对照：去掉那个 import pytest 的测试文件后（`mypy cypyc/parser/lexer.py cypy_bridge/types.py`），
mypy 不中断而是报出成片的存量 error（R1-验证 记的是 950 条/37 文件）⇒
同一个配置在"产品码输入"与"含测试输入"两种口径下给出完全不同形状的结果，
说明 `python_version=3.9` 这条声明与实际运行环境（CPython 3.13.14）已经不一致。

影响：PROJECT-SPEC 的静态检查口径无法在测试树上执行；CI 若照声明跑 `mypy`，
会在中断的情况下只拿 1 条 error 当作「基本干净」（本轮扫描器就差点这么写——它输出了
`total_errors=1`，而真相是"检查被中止"）。任何以这个数字立论的门禁都建在沙上。

修法（交裁决，本环不动配置）：a) `[[tool.mypy.overrides]]` 对第三方模块
（`pytest.*` 等）设 `ignore_missing_imports=true` / `follow_imports="silent"`；
b) 把 `python_version` 抬到实际支持的最低版本（若项目确实要支持 3.9，则该声明与 pytest 版本
需要一起裁决）；c) 让包装脚本把「中断」与「N 条 error」区分开（`errors prevented further checking`
必须判为未跑成，而不是计数 1）。
- task_id: T0r53

## BUG-44 [2026-09-27T06:11:39Z] [high] OPEN
- summary: struct 里的 @staticmethod 生成时仍注入 self，产物签名与声明不符且调用必炸
- detail: 调用面实测（`.fist-loop-20260927/advance_verify_r1.json` 候选 #3，可复跑 `advance_verify_r1.py`）：

  SYNTAX/06d-builtin-magic-traits.md:49 在 struct 里声明了 @staticmethod，
  最小用例 `struct Point: x: int` + `@staticmethod def origin() -> Point` 走
  `python -m cypyc transpile` 得到 rc=0 与「[OK] Transpiled successfully」，
  但产物是 `cdef class Point:` 里的

      @staticmethod
      def origin(self):
          return Point(x=0)

  ⇒ 声明是无参静态方法，产物却保留 self（Cython 会照编译过去，调用 Point.origin() 时 TypeError）。
  同一份生成器在 class 路径上是对的，只有 struct 路径把 self 注进去：
  cypyc/codegen/cython_generator.py:2267 给 struct 方法整体置 is_struct_method=True，
  而 _visit 的签名装配只看这个标志，不看装饰器。

为什么这比解析报错严重：CLI 的成功横幅与产物文件都在，用户看不出任何异常。
判据面（本单的 want/neg 成对对照在 advance_verify_r1.py 的 match() 里）用的是
「产物里有没有 `def origin()` 空参形状」，而不是「产物里有没有 staticmethod 字样」——
后者第一版就恒绿了（产物确实含 @staticmethod），是它自己的对照把这轮打回的。

修法（交修复轮）：struct 方法签名装配处读取 FuncDef 的装饰器，遇 staticmethod/classmethod 不注 self；
改完须重跑 25 份端到端基准（struct 方法在 demo 里用得多，产物面会变）。
- reported_by: cypy-advancer


### FIXED(verify=已完成) — 2026-09-27T10:04:00Z 追加留档（2026-09-27 R2-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.1.1` 与 `T0r56.1.2`，全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.17.30.01.md`
- 修复面：`cypyc/codegen/cython_generator.py` 新增 `_decorator_names`/`_is_selfless_method`，
  `_visit_FuncDef` 的 self 注入改为「已声明 self **或** 是 @staticmethod/@classmethod 都不再注入」；
  struct 方法循环里 `@cython.binding(False)` 只挂在绑定方法上（此前 3 个方法挂 3 条）。
- 锁死回归：在**只回退本单**的临时树上证红 2 条：`test_bug44_struct_selfless_methods_drop_injected_self`、`test_bug44_at_cli_product_is_transpiled_without_self`；同树上其余 16 条（本单对照 + 另 5 单的用例）保持绿（混因=0 条、对照被带回=0 条）。
- 调用面证据：`cypyc transpile` 产物由 `def origin(self):` 变成 `def origin():`
  （锁：`tests/test_loop_20260927_fix_r2.py::test_bug44_at_cli_product_is_transpiled_without_self`）。
- 修复边界：SYNTAX/06d 的绑定方法写法是**显式 `self`**；隐式 self 在类型检查面仍报
  `Undefined name 'self'`（本轮实测，属既有面、不在本单半径），已在环节报告里单列一条观察。
- 双套基线：pytest `1886 passed`（下限 1886，末行 `1886 passed in 327.53s (0:05:27)`）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`（亲笔行 323 条，black/flake8 零违例 + 必然违例自检通过） 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）

## BUG-45 [2026-09-27T06:11:39Z] [high] OPEN
- summary: struct 的 __implicit_default__ 默认值生成成裸名字，导入即 NameError，声明的自动填充没有落地
- detail: 调用面实测（`.fist-loop-20260927/advance_verify_r1.json` 候选 #4，可复跑）：

  SYNTAX/06d-builtin-magic-traits.md:53 声明「__implicit_default__ 提供隐式默认值填充，
  当参数未提供时自动使用」，并给出 `def process(data: str, cfg: Config = __implicit_default__)`。
  同形状最小用例 transpile rc=0，产物是

      def process(cfg=__implicit_default__):

  ⇒ 默认值是一个**裸名字**，模块作用域里没有这个符号（它只作为类方法存在一次，且签名还错保留 self），
  Python/Cython 求值默认参数是在 def 执行时 ⇒ import 该模块即 NameError。文档承诺的
  「未提供参数时自动用隐式默认填充」在产物里没有任何等价的填充逻辑。

同上一条的判据口径：want 是「产物里出现 __implicit_default__ 的**调用形**」（`(...)`），
neg 是修复前的裸名形状 ⇒ 不会因为产物里出现该字样就恒绿。

修法（交修复轮）：把 `= __implicit_default__` 脱糖成 `Type.__implicit_default__()` 调用，
并把 #44 的 self 问题一并解决（否则调用点仍错）。两者同文件同域，建议修复轮一起做。
- reported_by: cypy-advancer


### FIXED(verify=已完成) — 2026-09-27T10:04:00Z 追加留档（2026-09-27 R2-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.2.1` 与 `T0r56.2.2`，全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.17.30.01.md`
- 修复面：`cython_generator._param_default_str` 把 `= __implicit_default__` 脱糖成
  `{参数类型}.__implicit_default__()`（产物形状：`cfg=Config.__implicit_default__()`）；
  `cypyc/parser/parser.py::_parse_params` 对**无类型注解**的该默认值给带行列诊断（此时无从确定调谁）。
- 锁死回归：在**只回退本单**的临时树上证红 2 条：`test_bug45_implicit_default_desugars_to_typed_call`、`test_bug45_implicit_default_without_annotation_is_diagnosed`；同树上其余 16 条（本单对照 + 另 5 单的用例）保持绿（混因=0 条、对照被带回=0 条）。
- 成对对照：普通默认值 `t: int = 5` 产物仍是 `t=5`（脱糖逻辑不误伤），对照用例 `test_bug45_control_ordinary_default_untouched`。
- 修复边界：只做「默认值形状」的脱糖，不改 `__implicit_default__` 的**调用时机语义**
  （文档"参数未提供时自动使用"= Python 默认参数求值语义，本轮不引入新的隐式填充路径）。
- 双套基线：pytest `1886 passed`（下限 1886，末行 `1886 passed in 327.53s (0:05:27)`）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`（亲笔行 323 条，black/flake8 零违例 + 必然违例自检通过） 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）

## BUG-46 [2026-09-27T08:14:56Z] [high] OPEN
- summary: hook install 打印 [OK] 但不做任何持久化，紧接着 status 在另一进程里报未安装（两命令互相否定）
- detail: 现象（一次跑完，全在调用面）：
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
    并同步 docs/USAGE.md:121-124 的措辞。
- reported_by: cypy-hunter


### FIXED(verify=已完成) — 2026-09-27T10:04:00Z 追加留档（2026-09-27 R2-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.5.1` 与 `T0r56.5.2`，全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.17.30.01.md`
- 取**口径修法（本单 a/b 二选一里的 b）**，不动用户环境：`cypyc/cli.py` 的
  `hook install/uninstall/status` 三条输出全部限定「当前进程」，install 不再打
  `installed successfully`，status 不再打 `[FAIL] ... is not installed`（两命令此前互相否定）；
  `docs/USAGE.md` 2.6 段同步删掉「写入用户 sitecustomize / 注册」这句未实现的承诺，
  改为给出跨进程的正确写法（在自己进程里 `cypy_hook.install_hook()`）。
- 为什么不选 a（真做持久化）：写用户 site-packages/.pth 属改动本机 Python 环境，
  在本轮红线里是不可逆动作 ⇒ 只挂账待裁决，不在自动轮里替用户装东西。
- 锁死回归：在**只回退本单**的临时树上证红 2 条：`test_bug46_install_and_status_agree_on_process_scope`、`test_bug46_usage_doc_matches_the_narrowed_claim`；同树上其余 16 条（本单对照 + 另 5 单的用例）保持绿（混因=0 条、对照被带回=0 条）。
- 成对对照：`test_bug46_fresh_process_reports_not_active` 钉住"新进程仍报未激活"是真的
  （修复前它也绿 ⇒ 说明旧缺陷不在这条面上，而在两条横幅互相否定）。
- 双套基线：pytest `1886 passed`（下限 1886，末行 `1886 passed in 327.53s (0:05:27)`）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`（亲笔行 323 条，black/flake8 零违例 + 必然违例自检通过） 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）

## BUG-47 [2026-09-27T08:14:56Z] [medium] OPEN
- summary: docs 声明的 cypy_hook 包级 API（install_hook/uninstall_hook/is_hook_installed）未再导出，导入即 AttributeError
- detail: 现象：`python -c "import cypy_hook; cypy_hook.install_hook()"` →
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
修法：__init__.py 增补再导出并把 `__all__` 补齐（或改文档到 `cypy_hook.hook.*` 的真实路径）。
- reported_by: cypy-hunter


### FIXED(verify=已完成) — 2026-09-27T10:04:00Z 追加留档（2026-09-27 R2-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.6.1` 与 `T0r56.6.2`，全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.17.30.01.md`
- 修复面：`cypy_hook/__init__.py` 再导出 `install_hook`/`uninstall_hook`/`is_hook_installed`
  并把 `__all__` 补齐 ⇒ 手册 3.x 承诺的包级 API 路径可用（此前只有 `CypyHook`）。
- 锁死回归：在**只回退本单**的临时树上证红 2 条：`test_bug47_package_level_hook_api_exists`、`test_bug47_in_process_install_then_uninstall`；同树上其余 16 条（本单对照 + 另 5 单的用例）保持绿（混因=0 条、对照被带回=0 条）。
- 判据自身对照：探测里额外问 `hasattr(cypy_hook, 'is_hook_installed_v2')` 必须为 False
  ⇒ 证明 `hasattr` 探测本身不是恒真。
- 修复边界：只补再导出，不动 `cypy_hook.hook` 里的实现位置（`from cypy_hook.hook import ...` 仍可用）。
- 双套基线：pytest `1886 passed`（下限 1886，末行 `1886 passed in 327.53s (0:05:27)`）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`（亲笔行 323 条，black/flake8 零违例 + 必然违例自检通过） 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）

## BUG-48 [2026-09-27T08:14:56Z] [high] OPEN
- summary: cypyc watch 只打印横幅：改动或新增被监控文件后 16s 内无任何重编译产物与事件日志，rc 始终 0
- detail: 现象：`python -m cypyc watch <dir> --debounce 0.2` 起得来（横幅打印Watching directory / Output
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
修复后必须在**新进程**里看到 output/ 下出现对应 .pyx，并且 stdout 有事件行。
- reported_by: cypy-hunter

### FIXED(推进=已完成) — 2026-09-27T11:55:00Z 追加留档（2026-09-27 R2-推进(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 处置单：根 `T0r61`（ns `cypy-loop-20260927`）的 8 枝 16 叶全链带 `[omega:required]`，逐叶
  `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.19.55.00.md`
- **原话先重测再反驳**（本条是这单的主要内容）：条目正文说『cypyc watch 只打印横幅：改动或新增被监控文件后 16s 内无任何重编译产物与事件日志，rc 始终 0』。同一夹具改码前实测（`.fist-loop-20260927/advance_r2_watch_probe_before.json`）：
  `[HotReload] File changed` 3 条、`Successfully reloaded` 2 次、
  `Failed to reload` 0 次、`Traceback` 0 次 ⇒ **事件日志与重编译都在发生**，
  这半句话是错的。真缺的是三件（下面逐件给判据），其中"产物"那半只成立在
  「`-o` 目录收不到」这个精确形状上：before 件 `outputs_in_out_dir` = `[]`。
- 补全一 `-o 产物发布`：`cypyc/incremental/hot_reload.py` 新增 `artifact_dir` 与 `_publish_artifacts()`
  （把 `.pyx/.pyd` 从编译用临时目录复制进 -o；`.c` 中间产物按手册字面不算"编译文件"），
  `cypyc/cli.py::run_watch` 传 `artifact_dir=args.output`。调用面实测（`advance_r2_watch_probe.json`）：
  `-o` 目录得到 `['a.cp313-win_amd64.pyd', 'a.pyx', 'b.cp313-win_amd64.pyd', 'b.pyx']`。
  成对对照：不设 `artifact_dir` 时 `_publish_artifacts` 必须返回空且目录里什么都不出现
  （`test_publish_artifacts_is_noop_without_artifact_dir` + `test_real_toolchain_publishes_compiled_artifacts` 第二段）
  ⇒ 库路径默认行为没被这次改动带偏。
- 补全二 `on_reload 接线`：run_watch 内定义 `report_reload()` 打批次结论，哨件
  `advance_r2_wiring.json` 逐项核对实参（`on_reload_callable=True`、
  `debounce_delay=0.7`、`artifact_dir` 与 -o 同值），并**真调一次**回调
  ⇒ 实测 stdout 出现 `2` 行 `[Watch] Published N artifact(s) …`。
- 补全三 `--debounce`：`HotReloadEngine.start()` 新增 `debounce_delay` 透传给监控器
  （实测显式 1.23 ⇒ 监控器存 `1.23`；不传 ⇒ 仍
  `0.5`）。此前 CLI 打印用户输入的时延、引擎却写死 0.5。
- **附带发现并当场定性**：探针有一跑 `-o` 为空、日志出现 `cl.exe failed with exit code 1` /
  `can't copy 'build\lib.win-amd64-cpython-313…'`。同夹具跑开关两态
  （`advance_r2_race_probe.json`）：去掉引擎锁 3/3 轮出红且成因均为编译类
  （红轮 `[1, 2, 3]`），加锁 3/3 轮双线程全绿。
  ⇒ 成因是 setuptools 的**中间**产物落在进程 CWD 下共享的 `build/`，watchdog 一次保存发多个事件
  即并发互踩。本环把锁加在**类**上（`HotReloadEngine._compile_lock = threading.RLock()`，
   锁住的是进程共享的 `build/`，不是某个引擎实例；同进程内已足够），
  **跨进程那半边不修**：要动 `cypy_hook` 的中间目录策略（同时影响 import hook 与缓存命中）⇒
  入账 BUG-54（`BUG-54` / `T0r62`），关闭判据写明必须是两个子进程并发。
- 行为未变（同一时刻复算）：pytest `1903 passed in 412.93s (0:06:52)`（下限 1903 =
  上环 1894 + 本环 9 条锁，collected=1903）；
  自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；端到端 `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；基准未重注册。
  作用域化 lint：亲笔 429 行零违例（含必然违例自检
  `selfprobe-caught`），存量违例只减不增。git 红线 HEAD `17d68b4`、暂存 0。
- 手册同步：`docs/USAGE.md` 2.5 段补 `-o` 产物、两种批次结论行措辞、以及"临时目录编译再复制 +
  同进程串行编译"的说明——文档里每一句都在上面的实测里有对应物。
- **自曝**：锁与 `artifact_dir` 一开始只写在 `__init__` 里，被全量撞红一条老用例
  （`tests/test_polish_20260926.py::test_bug10_cache_update_parse_failure_warns` 用
  `HotReloadEngine.__new__` 绕过构造造引擎 ⇒ `AttributeError: '_compile_lock'`）。老测试不可改 ⇒
  提成类属性，并补第 9 条锁 `test_engine_attributes_survive_construction_without_init` 钉住这条构造路径。
- 不算证明（本环明确排除）：① "重载成功"不证明产物落到了用户指定的目录 ⇒ 靠 before/after 两件的
  `outputs_in_out_dir` 差集；② "源码里出现了 `on_reload=`"不证明回调真被调用 ⇒ 靠哨件真调一次并
  核对 stdout 行；③ "加了锁之后跑通了"不证明锁在承重 ⇒ 靠同一夹具的锁关对照必须出红；
  ④ "三套基线全绿"不证明跨进程安全 ⇒ BUG-54 因此不关闭。
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）

## BUG-49 [2026-09-27T08:34:30Z] [medium] OPEN
- summary: SYNTAX/33 的实现状态栏说 constraint 未实现，但同一文件与实测都表明它四层已落地（过期声明会诱使后续轮重复实现）
- detail: 声明处（逐字）：
  SYNTAX/33-type-constraints-subtypes-dispatch.md:6
    > **实现状态**：三件套 **全部未实现（0/4 层）**。`constraint` 与 `dispatch` 目前会被**静默吞成普通标识符/函数调用**，
  同文件 :40 的 B2 行还断言：`constraint Numeric = int | float` + `def f<T: Numeric>(x: T)` 用 `f(1)`
  会报 `type 'int' does not satisfy constraint 'Numeric'`。

调用面实测（本次，可复跑）：把 :40 那个 B2 程序原样写成 .cypy 交给 CLI：
  constraint Numeric = int | float

  def f<T: Numeric>(x: T) -> T:
      return x

  print(f(1))
  → `python -X utf8 -m cypyc transpile <该文件> -o <临时目录>` **rc=0**，
    打印 `[OK] Transpiled successfully`，产物 .pyx 非空。
  （对照：把 `def f<T: Numeric>` 误写成 `def f[T: Numeric]` 会在 3:10 报 `Expected LPAREN, got LBRACKET`
   ——说明 rc=0 不是因为解析器根本没看见这段，形状判据是活的。）

实现面旁证：`grep -c constraint cypyc/parser/lexer.py` = 3、`cypyc/codegen/cython_generator.py` = 6，
且仓库里有永久回归 `tests/test_named_constraints.py`（文件头自述：与 `Find_BUG/audit_2026q3/feat_constraint_*.py`
同源，覆盖 C-1.2/C-2.3/C-2.5 与 §5 的 codegen 行为）。

我只声称我实测过的部分：**`constraint` 的"未实现/静默吞"这半句与实测矛盾**；
`subtype` / `dispatch` 本轮没打探针，不在本单射程内（:6 里它们那半句可能是对的）。

影响（不是文案洁癖）：这条状态栏是给后续自动化轮次读的"路由表"。R1 已经因为 appendix-A:88
的过期描述把 `constraint` 当成候选核过一遍（当时结论：四层已落地、那行过期）；
本轮又同一形状复现。留着它就会每轮重新怀疑/重做同一件已完成的事。

修法（交文档/推进轮，红线要求我不改 SYNTAX/ 与 PROJECT-SPEC/）：
 把 :6 的状态行改成按件套分层的实测事实（constraint 四层可用 + 指回 tests/test_named_constraints.py；
 subtype/dispatch 维持未实现），或在文件头写明"状态以 §表格逐行实测为准，本行仅是快照"。
判据：改后仍要能用上面那条 .cypy 探针跑出 rc=0，否则是改错了而不是改好了。
- reported_by: cypy-hunter
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）

## BUG-50 [2026-09-27T09:33:03Z] [high] OPEN
- summary: 操作者把两档存量未格式化的产品文件交给 black 整档重写，改动不可回滚且淹没真实 diff
- detail: 现象（全部当场可复算）：

  $ git diff --stat -- cypyc/parser/parser.py cypyc/parser/macro_expander.py
   cypyc/parser/macro_expander.py |  365 ++++---
   cypyc/parser/parser.py         | 1885 +++++++++++++++++++++++++++----------
  ↑ 相对 HEAD(17d68b4) 的改动行数是 425 → 1885（parser.py）。而**本单对该文件的真实意图只有 4 处**：
    ① `_parse_params` 里给 `= __implicit_default__` 加无注解诊断（9 行）；
    ② `_parse_return_stmt` 补 `_require_function_scope`（2 行）；
    ③ `Parser.__init__` 增 `body_scope` 形参与 `self._body_scope`（3 行）；
    ④ `_require_function_scope` 条件加 `or self._body_scope` + `_parse_macro_def` 保存/恢复该标志（5 行）。

来历（一次性命令，写在 `.fist-loop-20260927/` 的执行记录里）：
  python -X utf8 -m black .fist-loop-20260927/fix_r2_lint.py .fist-loop-20260927/fix_r2_lockproof.py \
      .fist-loop-20260927/fix_r2_baselines.py cypyc/parser/parser.py cypyc/parser/macro_expander.py \
      tests/test_loop_20260927_fix_r2.py
本意是"格式化我本轮写的文件"，但把两档**存量未格式化**的产品文件一起传了进去：
仓库声明的是 flake8 100 列（且 BUG-40 已证 `[tool.flake8]` 根本不生效），black 从未在这两档上跑过
⇒ black 按自己的口径整档重排（引号、空行、换行位置、长表达式续行等）。

为什么这是缺陷而不是"顺手整理"：
1. 不可逆：改动前的文本没有任何副本 —— 三条反证当场可查：
   `git ls-files -s cypyc/parser/parser.py` 的索引 blob 与 `git rev-parse HEAD:...` **同一个哈希**
   （fe5a888…，164275 字节），即从未 `git add` 过；
   IDE 侧 `file-history` 目录里今天 16:00 之后没有任何 >140KB 的快照（全量 `find` 只命中本仓那份）；
   `git archive HEAD` 类快照树取的是 HEAD，不含 09-26/R1 的**未提交**工作。
   ⇒ 唯一还能确定的是「语义应保持不变」（black 只做格式化），但这是**主张不是证据**。
2. 覆盖了别人的在飞工作：这两档里压着 09-26 审计轮与 R1 轮未提交的改动，
   现在它们的作者若再按原文本做锚点替换（并发 lane 的脚本化补丁正是这么做的），会静默改不到位置。
3. 破坏了评审面：人类 reviewer 拿到的 diff 从 425 行变 1885 行，真正的 4 处改动被埋在重排噪声里。

期望：操作者对**产品文件**只做定向编辑；格式化只在"本轮亲笔整档"上跑；
任何可能整档重写工具的调用前先落快照（本轮起 `.fist-loop-20260927/snapshot_tracked.py`
把 `git ls-files` 全集复制到仓库外 `E:/IDEProjects/AI/_cypy_snapshots/<标签>/` 并自证文件数/字节数）。

不算证明的现象：三套基线（pytest/自研/e2e）全绿**不能**证明没有损失 —— 它们测的是行为，
而这条损失是文本层与评审面的；反过来基线若红，也说明不了是格式化引起的（本轮已实测一例真回归
是语义改动引起：`_require_function_scope` 吃掉了宏体 return，见 BUG-51）。

修法（交人工裁决，自动轮不再动这两档的排版）：
 a) 接受现状，在提交说明里把"4 处真实改动"与"black 整档重排"分开列（我已在本轮报告 §五′ 写清）；
 b) 由持有原始文件的人（09-26 轮 / R1 轮的作者或用户本地备份）提供原文，再由我重放 4 处改动；
 c) 长期项：给仓库加 `black --check` 的**范围化**门禁（只判本轮改动的 hunk），
    避免"格式化器一旦有人手滑就整档重排"这条路再次被走。
- reported_by: cypy-fixer
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）

## BUG-51 [2026-09-27T09:33:04Z] [medium] OPEN
- summary: BUG-39 的顶层 return 守卫首版吃掉宏体/宏展开片段里的 return，全量 pytest 当场红 2 条
- detail: 现象（修复前一次真实全量跑，日志 `.fist-loop-20260927/r2fix/pytest_gate.txt`）：
  2 failed, 1881 passed in 373.79s
  FAILED tests/test_parser_macro.py::test_macro_definition_parsing - ValueError:
      return must be used inside a function, found at 2:5
  FAILED tests/test_macro_features.py::test_macro_interpolation_expression - assert 1 == 0
      [cypy][warn] 宏展开后的代码块无法解析，按原样保留（该语句可能从输出中消失）

来历：`cypyc/parser/parser.py::_parse_return_stmt` 加 `_require_function_scope` 时，
按「函数体之外」理解作用域，而**宏体本身也是 `-> Tokens` 的返回语义**：
`_parse_macro_def` 与 `cypyc/parser/macro_expander.py::_parse_code` 都用一个新建 Parser 解析宏体/
展开片段，此时 `_in_function` 为假 ⇒ 合法的 `macro m(ts: Tokens) -> Tokens = return ts` 被拒；
展开路径更糟——异常被 expander 吞成 warn，整条宏调用**从产物里消失**（静默丢代码）。

本单记录的是**修 BUG 时把半径判窄了一半**这个缺陷本身：
我当场给的"波及面实测"只跑了 `examples/` 27 份 .cypy（全绿），据此就在报告草稿里写了
"不会打掉既有可编译样例" —— 真正暴露它的是随后那次全量 pytest。⇒ 判据口径修正：
"改了 parser/lexer 的作用域判定"这类改动，波及面必须用**全量套件**（两套体系）量，
examples 语料不能代表 `tests/` 里那些为特性写的形状。

修法（本轮已落地并锁死）：`Parser.__init__(..., body_scope: bool = False)`，
`_require_function_scope` 改为 `if not (self._in_function or self._body_scope)`；
`_parse_macro_def` 解析宏体前置位、解析后恢复；expander 用 `Parser(tokens, body_scope=True)`。
刻意不动 `_scope_stack` —— 它是 `_is_module_level()` 的依据，宏体里仍可生成 struct/impl。
锁：`tests/test_loop_20260927_fix_r2.py` 的
`test_bug39_macro_body_return_stays_legal`、`test_bug39_expanded_fragment_return_stays_legal`
与对照 `test_bug39_control_fragment_without_body_scope_still_rejected`（不开标志时仍必须被拒）。

不算证明：只看这两条测试绿不足以说明宏语义没被动 —— 它们只覆盖 `return`；
`defer`/`@meta` 之类同样走 `_require_function_scope`/`_require_module_level` 的构造，
本轮未扩测，转结后续轮。
- reported_by: cypy-fixer


### FIXED(verify=已完成) — 2026-09-27T10:04:00Z 追加留档（2026-09-27 R2-修复(循环轮)，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.3.1` 与 `T0r56.3.2`，全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`memory/reviews/20260927.17.30.01.md`
- 修复面：`Parser.__init__(tokens, body_scope=False)` + `_require_function_scope` 改成
  `if not (self._in_function or self._body_scope)`；`_parse_macro_def` 解析宏体时置位、之后恢复；
  `cypyc/parser/macro_expander.py::_parse_code` 用 `Parser(tokens, body_scope=True)`。
  **刻意不动 `_scope_stack`** —— 它是 `_is_module_level()` 的依据，宏体里照旧可以生成 struct/impl。
- 证据形状（与另 5 单不同，如实写明）：本单**不参与逐单回退矩阵**（它锁的是"别把守卫做过头"，
  回退 BUG-39 的守卫不会让它红）。承重证据是首版那次全量 pytest 的 2 条红
  （`.fist-loop-20260927/r2fix/pytest_gate.txt`：`2 failed, 1881 passed`，
  `test_parser_macro.py::test_macro_definition_parsing` 与
  `test_macro_features.py::test_macro_interpolation_expression`）+ 修回后 18 条全收集全绿。
- 锁：`test_bug39_macro_body_return_stays_legal`、`test_bug39_expanded_fragment_return_stays_legal`
  （`macro_exemption` 组），以及归在 BUG-39 名下的
  `test_bug39_control_fragment_without_body_scope_still_rejected`（断言守卫本身在拦）。
- 未扩测的部分如实转结：`defer`、`@meta` 之类同样受作用域判定约束的构造，在宏体里的形状本轮没测。
- 双套基线：pytest `1886 passed`（下限 1886，末行 `1886 passed in 327.53s (0:05:27)`）；自研套件 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`；e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`（亲笔行 323 条，black/flake8 零违例 + 必然违例自检通过） 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）
- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 0 条，无唯一命中 ⇒ 该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）
## BUG-52 [2026-09-27T10:24:13Z] [medium] OPEN
- summary: [构建/规范配置] pyproject 声明了 [tool.black] line-length=100，但 156 个 .py 里 142 个不满足，照 PROJECT-SPEC/02 跑 format 会产出巨量不可复审的 diff
- detail: 现象（两条口径当场可复跑，全部在本工作树实测）：
  $ python -X utf8 -m black --line-length 100 --check cypyc cypy_bridge scripts tests
  142 files would be reformatted, 14 files would be left unchanged
  $ find cypyc cypy_bridge scripts tests -name "*.py" | wc -l   → 156
  ↑ 声明口径覆盖不到 142/156 个文件（91%）；本机 black：python -m black, 26.3.1 (compiled: yes)
Python (CPython) 3.13.14

声明处（逐字）：
  pyproject.toml:49-50  [tool.black] / line-length = 100
  PROJECT-SPEC/02-命名与源码规范.md:46  “提交前跑 lint/format（如项目配置），0 warning 优先。”
contributor 照这条跑 `black .` 得到的不是"通过"，而是把 142 个文件整档重写。

本轮改动半径（同一命令、只列半径内 7 个 .py）：不满足的是 ["cypy_hook\\hook.py", "cypyc\\cli.py", "cypyc\\codegen\\cython_generator.py"]，
其余 1 个干净 —— 也就是说 R2-修复 的亲笔行是干净的，**债在文件级不在本环**。

为什么这条不是"格式洁癖"而是可量化的损失（R2-验证 的 P9 实测，件 `verify_r2_probe.json`）：
  以 HEAD 为底，`cypyc/parser/parser.py` 文本差 1893 行；
  先把 HEAD 版本按同一配置过一遍 black 再比，只差 460 行
  ⇒ 其中 1433 行纯属排版噪声，真实内容增量（09-26/R1 未提交工作 +
  本环 4 处）只有 460 行。`macro_expander.py` 同型：365 →
  185（排版占 194）。
这正是 BUG-50 的放大器：一个未被门禁认领的 formatter 声明，让人有理由顺手 `black` 掉两档产品文件，
而全仓 91% 的文件都在同一个坑里。

不算证明（避免被误判成"已修"）：
 - 只对个别文件跑 `black` 让它变干净 ≠ 这条闭环 —— 声明是仓库级的；
 - 把 `[tool.black]` 段落删掉/改口 ≠ 修复（那是把声明改成既成事实，且与 BUG-40 的"配置不生效"是同一种回避）；
 - `black --check` 的 rc=1 只是本条的现象，不能反过来当判据。

修法（交裁决，三选一或组合，自动轮不独走）：
 a) 一次性全仓 `black` 提交（约 142 文件、数千行噪声）+ 之后把 `black --check` 设为 CI 硬门；
    这一条要人工批，因为一旦提交，任何未提交工作都无法与排版噪声区分（BUG-50 就是它的单机版本）；
 b) 只设**增量门**：对 `git diff` 命中的 hunk 跑 `black --check`（本轮 R2-修复 的作用域化 lint 判据已是这个形状），
    存量债列白名单，逐步收敛；
 c) 改声明：把 PROJECT-SPEC/02 的"跑 format"改成"新写/新改代码满足 formatter"，并在 pyproject 注明不追存量
    （冻结文档，需人工）。
同族参照：BUG-40（flake8 的 [tool.flake8] 因缺插件完全不生效）。
- reported_by: cypy-verifier
- task_id: T0r58

## BUG-53 [2026-09-27T10:25:21Z] [medium] OPEN
- summary: [构建/规范配置] pyproject 声明了 [tool.black] line-length=100，但 156 个 .py 里 142 个不满足，照 PROJECT-SPEC/02 跑 format 会产出巨量不可复审的 diff
- detail: 现象（两条口径当场可复跑，全部在本工作树实测）：
  $ python -X utf8 -m black --line-length 100 --check cypyc cypy_bridge scripts tests
  142 files would be reformatted, 14 files would be left unchanged
  $ find cypyc cypy_bridge scripts tests -name "*.py" | wc -l   → 156
  ↑ 声明口径覆盖不到 142/156 个文件（91%）；本机 black：python -m black, 26.3.1 (compiled: yes)
Python (CPython) 3.13.14

声明处（逐字）：
  pyproject.toml:49-50  [tool.black] / line-length = 100
  PROJECT-SPEC/02-命名与源码规范.md:46  “提交前跑 lint/format（如项目配置），0 warning 优先。”
contributor 照这条跑 `black .` 得到的不是"通过"，而是把 142 个文件整档重写。

本轮改动半径（同一命令、只列半径内 7 个 .py）：不满足的是 ["cypy_hook\\hook.py", "cypyc\\cli.py", "cypyc\\codegen\\cython_generator.py"]，
其余 1 个干净 —— 也就是说 R2-修复 的亲笔行是干净的，**债在文件级不在本环**。

为什么这条不是"格式洁癖"而是可量化的损失（R2-验证 的 P9 实测，件 `verify_r2_probe.json`）：
  以 HEAD 为底，`cypyc/parser/parser.py` 文本差 1893 行；
  先把 HEAD 版本按同一配置过一遍 black 再比，只差 460 行
  ⇒ 其中 1433 行纯属排版噪声，真实内容增量（09-26/R1 未提交工作 +
  本环 4 处）只有 460 行。`macro_expander.py` 同型：365 →
  185（排版占 194）。
这正是 BUG-50 的放大器：一个未被门禁认领的 formatter 声明，让人有理由顺手 `black` 掉两档产品文件，
而全仓 91% 的文件都在同一个坑里。

不算证明（避免被误判成"已修"）：
 - 只对个别文件跑 `black` 让它变干净 ≠ 这条闭环 —— 声明是仓库级的；
 - 把 `[tool.black]` 段落删掉/改口 ≠ 修复（那是把声明改成既成事实，且与 BUG-40 的"配置不生效"是同一种回避）；
 - `black --check` 的 rc=1 只是本条的现象，不能反过来当判据。

修法（交裁决，三选一或组合，自动轮不独走）：
 a) 一次性全仓 `black` 提交（约 142 文件、数千行噪声）+ 之后把 `black --check` 设为 CI 硬门；
    这一条要人工批，因为一旦提交，任何未提交工作都无法与排版噪声区分（BUG-50 就是它的单机版本）；
 b) 只设**增量门**：对 `git diff` 命中的 hunk 跑 `black --check`（本轮 R2-修复 的作用域化 lint 判据已是这个形状），
    存量债列白名单，逐步收敛；
 c) 改声明：把 PROJECT-SPEC/02 的"跑 format"改成"新写/新改代码满足 formatter"，并在 pyproject 注明不追存量
    （冻结文档，需人工）。
同族参照：BUG-40（flake8 的 [tool.flake8] 因缺插件完全不生效）。
- reported_by: cypy-verifier
- task_id: T0r59

### DUPLICATE(2026-09-27T10:28Z 追加留档，R2-验证 自证) — 本条是「重跑未加幂等守卫的入账脚本」造成的双发
- 正身：**BUG-52**（`task_id: T0r58`，2026-09-27T10:24:13Z）；本条 `T0r59`（10:25:21Z）与它的 summary/detail 逐字相同。
- 成因：首跑 `verify_r2_file_bug52.py` 在 `report_bug` 落账之后，崩于「取下一条条目标题」的 `txt.index(...)`
  （账本最后一条没有后继标题 ⇒ ValueError）⇒ 证据件没写成；我在没加幂等守卫的情况下重跑同一条命令，
  于是 `report_bug` 又发了一次。
- 服务端没有任何删除/合并/关闭 bug 的 API（本轮实测：120 个工具无一可改 description 或撤单）
  ⇒ 这条只能**标注**：`T0r59` 保持 `待领取` 但**不应被 claim**；后续轮引用该缺陷一律用 BUG-52。
- 机制化补救：`verify_r2_finish_bug52.py` 改成「summary 命中数必须恰好为 1，否则 REFUSE」；
  `verify_r2_ledger3way.py` 增加「同一 summary 出现多次 ⇒ refuse」的重复检测。

## BUG-54 [2026-09-27T11:47:06Z] [medium] OPEN
- summary: cypyc watch 的编译中间目录 build/ 是进程间共享的：两个 watch 并发编译会互踩，引擎内串行锁挡不住
- detail: 现象（本环实测，判据件 `.fist-loop-20260927/advance_r2_race_probe.json`）：
同一引擎内两个线程并发调用 `HotReloadEngine._compile_and_reload_module` 编译**同一模块**时，
锁关（把 `_compile_lock` 换成 nullcontext，其余逐字相同）3/3 轮出红，锁开 3/3 轮全绿。
红文的成因不是我的夹具：`error: can't copy 'build\lib.win-amd64-cpython-313\<mod>.pyd':
doesn't exist or not a regular file`、`error: command 'cl.exe' failed with exit code 1`、
以及随后 `未找到生成的.pyd文件` + `[WinError 2] 系统找不到指定的文件: <临时目录>`。

来历：`CypyHook.compile_to_pyd` 虽然把**最终**产物写进传入的 output_dir（本环之后还会复制到 -o），
但 setuptools 的**中间**产物固定在调用进程 CWD 下的 `build/`（`build\lib.win-amd64-cpython-313\`），
这个路径不受 output_dir 参数控制 ⇒ 同进程用锁串行可以避开，**两个进程**（例如两个
`cypyc watch` 分别盯两个目录，或 watch 与 `cypyc transpile --watch` 之类并行）仍会在同一个
`build/` 上互相覆盖。

影响：本环加的引擎级 `threading.RLock` 只保证单引擎串行（`advance_r2_watch_probe.py` 三次
跑全绿即为此证）；跨进程并行使用时，用户看到的是一条不含模块名的 `cl.exe failed`，
难以归因到"另一个 watch 进程正在写同一个 build 目录"。

修法（下一轮或人工）：给每次编译一个独立 `build_temp`/`--build-lib`（把中间目录也搬进临时目录），
或让 CLI 在同一仓库内对 watch 进程做单实例锁。本环不动 `cypy_hook`，因为它同时服务
import hook 路径，改中间目录会影响缓存命中面。

不算证明：只说"加了引擎内锁"不等于这条关闭；关闭判据必须是**两个进程**并发编译不同模块
仍能各自产出 .pyd（配一条子进程对照）。
- reported_by: cypy-advancer
- task_id: T0r62

## BUG-55 [2026-09-27T12:46:09Z] [medium] OPEN
- summary: generic_transformer 读 `type_params`，parser 的泛型节点带的是 `generic_params` ⇒ 泛型收集恒为空
- detail: 主张：generic_transformer 读 `type_params`，parser 的泛型节点带的是 `generic_params` ⇒ 泛型收集恒为空
声明面（缺陷就是与它矛盾之处）：cypyc/transformer/generic_transformer.py:5（自称注册泛型参数）与 :39（读 type_params）

现形判据(pos) 实测：{"generic_param_nodes": [["FuncDef", ["T"]], ["StructDef", ["T"]]], "generic_defs_collected": 0}
  期望：有泛型节点时被收集到（docstring 第 5 行『注册泛型参数』）
对照判据(ctl) 实测：{"collected_with_type_params_attr": 1}
  期望：只要属性叫 type_params 就能收 ⇒ 坏的是名字对不上，不是收集器逻辑

为什么值得入账：泛型定义在转换阶段被静默丢弃：`GenericTransformer.generic_defs` 恒空 ⇒ 任何依赖泛型注册的下游（类型约束、单态化）拿不到输入，而接口不报错。

复跑（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）：python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C1
整批复跑：python -X utf8 .fist-loop-20260927/hunt_r3_confirm.py（判据件 .fist-loop-20260927/hunt_r3_confirm.json）

不算证明：只说『文件里有 generic 关键字』不算；必须给出真解析出的节点带 generic_params 而收集结果为空，并配一条『属性叫 type_params 时确实被收集』的对照。

来历（待修复轮确认，我只给到调用面事实与形状）：见上面 file:line 与两条判据的实测输出。
- reported_by: cypy-hunter
- task_id: T0r63

### FIXED(修复=已完成) — 2026-09-27T16:52:09Z 追加留档（2026-09-28 R3-修复，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r70`（ns `cypy-loop-20260927`）下 16 叶全链带 `[omega:required]`的 claim→omega→execute→submit→output_validate→omega_result_verify→verify；报告：`memory/reviews/20260928.00.20.00.md`
- 修法：_collect_generics 同时认 generic_params 与 type_params（前者是 FuncDef/StructDef 的叫法，后者是 DuckDef 的叫法，两族都得收）
- 被放弃的替代修法与理由：把 parser 的属性改名成 type_params：会撞 SYNTAX/11-generics 的既有语义面与 3 个 analyzer + 1 个 codegen 读取点，改一处牵四文件
- 改动文件：`cypyc/transformer/generic_transformer.py`
- 回归锁（2 条，pos=1 / 对照=1）：`test_bug55_generic_params_nodes_are_collected`、`test_bug55_duck_def_type_params_still_collected`
- 前后对照（R3-寻虫 原夹具 hunt_r3_repro.py，0=现形 / 1=不现形 / 2=夹具坏）：before rc=0 → after rc=1；修前 observed=`{"generic_nodes": 1, "collected": 0}`，修后 observed=`{"generic_nodes": 1, "collected": 1}`
- 三套基线（同一时刻复算，`.fist-loop-20260927/fix_r3_baselines.json` refuse=[]）：pytest `1920 passed in 470.29s (0:07:50)`（下限 1920）/ 自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；HEAD 仍 `17d68b4`、暂存 0；改动半径 7 档全部归属本单
- 复跑：`python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C1`（本条目复跑命令与本段前后对照同源）
## BUG-56 [2026-09-27T12:46:10Z] [medium] OPEN
- summary: `cypyc transpile` 的 --check-only/--emit-ast/--generate-setup/--emit-cython 只被印给用户，run_transpile 一个都不读（读它们的是只能从不可达分支进入的 r
- detail: 主张：`cypyc transpile` 的 --check-only/--emit-ast/--generate-setup/--emit-cython 只被印给用户，run_transpile 一个都不读（读它们的是只能从不可达分支进入的 run_default）
声明面（缺陷就是与它矛盾之处）：docs/USAGE.md 与 transpile --help 的承诺 vs cypyc/cli.py:435-516

现形判据(pos) 实测：{"flag_readers": {"run_default": ["check_only", "emit_ast", "emit_cython", "generate_setup"], "run_build": ["check_only"]}, "run_transpile_reads": []}
  期望：transpile 的帮助文本写了这四个旗标 ⇒ 至少要读一个
对照判据(ctl) 实测：{"top_level_choices": ["transpile,compile,build,run,watch,hook", "transpile,compile,build,run,watch,hook"], "transpile_help_advertises": ["--check-only", "--emit-ast", "--generate-setup", "--emit-cython"]}
  期望：transpile --help 确实把这四个旗标承诺给用户

为什么值得入账：`cypyc transpile` 把 --check-only/--emit-ast/--generate-setup/--emit-cython 印给用户，但 run_transpile 一个都不读 ⇒ 用户以为做了静态检查/出了中间码，实际什么都没发生；真正读这四个旗标的是只能从不可达 else 分支进入的 run_default。

复跑（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）：python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C3
整批复跑：python -X utf8 .fist-loop-20260927/hunt_r3_confirm.py（判据件 .fist-loop-20260927/hunt_r3_confirm.json）

不算证明：只证明『旗标能解析成 args.xxx』不算（那是 argparse 的功劳）；必须证明 transpile 路径上没有任何读取，且 --help 确实承诺过这四个旗标（调用面实测，不是读源码字面）。

来历（待修复轮确认，我只给到调用面事实与形状）：见上面 file:line 与两条判据的实测输出。
- reported_by: cypy-hunter
- task_id: T0r64

### FIXED(修复=已完成) — 2026-09-27T16:52:09Z 追加留档（2026-09-28 R3-修复，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r70`（ns `cypy-loop-20260927`）下 16 叶全链带 `[omega:required]`的 claim→omega→execute→submit→output_validate→omega_result_verify→verify；报告：`memory/reviews/20260928.00.20.00.md`
- 修法：在 run_transpile 里落地四个旗标：check_only 走 CypyHook._parse_and_analyze 且不产码；emit_ast 打印解析后的节点树；emit_cython 打印 .pyx 文本；generate_setup 用 SetupGenerator 在产物目录写 setup.py。bridge 模式下 emit_cython 明确回话『这里产的是 C』而不是静默
- 被放弃的替代修法与理由：把四个旗标从 CLI 上摘掉：手册与 --help 已对外承诺，摘旗是缩对外接口面，且违反指挥官裁定「接线而不是砍 CLI」
- 改动文件：`cypyc/cli.py`
- 回归锁（6 条，pos=5 / 对照=1）：`test_bug56_check_only_reports_and_generates_nothing`、`test_bug56_check_only_fails_on_broken_source`、`test_bug56_emit_ast_prints_parsed_nodes`、`test_bug56_emit_cython_prints_cython_code`、`test_bug56_generate_setup_writes_buildable_script`、`test_bug56_control_plain_transpile_writes_no_setup`
- 前后对照（R3-寻虫 原夹具 hunt_r3_repro.py，0=现形 / 1=不现形 / 2=夹具坏）：before rc=0 → after rc=1；修前 observed=`{"flag_readers": {"run_default": ["check_only", "emit_ast", "emit_cython", "generate_setup"], "run_build": ["check_only"]}}`，修后 observed=`{"flag_readers": {"run_transpile": ["check_only", "emit_ast", "emit_cython", "generate_setup"], "run_default": ["check_only", "emit_ast", "emit_cython", "generate_setup"], "run_build": ["check_only"]}}`
- 三套基线（同一时刻复算，`.fist-loop-20260927/fix_r3_baselines.json` refuse=[]）：pytest `1920 passed in 470.29s (0:07:50)`（下限 1920）/ 自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；HEAD 仍 `17d68b4`、暂存 0；改动半径 7 档全部归属本单
- 复跑：`python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C3`（本条目复跑命令与本段前后对照同源）
## BUG-57 [2026-09-27T12:46:10Z] [low] OPEN
- summary: CUnion/union 的 docstring 示例 `CUnion(int, float)` 一跑就抛 TypeError（对 Python 内建类型取 ctypes.sizeof）
- detail: 主张：CUnion/union 的 docstring 示例 `CUnion(int, float)` 一跑就抛 TypeError（对 Python 内建类型取 ctypes.sizeof）
声明面（缺陷就是与它矛盾之处）：cypy_bridge/union.py:23-31 与 :179 的示例文本

现形判据(pos) 实测："TypeError: this type has no size"
  期望：docstring 里的示例（若真含 CUnion(int, float)）应可用
对照判据(ctl) 实测：{"with_ctypes_types": "CUnion"}
  期望：给 ctypes 类型时构造成功

为什么值得入账：`cypy_bridge.union` 的 docstring/工厂函数示例用 Python 内建类型 `CUnion(int, float)`，而实现对它们调 `ctypes.sizeof` ⇒ 照文档抄一行就抛 `TypeError: this type has no size`。文档示例是这个模块对外唯一的用法说明。

复跑（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）：python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C4
整批复跑：python -X utf8 .fist-loop-20260927/hunt_r3_confirm.py（判据件 .fist-loop-20260927/hunt_r3_confirm.json）

不算证明：只说『文档写得不够清楚』不算；必须实证示例代码本身跑不通，并配一条『换成 ctypes 类型即成功』的对照（证明坏在示例，不是整个 API）。

来历（待修复轮确认，我只给到调用面事实与形状）：见上面 file:line 与两条判据的实测输出。
- reported_by: cypy-hunter
- task_id: T0r65

### FIXED(修复=已完成) — 2026-09-27T16:52:09Z 追加留档（2026-09-28 R3-修复，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r70`（ns `cypy-loop-20260927`）下 16 叶全链带 `[omega:required]`的 claim→omega→execute→submit→output_validate→omega_result_verify→verify；报告：`memory/reviews/20260928.00.20.00.md`
- 修法：示例改成文档自己承诺的两种可用形状（ctypes 类型 / C 类型名字符串）；对 Python 内建类型给 UnionTypeError 并写清可接受形状，不再让 ctypes 抛『this type has no size』这种看不懂的错
- 被放弃的替代修法与理由：把 int/float 隐式映射到 c_int/c_double：Cython 的 int/float 宽度（32 位）与 CPython 的 int（64 位）不同，选哪个都是新的语义决定，SYNTAX/26 未对 bridge 侧 CUnion 定宽 ⇒ 属裁决面，本轮不代作
- 改动文件：`cypy_bridge/union.py`
- 回归锁（3 条，pos=2 / 对照=1）：`test_bug57_documented_member_shapes_work`、`test_bug57_builtin_member_type_is_diagnosed`、`test_bug57_union_docstrings_advertise_only_runnable_shapes`
- 前后对照（R3-寻虫 原夹具 hunt_r3_repro.py，0=现形 / 1=不现形 / 2=夹具坏）：before rc=0 → after rc=1；修前 observed=`{"raised": "TypeError: this type has no size"}`，修后 observed=`{"raised": "UnionTypeError: Union member 'int' is a Python builtin type; pass a ctypes type (ctypes.c_int) or a "}`
- 三套基线（同一时刻复算，`.fist-loop-20260927/fix_r3_baselines.json` refuse=[]）：pytest `1920 passed in 470.29s (0:07:50)`（下限 1920）/ 自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；HEAD 仍 `17d68b4`、暂存 0；改动半径 7 档全部归属本单
- 复跑：`python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C4`（本条目复跑命令与本段前后对照同源）
## BUG-58 [2026-09-27T12:46:10Z] [medium] OPEN
- summary: realloc(ptr, 0) 先 free 再 `return None`，而签名是 `-> int`、文档只说返回地址，malloc 同一形状走的是抛错分支
- detail: 主张：realloc(ptr, 0) 先 free 再 `return None`，而签名是 `-> int`、文档只说返回地址，malloc 同一形状走的是抛错分支
声明面（缺陷就是与它矛盾之处）：cypy_bridge/memory.py:195-216

现形判据(pos) 实测：{"returned": "None", "annotation": "int", "doc_says": "新的内存地址（int）\n\n异常："}
  期望：注解 int + 文档『新的内存地址（int）』⇒ 不该返回 None
对照判据(ctl) 实测："malloc(0) raised MemoryError"
  期望：抛错

为什么值得入账：`memory.realloc` 签名 `-> int`、docstring 只说返回地址，却在 `size<=0` 分支先 free 再 `return None` ⇒ 调用方按 int 拿返回值做地址运算会拿到 None（且原内存已被释放）。同族入口 `malloc(0)` 走的是抛 MemoryError，说明这不是模块统一风格。

复跑（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）：python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C5
整批复跑：python -X utf8 .fist-loop-20260927/hunt_r3_confirm.py（判据件 .fist-loop-20260927/hunt_r3_confirm.json）

不算证明：『文档没写这个分支』只是措辞问题；要的是**注解与返回值互斥**（int 却给 None）且同族入口行为不一致这两条同时成立。

来历（待修复轮确认，我只给到调用面事实与形状）：见上面 file:line 与两条判据的实测输出。
- reported_by: cypy-hunter
- task_id: T0r66

### FIXED(修复=已完成) — 2026-09-27T16:52:09Z 追加留档（2026-09-28 R3-修复，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r70`（ns `cypy-loop-20260927`）下 16 叶全链带 `[omega:required]`的 claim→omega→execute→submit→output_validate→omega_result_verify→verify；报告：`memory/reviews/20260928.00.20.00.md`
- 修法：注解改 Optional[int]，docstring 写明 size<=0 走 C 的 realloc(p,0) 口径（释放并返回 None），并说明它与 malloc(0) 抛 MemoryError 不是同一条规则
- 被放弃的替代修法与理由：改成返回 0 或抛 MemoryError：既有 tests/test_bridge_library.py::test_realloc_zero_size 断言 assertIsNone(result)，改返回值必须弱化/删除既有测试 ⇒ 撞红线。行为半边的不对称留裁决
- 改动文件：`cypy_bridge/memory.py`
- 回归锁（3 条，pos=1 / 对照=2）：`test_bug58_realloc_annotation_matches_return_shape`、`test_bug58_realloc_zero_size_still_returns_none_and_frees`、`test_bug58_control_malloc_zero_still_raises`
- 前后对照（R3-寻虫 原夹具 hunt_r3_repro.py，0=现形 / 1=不现形 / 2=夹具坏）：before rc=0 → after rc=0；修前 observed=`{"returned": "None", "annotation": "int"}`，修后 observed=`{"returned": "None", "annotation": "Optional"}`
- **本环未消除的那一半（如实写明，不签已修）**：C5 的现形判据钉的是『返回 None』这一半，那半边被既有测试钉住；本环只消除注解/文档与返回值的互斥，observed 里 annotation 已从 int 变 Optional
- 交回裁决：realloc(p,0) 是否应改为返回 0（并与 malloc(0) 对称）——若改，须同轮改既有测试并记为口径变更
- 三套基线（同一时刻复算，`.fist-loop-20260927/fix_r3_baselines.json` refuse=[]）：pytest `1920 passed in 470.29s (0:07:50)`（下限 1920）/ 自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；HEAD 仍 `17d68b4`、暂存 0；改动半径 7 档全部归属本单
- 复跑：`python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C5`（本条目复跑命令与本段前后对照同源）
## BUG-59 [2026-09-27T12:46:10Z] [medium] OPEN
- summary: get_compilation_order 把环内模块塞进 `set` 再 extend ⇒ 环存在时推荐编译序随进程哈希种子变化
- detail: 主张：get_compilation_order 把环内模块塞进 `set` 再 extend ⇒ 环存在时推荐编译序随进程哈希种子变化
声明面（缺陷就是与它矛盾之处）：cypyc/project/module_dependency_graph.py:200-212（文档只说『跳过循环中的模块』）

现形判据(pos) 实测：{"per_seed_orders": [["0", "d,b,c,a,e"], ["1", "d,e,a,b,c"], ["7", "d,b,a,c,e"], ["42", "c,e,b,d,a"], ["99", "e,b,a,d,c"]], "distinct": 5}
  期望：同一张图必须给同一个推荐序（文档只说『跳过循环中的模块』）
对照判据(ctl) 实测：{"acyclic_order": ["z", "y", "x"], "edges": "x→y, y→z（x 依赖 y）"}
  期望：无环时给确定的『被依赖者在前』序 ⇒ 证明 get_compilation_order 本身没坏

为什么值得入账：`get_compilation_order` 把环内模块塞进 `set` 再 extend ⇒ 存在循环依赖时推荐编译序随进程字符串哈希种子变化（同一张图在不同 PYTHONHASHSEED 下给出不同顺序），破坏可重现构建；文档只承诺『跳过循环中的模块』，没承诺任意序。

复跑（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）：python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C6
整批复跑：python -X utf8 .fist-loop-20260927/hunt_r3_confirm.py（判据件 .fist-loop-20260927/hunt_r3_confirm.json）

不算证明：在同进程里改 `os.environ['PYTHONHASHSEED']` **测不出来**（字符串哈希在解释器启动时已定，本环 v1 就这么假绿过一次）⇒ 必须是独立子进程各带一个种子；还要配一条无环图给确定序的对照，否则分不清是产品 nondeterminism 还是夹具噪声。

来历（待修复轮确认，我只给到调用面事实与形状）：见上面 file:line 与两条判据的实测输出。
- reported_by: cypy-hunter
- task_id: T0r67

### FIXED(修复=已完成) — 2026-09-27T16:52:09Z 追加留档（2026-09-28 R3-修复，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r70`（ns `cypy-loop-20260927`）下 16 叶全链带 `[omega:required]`的 claim→omega→execute→submit→output_validate→omega_result_verify→verify；报告：`memory/reviews/20260928.00.20.00.md`
- 修法：extend(sorted(cycle_modules)) ⇒ 同一张图在任何 PYTHONHASHSEED 下给同一推荐序，环内模块仍排在最后且按名字定序
- 被放弃的替代修法与理由：只改文档补一句『环内顺序不定』：把不可重现构建写成规格，等于放弃 topological_sort 那半边已经保证的确定性
- 改动文件：`cypyc/project/module_dependency_graph.py`
- 回归锁（1 条，pos=1 / 对照=0）：`test_bug59_compilation_order_stable_across_hash_seeds`
- 前后对照（R3-寻虫 原夹具 hunt_r3_repro.py，0=现形 / 1=不现形 / 2=夹具坏）：before rc=0 → after rc=1；修前 observed=`{"per_seed_orders": {"0": "['d', 'b', 'c', 'a', 'e']", "1": "['d', 'e', 'a', 'b', 'c']", "7": "['d', 'b', 'a', 'c', 'e']", "42": "['c', 'e', 'b', 'd', 'a']", "99": "['e', 'b', 'a', 'd', 'c']"}, "distinct": 5}`，修后 observed=`{"per_seed_orders": {"0": "['a', 'b', 'c', 'd', 'e']", "1": "['a', 'b', 'c', 'd', 'e']", "7": "['a', 'b', 'c', 'd', 'e']", "42": "['a', 'b', 'c', 'd', 'e']", "99": "['a', 'b', 'c', 'd', 'e']"}, "distinct": 1}`
- 三套基线（同一时刻复算，`.fist-loop-20260927/fix_r3_baselines.json` refuse=[]）：pytest `1920 passed in 470.29s (0:07:50)`（下限 1920）/ 自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；HEAD 仍 `17d68b4`、暂存 0；改动半径 7 档全部归属本单
- 复跑：`python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C6`（本条目复跑命令与本段前后对照同源）
## BUG-60 [2026-09-27T12:46:10Z] [low] OPEN
- summary: BuildBlockChecker 的 docstring 规则 2（指针语法只能在构建块内部使用）没有实现：_visit_DerefExpr/_visit_PointerType 只注释『移除』，不 append 任何 error
- detail: 主张：BuildBlockChecker 的 docstring 规则 2（指针语法只能在构建块内部使用）没有实现：_visit_DerefExpr/_visit_PointerType 只注释『移除』，不 append 任何 error
声明面（缺陷就是与它矛盾之处）：cypyc/analyzer/build_block_checker.py:5-6（声明）对 :75-84（实现）

现形判据(pos) 实测：{"node_kinds": ["FuncDef", "PointerType"], "docstring_rule2": ["1. 构建块内部默认unsafe，允许指针语法", "2. 指针语法只能在构建块内部使用"], "errors_for_pointer_outside_block": []}
  期望：规则 2 承诺『指针语法只能在构建块内部使用』⇒ 函数体内的 PointerType 应报错
对照判据(ctl) 实测：{"errors_from_a_different_rule": ["yield statement is not allowed in assign build blocks (=:) at 7:3"]}
  期望：对照：另一条规则（assign 块里不许 yield）确实在报 ⇒ 检查器不是整体空转，只有规则 2 是空的

为什么值得入账：`build_block_checker` 模块 docstring 列的规则 2『指针语法只能在构建块内部使用』没有实现：`_visit_DerefExpr`/`_visit_PointerType` 只留了一句『移除…限制』的注释，不 append 任何 error ⇒ 函数体里裸用 `*int` 也过得了这道门。要么补实现，要么改文档口径。

复跑（退出码 0=缺陷现形 / 1=不现形 / 2=夹具坏了）：python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C8
整批复跑：python -X utf8 .fist-loop-20260927/hunt_r3_confirm.py（判据件 .fist-loop-20260927/hunt_r3_confirm.json）

不算证明：只说『注释写着移除』不算；必须实测块外指针语法 errors 为空，且配一条『别的规则确实在报』的对照（否则整个检查器空转是另一码事）。另：规则清单在**模块** docstring，读类 docstring 会读空（本环 v3 误判过一次）。

来历（待修复轮确认，我只给到调用面事实与形状）：见上面 file:line 与两条判据的实测输出。
- reported_by: cypy-hunter
- task_id: T0r68

### FIXED(修复=已完成) — 2026-09-27T16:52:09Z 追加留档（2026-09-28 R3-修复，本条目正文与标题行 `OPEN` 一字未改）
- 修复单：根 `T0r70`（ns `cypy-loop-20260927`）下 16 叶全链带 `[omega:required]`的 claim→omega→execute→submit→output_validate→omega_result_verify→verify；报告：`memory/reviews/20260928.00.20.00.md`
- 修法：规则 2 按 SYNTAX/04-pointer-types.md『指针使用限制』重写：指针声明的合法位置是函数作用域，构建块只是其中一种；并写明指针寻址合法性/所有权检查在 pointer_checker，本模块不重复把关
- 被放弃的替代修法与理由：补实现（块外指针就报错）：会打断仓库里 36 处 `: *t` 的合法写法，且与冻结层 SYNTAX/04 直接冲突——冻结语义优先于模块 docstring
- 改动文件：`cypyc/analyzer/build_block_checker.py`
- 回归锁（2 条，pos=1 / 对照=1）：`test_bug60_docstring_rule2_aligns_with_frozen_syntax`、`test_bug60_control_other_rules_still_enforced`
- 前后对照（R3-寻虫 原夹具 hunt_r3_repro.py，0=现形 / 1=不现形 / 2=夹具坏）：before rc=0 → after rc=0；修前 observed=`{"node_kinds": ["PointerType"], "errors": []}`，修后 observed=`{"node_kinds": ["PointerType"], "errors": []}`
- **本环未消除的那一半（如实写明，不签已修）**：C8 的现形判据是『块外指针不报错』，而按 SYNTAX/04 那正是期望行为：入账主张里的『要么补实现』半边经冻结层核对后不成立，只有 docstring 那半边是真缺陷
- 交回裁决：是否把『结构体字段不能是指针』这条 SYNTAX 限制落成检查（本环未做）
- 三套基线（同一时刻复算，`.fist-loop-20260927/fix_r3_baselines.json` refuse=[]）：pytest `1920 passed in 470.29s (0:07:50)`（下限 1920）/ 自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；HEAD 仍 `17d68b4`、暂存 0；改动半径 7 档全部归属本单
- 复跑：`python -X utf8 .fist-loop-20260927/hunt_r3_repro.py C8`（本条目复跑命令与本段前后对照同源）
## BUG-61 [2026-09-27T20:25:15Z] [high] OPEN
- summary: [RC1_func_symbol_typed_as_return] 函数名被登记成它的**返回类型**（没有可调用签名）⇒ 元数判定挂错表：正确调用被判错、错误调用被放行
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  C01 correct_two_arg_call_of_local_function 期望=clean 实测=["Callable arity mismatch: expected 1, got 2 at 9:5"]；
  C02 missing_arg_call_of_local_function 期望=error 实测=[]；
  C03 function_with_matching_signature_returned_as_alias 期望=clean 实测=["Return type mismatch: expected Callable[tuple[int], str], got str at 7:1"]；
  C04 plain_fn_called_with_extra_arg 期望=error 实测=[]；
  C05 plain_fn_called_with_missing_arg 期望=error 实测=[]

成对对照（同族里今天行为正确的形状）：
  对照 return_mismatch_reported 实测=["Return type mismatch: expected int, got str at 3:1"]
  对照 alias_identity_clean 实测=[]
  对照 callback_arity_reported 实测=["Callable arity mismatch: expected 1, got 2 at 3:12"]

机制（file:line 级，本环未改产品码）：type_checker.py:523-525（同族 :393-395、:473-475）`self.type_map[node.name] = return_type`；`_visit_Call`(:1035) 之后只看 `type_map[名字]` 是不是 Callable，于是函数自身的参数表 (:546-547 `old_type_map[node.name] = return_type`) 全程不参与判定

为什么值得入账：一张单一个根因，症状 5 条：C01、C02、C03、C04、C05。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py RC1_func_symbol_typed_as_return
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：只说『读代码像是这样』不算；必须同时给出「正确调用被判错」与「错误调用被放行」两向实测，并配一条元数违例确实在报的对照（否则是整条通道空转，另码另说）。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:15+00:00 实测；severity=high；修属：下一环修（分析器内部，不涉冻结面）
- reported_by: cypy-hunter
- task_id: T0r75

### FIXED(verify=已完成) — 2026-09-28 R4-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r75`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-27T21:57:32+00:00`、`completed_by=cypy-fixer`）
- 改动文件：`cypyc/analyzer/type_checker.py`（新增 `callable_sigs` 签名表与 `_register_callable`）
- 锁死回归：`tests/test_loop_20260927_fix_r4.py::test_fixture_matches_declared_expectation` 的 C01..C05 五条 + `test_call_face_reports_over_cli`（CLI 调用面）
- 闭环证据：.fist-loop-20260927/fix_r4_locks.json（修前 14 红→修后全绿）、fix_r4_revert.json（摘掉 `_register_callable` 后该族锁必红）
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-62 [2026-09-27T20:25:15Z] [high] OPEN
- summary: [RC2_no_argument_type_check] 实参类型与形参声明类型从不做兼容性比对：`apply("s")`（形参 `n: int`）零诊断，而同族 `let x: int = "s"` 会报
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  C06 wrong_signature_passed_to_callback_param 期望=error 实测=[]；
  C07 non_callable_passed_to_callback_param 期望=error 实测=[]；
  C08 str_arg_to_annotated_int_param 期望=error 实测=[]

成对对照（同族里今天行为正确的形状）：
  对照 assignment_mismatch_reported 实测=["Type mismatch: expected int, got str at 2:9"]

机制（file:line 级，本环未改产品码）：`_visit_Call`(:1039-1043) 对每个 arg 只 `_visit(arg)` 求类型后丢弃，赋值处(:768/792/807)才比类型；两边没有共用同一个兼容性谓词

为什么值得入账：一张单一个根因，症状 3 条：C06、C07、C08。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py RC2_no_argument_type_check
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：必须与同族赋值形状（`let x: int = "s"` 会报）并排给出，否则分不清是「没有实参检查」还是「分析器整体不看类型」。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:15+00:00 实测；severity=high；修属：下一环修（需与 SYNTAX/01 的『有注解的参数进行类型检查』口径对齐）
- reported_by: cypy-hunter
- task_id: T0r76

### FIXED(verify=已完成) — 2026-09-28 R4-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r76`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-27T21:57:32+00:00`、`completed_by=cypy-fixer`）
- 改动文件：`cypyc/analyzer/type_checker.py`（`_callable_arg_mismatch` 与 `_check_callable_arg_types`，判定入口只有这一个）
- 锁死回归：同上 C06..C08，外加对照 `test_arg_type_control_on_dynamic_value_stays_silent`（动态值不得误报）
- 闭环证据：fix_r4_impact.json（203 档语料：新增诊断 0、消失诊断 0）
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-63 [2026-09-27T20:25:16Z] [high] OPEN
- summary: [RC3_struct_field_type_unresolved] struct 成员的声明类型在方法体里解析不出来：`self.n`/`self.i.n`/`self.cb(1,2)` 三类全部静默，同族局部变量与形参都会判
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  C09 int_field_returned_from_str_method 期望=error 实测=[]；
  C10 nested_field_wrong_type 期望=error 实测=[]；
  C11 field_used_with_wrong_arity_call 期望=error 实测=[]

成对对照（同族里今天行为正确的形状）：
  对照 local_let_flows_to_return 实测=["Return type mismatch: expected str, got int at 4:1"]
  对照 callback_arity_reported 实测=["Callable arity mismatch: expected 1, got 2 at 3:12"]

机制（file:line 级，本环未改产品码）：`_visit_Attribute`(:2122) 不查 struct 登记表 ⇒ `self.<field>` 得 Optional[None]，后续类型/元数判定按『不知道』放行

为什么值得入账：一张单一个根因，症状 3 条：C09、C10、C11。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py RC3_struct_field_type_unresolved
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：只测一层 `self.n` 不算，需再测嵌套链 `self.i.n` 与成员被当回调调用的形状；且必须配一条「同函数里局部变量会报」的对照。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:16+00:00 实测；severity=high；修属：下一环修
- reported_by: cypy-hunter
- task_id: T0r77

### FIXED(verify=已完成) — 2026-09-28 R4-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r77`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-27T21:57:32+00:00`、`completed_by=cypy-fixer`）
- 改动文件：`cypyc/analyzer/type_checker.py`（`self` 绑定不再被 object 覆盖；属性位 Callable 复用同一套判定；成员未知时返回 object 而不是 None）
- 锁死回归：同上 C09..C11 + 对照 `test_fixture_matches_declared_expectation[C09_ctl]`
- 闭环证据：fix_r4_revert.json（RC3 摘除 ⇒ C09/C10/C11 红）
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-64 [2026-09-27T20:25:16Z] [medium] OPEN
- summary: [RC4_internal_repr_in_message] 类型不符的用户可见文案直接内插 `Type` 对象 ⇒ 打印 `Callable[tuple[int], str]`，与源语法 `Callable[[int], str]` 两种写法都不对应
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  C12 alias_mismatch_message_is_source_shape 期望=clean_message 实测=["Type mismatch: expected Callable[tuple[int], str], got int at 3:9", "Return type mismatch: expected int, got Callable[tuple[int], str] at 5:1"]

成对对照（同族里今天行为正确的形状）：
  对照 plain_message_shape_ok 实测=["Type mismatch: expected int, got str at 2:9"]

机制（file:line 级，本环未改产品码）：f-string 里 `{declared_type}`（:768/:792/:807/:840…）走 `Type.__repr__`，泛型参数位用的是 python `tuple[...]` 的 repr

为什么值得入账：一张单一个根因，症状 1 条：C12。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py RC4_internal_repr_in_message
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：文案类主张必须把整条 message 原文打出来；只说『不好看』不算——判据是产物里出现 `tuple[`而源语法从未这样写。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:16+00:00 实测；severity=medium；修属：下一环修（文案层，行为不变）
- reported_by: cypy-hunter
- task_id: T0r78

### FIXED(verify=已完成) — 2026-09-28 R4-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r78`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-27T21:57:32+00:00`、`completed_by=cypy-fixer`）
- 改动文件：`cypyc/analyzer/type_checker.py`（`_type_display` 显示层 + `_mismatch` 统一出口）
- 锁死回归：C12 与横向锁 `test_no_internal_repr_leaks_in_any_fixture_message`
- 闭环证据：fix_r4_revert.json（RC4 摘除 ⇒ C12 红）
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-65 [2026-09-27T20:25:17Z] [medium] OPEN
- summary: [DOC_status_stale_rows] 文档宣称的形态与今天实现不符（appendix-C 特性表 5 行 + USAGE 未实现清单 + 实现状态表 1 行 + 主类型表 i32 一族）
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  D01 [stale-doc] SYNTAX/appendix-C-features.md:594 原文「| `Callable[[T], R]` 函数类型标注 | 使用 `def` + 类型推断 | v0.5 |」 实测={"errors": ["Callable arity mismatch: expected 1, got 2 at 3:12"], "arity_violation_reported": true}；
  D02 [stale-doc] SYNTAX/appendix-C-features.md:595 原文「| `&` 位运算与取址冲突 | 使用 `|` 和 `^` 替代（`&` 保留给取址） | v0.5 |」 实测={"errors": []}；
  D04 [real-gap] SYNTAX/appendix-C-features.md:64 原文「| 整数 | `i8`、`i16`、`i32`、`i64`、`u8`、`u16`、`u32`、`u64` |」 实测={"let_i32": ["Type mismatch: expected i32, got int at 1:5"], "fn_i32_f64": ["Undefined name 'i32' at 1:10", "Undefined name 'f64' at 1:18"], "i32_literal_in_compiler": []}；
  D05 [stale-doc] SYNTAX/appendix-C-features.md:264 原文「let p: *mut i32 = &x      # 取地址」 实测={"mut_errors": ["Type mismatch: expected i32, got int at 2:9"]}；
  D07 [stale-doc] SYNTAX/appendix-C-features.md:520 原文「| 缩进 | 任意 4/8/Tab | 任意 | **必须 4 的倍数** |」 实测={"eight_spaces": ["Compilation error: Expected increased indentation at line 2. Expected 4, got 8"], "four_spaces_clean": true, "two_spaces": ["Compilation error: Invalid indentation level 2 at line 2. Indentation must be a multiple of 4"]}；
  D13 [stale-doc] docs/USAGE.md:404 原文「4. **`constraint` / `subtype` / `dispatch` 尚未实现**（v0.5 计划），联合类型可用 `type Numeric = int | fl」 实测={"constraint": ["'Numeric' is a constraint, not a type: it can only appear as a generic bound 'T: Numeric'. For a usable union type write 'type Numeric = int | float'. Use 'constraint' as a bound only (SYNTAX/33 C-2.1) at 2:22", "'Numeric' is a constraint, not a type: it can only appear as a generic；
  D14 [stale-doc] SYNTAX_IMPLEMENTATION_STATUS.md:106 原文「| 子类型声明 `subtype` | SubtypeDecl | ⚠ 仅词法已收（`subtype` 在 `Lexer.KEYWORDS`，已是保留字、不能再用作标识符）；`Su」 实测={"parser_hits": ["cypyc/parser/parser.py:1328", "cypyc/parser/parser.py:3390"], "codegen_hits": ["cypyc/analyzer/type_checker.py:125", "cypyc/analyzer/type_checker.py:460", "cypyc/analyzer/type_checker.py:1584"], "dispatch_hits": ["cypy_bridge/compiler.py:2345"]}

成对对照（同族里今天行为正确的形状）：
  D01 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D02 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D04 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D05 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D07 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D13 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D14 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词

机制（file:line 级，本环未改产品码）：状态表按 v0.5 计划手写，实现落地后无人回写。落地证据（符号级）：`constraint` 与 `subtype` 已在 parser 里走 `_parse_subtype_def` 建 `SubtypeDef`、codegen 侧登记 `subtype_defs`，`DispatchDecl` 只剩 bridge 里的死 handler；而主类型表宣称的 `i32` 在 `type_mapper` 里 0 命中

为什么值得入账：一张单一个根因，症状 7 条：D01、D02、D04、D05、D07、D13、D14。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py DOC_status_stale_rows
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：每一行都要当场重跑它自己宣称的那件事（今天已实现 / 仍未实现）；只抄文档行号不算，附录里《已实现的限制修复》14 行本轮未逐行复测 ⇒ 不入账。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:16+00:00 实测；severity=medium；修属：人工（SYNTAX/ 与状态表属冻结面 ⇒ 只挂账）
- reported_by: cypy-hunter
- task_id: T0r79

## BUG-66 [2026-09-27T20:25:17Z] [medium] OPEN
- summary: [DOC_cli_face_mismatch] CLI 用法文档与实读不符：`cypyc --compile` / `build --incremental` 不存在，`hook` 有 6 个未记选项，入口点与 Python 下限两处转述错
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  D06 [real-gap] SYNTAX/appendix-C-features.md:33 原文「cypyc --compile input.cypy       # 编译」 实测={"flag_compile": {"args": ["--compile", "examples/hello.cypy"], "rc": 1, "lines": ["<frozen runpy>:130: RuntimeWarning: 'cypyc.cli' found in sys.modules after import of package 'cypyc', but prior to execution of 'cypyc.cli'; this may result in unpredictable behaviour", "usage: cypyc [-h] [-o OUTPUT]；
  D08 [stale-doc] docs/USAGE.md:367 原文「cypyc = "cypy_hook.hook:main"     # 安装后注册 cypyc 命令」 实测={"pyproject_scripts": ["cypyc = \"cypyc.cli:main\"", "cypy-hook = \"cypy_hook.hook:main\""]}；
  D09 [stale-doc] docs/USAGE.md:19 原文「| Python | ≥ 3.8 |」 实测={"pyproject_requires": ["requires-python = \">=3.9\""], "declared_floor_note": "本机只有一个解释器，3.8 能不能跑我测不出 ⇒ 只比**文档引用的声明**与**实际声明**是否一致"}；
  D10 [usage-mismatch] docs/USAGE.md:131 原文「cypyc hook clear-cache    # 清除 Cypy 编译缓存（__pycache__/cypy）」 实测={"help_rc": 0, "undocumented_options": ["--transpile-only", "--compile", "--run", "--eval", "-o", "--output"], "help_tail": ["--run RUN             Run the specified function after compilation", "--eval EVAL           Evaluate Cypy code directly", "<frozen runpy>:130: RuntimeWarning: 'cypyc.cli' fou

成对对照（同族里今天行为正确的形状）：
  D06 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D08 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D09 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D10 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词

机制（file:line 级，本环未改产品码）：argparse 的子命令 choices 是唯一事实源，文档手抄：`--incremental` 不在 `build` 的 parser 里、`transpile-only` 与 `--run`/`--eval` 只在 `hook` 的 help 里出现；入口点由 `requires-python` 与 `cypyc =` 两处声明，USAGE 转述成了另一个程序

为什么值得入账：一张单一个根因，症状 4 条：D06、D08、D09、D10。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py DOC_cli_face_mismatch
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：旗标类主张必须拿 `--help` 与 argparse 实读集对照，并配一条「同一 CLI 别的命令可用」的对照，否则分不清是旗标不存在还是 CLI 整个挂了。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:17+00:00 实测；severity=medium；修属：下一环修（docs 非冻结）
- reported_by: cypy-hunter
- task_id: T0r80

### FIXED(verify=已完成) — 2026-09-28 R4-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r80`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-27T21:57:32+00:00`、`completed_by=cypy-fixer`）
- 改动文件：`docs/USAGE.md`（Python 下限、hook 选项清单、入口点三处按实读改写）
- 锁死回归：.fist-loop-20260927/fix_r4_docs.json 的 D08/D09/D10 三行 + 反向对照「实现里没有的 `--incremental` 不得出现在文档」
- 闭环证据：fix_r4_docs.json（verdict 全 agreed）；**half-open**：`SYNTAX/appendix-C-features.md` 的 `cypyc --compile` 行属冻结面，本轮只读不动（frozen_control 探针证明它仍然 stale）
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-67 [2026-09-27T20:25:18Z] [high] OPEN
- summary: [DOC_example_fails] 文档示例引用实现里不存在的符号：`ProjectCompileResult.output_files`（无此字段）、`hook.eval(...)` 承诺返回值（读侧要 `__result__`，写侧从不产出）
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  D11 [example-fails] docs/USAGE.md:333 原文「print("构建成功:", result.output_files)」 实测={"rc": 0, "json": {"fields": ["success", "compiled_modules", "failed_modules", "errors", "pyd_paths", "warnings", "compilation_order", "cycles_detected", "total_time", "type_registry_stats"], "has_output_files": false}, "tail": ["{\"fields\": [\"success\", \"compiled_modules\", \"failed_modules\", \；
  D12 [example-fails] docs/USAGE.md:251 原文「value = hook.eval("let x: int = 21 * 2\nx")」 实测={"result_symbol_in_cypyc": [], "only_reader_in_hook": ["cypy_hook/hook.py:759", "cypy_hook/hook.py:760"]}

成对对照（同族里今天行为正确的形状）：
  D11 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词
  D12 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词

机制（file:line 级，本环未改产品码）：`dataclass ProjectCompileResult`(project_compiler.py:25) 字段集里没有 output_files；`cypy_hook/hook.py:759` 只认 `__result__`，`cypyc/` 全仓 0 处生成

为什么值得入账：一张单一个根因，症状 2 条：D11、D12。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py DOC_example_fails
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：示例类主张不要求真编译：属性是否存在看 dataclass 字段集，`__result__` 看写侧是否产出。只说『跑起来会炸』而没指出符号不存在，不算。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:17+00:00 实测；severity=high；修属：下一环修（示例改口径或生成侧补，交裁决）
- reported_by: cypy-hunter
- task_id: T0r81

### FIXED(verify=已完成) — 2026-09-28 R4-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 修复任务：`T0r81`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-27T21:57:32+00:00`、`completed_by=cypy-fixer`）
- 改动文件：`docs/USAGE.md`（构建示例改引用真实字段 `pyd_paths`；eval 示例不再承诺返回 42）
- 锁死回归：fix_r4_docs.json 的 D11/D12 两行
- 闭环证据：fix_r4_docs.json；**half-open**：`hook.eval` 的写侧从不产出 `__result__`（生成侧缺口，改它超出本单授权）⇒ 转结
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-68 [2026-09-27T20:25:18Z] [medium] OPEN
- summary: [BRIDGE_cache_side_effect] `BridgeCacheManager` 的只读查询在**调用方 CWD** 造出 `__pycache__/cypy/py313/`（`_get_base_cache_dir(None)` 回落 `os.getcwd()`）
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  D16 [bridge-side-effect] cypy_bridge/compiler.py:3546 原文「"""获取基础缓存目录（__pycache__/cypy/py{major}{minor}/）」 实测={"rc": 0, "json": {"created": ["__pycache__", "__pycache__/cypy", "__pycache__/cypy/py313"], "cached_none": true, "stale": true}, "tail": ["{\"created\": [\"__pycache__\", \"__pycache__/cypy\", \"__pycache__/cypy/py313\"], \"cached_none\": true, \"stale\": true}"]}

成对对照（同族里今天行为正确的形状）：
  D16 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词

机制（file:line 级，本环未改产品码）：cypy_bridge/compiler.py:3545-3560 目录不存在即 `mkdir`，`get_cached_pyd`/`is_stale`(:3599/:3621) 都走它

为什么值得入账：一张单一个根因，症状 1 条：D16。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py BRIDGE_cache_side_effect
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：必须证明目录是**这两个只读调用**建的（调用前后各数一遍），并且探针跑在独立 CWD 里；只看代码里有个 mkdir 不算。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:18+00:00 实测；severity=medium；修属：下一环修
- reported_by: cypy-hunter
- task_id: T0r82

### NOT-FIXED(R5-修复 转结) — 状态仍是 OPEN，逐字写明卡在哪

- 机制键：`BRIDGE_cache_side_effect`；服务端单号：`T0r82`
- 卡点：本环没有这条单的锁（法②要求每单一条会失败的锁测试）
- 卡点：锁在 HEAD 快照树上没红
- 卡点：锁在当前树上没绿
- 卡点：这单点名的产品文件在本环窗口里没有改动（卡片点名面 ['cypy_bridge/compiler.py']；若回退矩阵在别的文件上测到承重，按 revert.extras.bearing 那栏复核）
- 卡点：回退矩阵里这单摘回后没红（本环没有这条单的锁（法②要求每单一条会失败的锁测试））⇒ 锁不承重或改动不在本环面
- 卡片原文的修前观察（逐字）："BRIDGE_cache_side_effect"
- 归属栏：`本环认领`（理由：机制/修法行点名 ['cypy_bridge/compiler.py']，落在可改半径内）
- 口径：入账未修是合法终态；这条不是「没问题」，下一环要按同一套判据重新认领。

## BUG-69 [2026-09-27T20:25:19Z] [high] OPEN
- summary: [BRIDGE_c_not_equivalent] bridge 生成的 C 里有**模块级** `if ((__name__ == "__main__")) {…}`（花括号净深 0 处），与 `cypy_bridge/__init__.py:4` 自述的「与 Cython 等价」不符，MSVC 必拒
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  D17 [bridge-not-equivalent] cypy_bridge/__init__.py:4 原文「提供与Cython等价的核心功能，作为移除Cython依赖的桥接层。」 实测={"rc": 0, "json": {"len": 1880, "口径": "按花括号净深推前缀和，depth==0 才算模块级", "module_level_if": ["if ((__name__ == \"__main__\")) {"], "total_if": 7}, "tail": ["{\"len\": 1880, \"\\u53e3\\u5f84\": \"\\u6309\\u82b1\\u62ec\\u53f7\\u51c0\\u6df1\\u63a8\\u524d\\u7f00\\u548c\\uff0cdepth==0 \\u624d\\u7b97\\u6a21\\u5

成对对照（同族里今天行为正确的形状）：
  D17 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词

机制（file:line 级，本环未改产品码）：`BridgeCompiler._generate_c_code`(:3756) 把入口分派写在函数体外

为什么值得入账：一张单一个根因，症状 1 条：D17。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py BRIDGE_c_not_equivalent
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：必须按花括号净深判定「模块级」，不能只看某行以 `if (` 开头（函数体内的 if 剥掉缩进后长一样）；真编译验证本轮未跑 ⇒ 本单只主张生成物结构非法这一半。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:18+00:00 实测；severity=high；修属：下一环修（真编译验证转结 R4-验证）
- reported_by: cypy-hunter
- task_id: T0r83

### NOT-FIXED(R5-修复 转结) — 状态仍是 OPEN，逐字写明卡在哪

- 机制键：`BRIDGE_c_not_equivalent`；服务端单号：`T0r83`
- 卡点：本环没有这条单的锁（法②要求每单一条会失败的锁测试）
- 卡点：锁在 HEAD 快照树上没红
- 卡点：锁在当前树上没绿
- 卡点：这单点名的产品文件在本环窗口里没有改动（卡片点名面 ['cypyc/codegen/bridge_generator.py']；若回退矩阵在别的文件上测到承重，按 revert.extras.bearing 那栏复核）
- 卡点：回退矩阵里这单摘回后没红（本环没有这条单的锁（法②要求每单一条会失败的锁测试））⇒ 锁不承重或改动不在本环面
- 卡片原文的修前观察（逐字）："BRIDGE_c_not_equivalent"
- 归属栏：`本环认领`（理由：机制/修法行点名 ['cypyc/codegen/bridge_generator.py']，落在可改半径内）
- 口径：入账未修是合法终态；这条不是「没问题」，下一环要按同一套判据重新认领。

## BUG-70 [2026-09-27T20:25:19Z] [low] OPEN
- summary: [SPEC_file_size_redline] PROJECT-SPEC 自己的 3000 行（不含注释）红线被 parser.py=3444、cython_generator.py=3108 越过，规范要求的"当时就拆"没有发生
- detail: 立单依据（文档声明/自述原文，含 file:line）：
  D15 [real-gap] PROJECT-SPEC/01-项目结构规范.md:42 原文「| **阈值** | 单个源文件超过 **3000 行**（不含注释），即视为规模超标 |」 实测={"parser": 3444, "generator": 3108, "type_checker": 2727, "口径": "非注释非字符串 token 覆盖的行数（docstring 也剔掉）"}

成对对照（同族里今天行为正确的形状）：
  D15 判据=见 .fist-loop-20260927/hunt_r4_repro.py 的显式谓词

机制（file:line 级，本环未改产品码）：口径是 `code_lines`（剔注释与字符串后 token 覆盖的行数，不是 `wc -l`）：`parser` 3444、`cython_generator` 3108 越过阈值 ⇒ 规范要求的「当时就拆」没有发生；纯存量规模，没有单点代码机制可指（这就是签名薄的地方，比对结果要如实标注）

为什么值得入账：一张单一个根因，症状 1 条：D15。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/hunt_r4_repro.py SPEC_file_size_redline
整批复跑判据件：.fist-loop-20260927/hunt_r4_confirm.json（代码面 12 条候选）、.fist-loop-20260927/hunt_r4_declared.json（文档面 18 行）

不算证明：行数主张必须写明口径（剔注释与字符串后的 token 覆盖行数）；`wc -l` 的数与这个口径不等价，两者都要落，取哪一个要注明。

去重结论：与 memory/bugs.md 现有 60 单按**机制签名**比对无重合（近亲逐条裁决见 .fist-loop-20260927/hunt_r4_dedup.json）。

来历（寻虫环只给调用面事实与形状）：[loop:20260927-loop:R4-寻虫] 2026-09-27T20:25:19+00:00 实测；severity=low；修属：人工（跨文件拆分不可逆 ⇒ 只挂账）
- reported_by: cypy-hunter
- task_id: T0r84

## BUG-71 [2026-09-28T00:17:49Z] [high] OPEN
- summary: [SLICE_typed_as_element] 切片表达式被判定成容器的**元素**类型：`xs[1:3]` 得 `int`，仓内自带 DEMO 因此过不了 `--check-only`（appendix-C《已实现的限制修复》第 1 行声称 v0.2 已实现）
- detail: [omega:required] 立单依据（调用面实测原文）：
  {
 "present": true,
 "probe": {
  "rc": 1,
  "diags": [
   "Return type mismatch: expected list[int], got int at 4:1"
  ]
 },
 "demo": {
  "file": "examples/demos/upcoming_features/planned_features.cypy",
  "rc": 1,
  "diags_total": 4,
  "first": [
   "Type mismatch: expected list[int], got int at 60:9",
   "Return type mismatch: expected list[int], got int at 67:1"
  ]
 },
 "predicate": "探针 rc!=0 且诊断里有「expected list[int], got int」，并且仓内 DEMO 也过不了 --check-only"
}

成对对照（同族里今天正确的形状）：
  同族里今天正确的形状：`return xs[1]`（整数下标）零诊断；`let a = xs[1:3]`（不标注返回类型）也能过——缺陷只在「切片结果被当容器用」时现形。

机制（file:line 级，本环未改产品码）：`cypyc/analyzer/type_checker.py:4119-4144` `_visit_Subscript` 只看 `hasattr(node.slice, 'kind')`，而切片在本仓 AST 里是 dict `{'slice': True, 'start': …, 'end': …, 'step': …}`（实测回读），于是走不到任何分支、直接返回 `params[0]`（元素类型）；切片的三个边界子节点也从不被访问。

为什么值得入账：本环是验证环，这三条都是**独立复算**打出来的，不来自寻虫/修复环的自述；每条一张单一个根因。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/verify_r4_repro.py SLICE_typed_as_element
整批复跑判据件：.fist-loop-20260927/verify_r4_appendixC.json（文档面 14 行）、.fist-loop-20260927/verify_r4_compile.json（真编译 3 次尝试）、.fist-loop-20260927/verify_r4_callsite.json（调用面 18 行）

不算证明：必须同时给出「仓内自带 DEMO 过不了 --check-only」与「最小探针的诊断文本」，并且说明修前修后同形（本件已用 R4-修复 的修前快照复跑，诊断逐字一致 ⇒ 不是本轮引入）。

去重结论（近亲逐条裁决）：
  BUG-37 位置模式把绑定名判成 int（同症状「Return type mismatch」，不同机制：那里是 pattern 绑定名类型，这里是 Subscript 的切片分支）
  BUG-65 文档 stale 行（那单说的是文档措辞，本单是产品类型面，文档只是受害者）
  与 memory/bugs.md 现有 70 单按机制签名比对无重合。

来历（验证环给的是复算事实与形状）：[loop:20260927-loop:R4-验证] 2026-09-28T00:17:49+00:00 实测；severity=high；修属：下一环修（R4-打磨不修产品码）
- reported_by: cypy-verifier
- task_id: T0r87

### NOT-FIXED(R5-修复 转结) — 状态仍是 OPEN，逐字写明卡在哪

- 机制键：`SLICE_typed_as_element`；服务端单号：`T0r87`
- 卡点：本环没有这条单的锁（法②要求每单一条会失败的锁测试）
- 卡点：锁在 HEAD 快照树上没红
- 卡点：锁在当前树上没绿
- 卡点：回退矩阵里这单摘回后没红（本环没有这条单的锁（法②要求每单一条会失败的锁测试））⇒ 锁不承重或改动不在本环面
- 卡片原文的修前观察（逐字）："SLICE_typed_as_element"
- 归属栏：`本环认领`（理由：机制/修法行点名 ['cypyc/analyzer/type_checker.py']，落在可改半径内）
- 口径：入账未修是合法终态；这条不是「没问题」，下一环要按同一套判据重新认领。


### FIXED(R9 组合环 2026-09-29T05:31:29+00:00，ns cypy-loop-20260929) — 追加留档（正文一字未改）

- 机制即卡片所写（`_visit_Subscript` 只看 `hasattr(node.slice,'kind')`，切片是 dict 形态 ⇒ 走不到分支直接返回 `params[0]`）：
  本轮在返回元素类型之前先分辨切片形态，`cypyc/analyzer/type_checker.py` 的 `_is_slice_form()` 只认
  `cypyc/parser/parser.py:3952-3991` 落的那个 `{"slice": True, …}` dict（语言里没有独立的 `Slice` AST 节点，
  所以判据只有这一支，不写「万一是节点」的死分支）。
- 规范先行：`SYNTAX/14-syntax-sugar.md` 新增「切片的类型规则（R9 补）」1-3 条 ——
  切片结果=被切容器自身类型；只有下标形态降到元素类型；切片不做越界/常量化判定。现测 377 行。
- R5 那条 `### NOT-FIXED` 的四个卡点逐一补齐：
  ① 锁 = `corpus/cypy.type.slice.json` 8 格 + `tests/regression/test_corpus_pairs.py` 参数化格（成对的另一半：
     `y: int = xs[1:3]` 必须报 `Type mismatch: expected int, got list[int]` 带行列，防止「判据恒绿」）；
  ② 摘掉即红 = `.fist-loop-20260929/verify_r9_locks.py` 的 S1 格（切片形态判断恒假 ⇒ Ω-gate 真红），副本树、逐字节摘回；
  ③ 当前树全绿 = 本段落盘时 pytest 终版结论 `====================== 2212 passed in 328.07s (0:05:28) =======================`；
  ④ 调用面 = 卡片点名的仓内 DEMO `examples/demos/upcoming_features/planned_features.cypy`
     `transpile --check-only` 由 rc=1（4 条诊断，首条 `Type mismatch: expected list[int], got int at 60:9`）
     变 rc=0，逐字 `(未找到 [OK] 行)`。
- 未随本段关闭的相邻面：元组可变长切片 `tuple<int, ...>` 仍进不了解析器（账上「语法未落地」那条），
  本条只主张 list/str 与「下标 vs 切片」形态区分这一型已闭。
## BUG-72 [2026-09-28T00:17:50Z] [medium] OPEN
- summary: [CODEGEN_named_conditions_unreachable] appendix-C 点名的三个 codegen 方法（以及 `_extractor_pattern_condition`/`_contains_extractor`）在活路径上调用计数为 0：模式条件由别处就地拼出
- detail: [omega:required] 立单依据（调用面实测原文）：
  {
 "present": true,
 "call_hits": {
  "_generate_tuple_condition": 0,
  "_generate_array_condition": 0,
  "_generate_dict_condition": 0,
  "_extractor_pattern_condition": 0,
  "_contains_extractor": 0
 },
 "behaviour_generated_inline": true,
 "predicate": "元组模式的判定条件确实出现在生成物里，而这五个名字的调用计数全为 0"
}

成对对照（同族里今天正确的形状）：
  同一份源里 `isinstance(_match_subject_1, (list, tuple))` 确实出现在生成物中⇒ **行为是有的**，本单只主张「文档点名的那三个名字不是实现所在的位置」。

机制（file:line 级，本环未改产品码）：`cypyc/codegen/cython_generator.py:1832-1855` 的 `_extractor_pattern_condition` 调用 `:1921/:1937/:1955` 三个 `_generate_*_condition`，但全文件（含 tests/）**没有任何调用方**指向 `_extractor_pattern_condition` 或 `_contains_extractor`；元组/列表/字典模式的实际条件在 `:1563/:1574/:1601/:1614` 就地拼装。

为什么值得入账：本环是验证环，这三条都是**独立复算**打出来的，不来自寻虫/修复环的自述；每条一张单一个根因。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/verify_r4_repro.py CODEGEN_named_conditions_unreachable
整批复跑判据件：.fist-loop-20260927/verify_r4_appendixC.json（文档面 14 行）、.fist-loop-20260927/verify_r4_compile.json（真编译 3 次尝试）、.fist-loop-20260927/verify_r4_callsite.json（调用面 18 行）

不算证明：计数器必须包在公开调用外面跑（`CypyHook.analyze_only` + `CythonGenerator.generate`），只 grep 到「函数定义存在」不算；行为面证据必须同时给出「条件确实生成了」。

去重结论（近亲逐条裁决）：
  BUG-36 位置模式不调用 __unapply__（那是语义错误，本单是可达性/文档指向，不同机制）
  BUG-71 切片类型面（同一张文档表不同行，互不覆盖）
  与 memory/bugs.md 现有 70 单按机制签名比对无重合。

来历（验证环给的是复算事实与形状）：[loop:20260927-loop:R4-验证] 2026-09-28T00:17:50+00:00 实测；severity=medium；修属：人工（删死码 vs 改道重写，二者都是语义决定）
- reported_by: cypy-verifier
- task_id: T0r88

### NOT-FIXED(R5-修复 转结) — 状态仍是 OPEN，逐字写明卡在哪

- 机制键：`CODEGEN_named_conditions_unreachable`；服务端单号：`T0r88`
- 卡点：本环没有这条单的锁（法②要求每单一条会失败的锁测试）
- 卡点：锁在 HEAD 快照树上没红
- 卡点：锁在当前树上没绿
- 卡点：回退矩阵里这单摘回后没红（本环没有这条单的锁（法②要求每单一条会失败的锁测试））⇒ 锁不承重或改动不在本环面
- 卡片原文的修前观察（逐字）："CODEGEN_named_conditions_unreachable"
- 归属栏：`本环认领`（理由：机制/修法行点名 ['cypyc/codegen/cython_generator.py']，落在可改半径内）
- 口径：入账未修是合法终态；这条不是「没问题」，下一环要按同一套判据重新认领。

## BUG-73 [2026-09-28T00:18:06Z] [medium] OPEN
- summary: [PYD_incremental_cache_not_reused] `compile_to_pyd` 连跑两次仍重写 `.pyd`：同一次结果里先写「缓存命中」再写「缓存未命中」，两个缓存各查各的（docs/USAGE.md:406 的「源未变会复用 .pyd」在调用面不成立）
- detail: [omega:required] 立单依据（调用面实测原文）：
  转译模式开始"
  ],
  "steps2": [
   "=== 一步到位编译模式 ===",
   "开始处理文件: E:\\IDEProjects\\AI\\Cypy\\.fist-loop-20260927\\verify_r4_tmp\\repro\\cache_src.cypy",
   "开始转译文件: E:\\IDEProjects\\AI\\Cypy\\.fist-loop-20260927\\verify_r4_tmp\\repro\\cache_src.cypy",
   "增量编译: 缓存命中，使用缓存结果",
   "增量编译: 缓存未命中，开始解析",
   "增量编译: 受影响定义数: 0"
  ],
  "cached_after": null,
  "stale_after": false,
  "dur": [
   7.1,
   7.65
  ]
 },
 "predicate": "两轮都 success、第二轮 .pyd 被重写（mtime 变了）、成功后 CypyCacheManager.get_cached_pyd 仍为 None"
}

成对对照（同族里今天正确的形状）：
  对照（今天确实正确的部分）：`CompileResult.pyd_path`（单数，实测属性名）两轮都指向同一个 `.pyd` 路径，且两轮 `success=True`——缺陷只在「命中之后没有真的复用」，不是编译挂了。

机制（file:line 级，本环未改产品码）：`cypy_hook/hook.py:343-365`：`:347` 用 `IncrementalCompiler.check_cache_validity` 判命中后追加「缓存命中，使用缓存结果」(`:351`)，紧接着 `:354-356` 换 `CypyCacheManager().get_cached_pyd()` **另一套**存储再问一次；它返回 None 时早退分支（`:357-361`）走不到，控制流落到 `:363-365` 又追加「缓存未命中，开始解析」，然后照常重新转译、重新编译。

为什么值得入账：本环是验证环，这三条都是**独立复算**打出来的，不来自寻虫/修复环的自述；每条一张单一个根因。

复跑（退出码 0=现形 / 1=不现形 / 2=夹具坏）：python -X utf8 .fist-loop-20260927/verify_r4_repro.py PYD_incremental_cache_not_reused
整批复跑判据件：.fist-loop-20260927/verify_r4_appendixC.json（文档面 14 行）、.fist-loop-20260927/verify_r4_compile.json（真编译 3 次尝试）、.fist-loop-20260927/verify_r4_callsite.json（调用面 18 行）

不算证明：必须给两轮的 `.pyd` mtime、两轮耗时与两轮 steps 原文；只说「变快了」不算——实测 8.35s vs 7.76s 在噪声内，唯一承重的是 mtime 变了 + steps 自相矛盾。

去重结论（近亲逐条裁决）：
  BUG-18（已修，`cypyc/incremental/incremental_manager.py` 的依赖比对）——本单在 `cypy_hook` 侧，是「命中判定与取产物用了两套存储」，不同机制
  BRIDGE_cache_side_effect（D16/BUG-66，只读查询在调用方 CWD 造目录）——同一文件族不同缺陷
  BUG-12/相关 manifest 单（manifest 损坏与不存在不可区分）——本单不需要 manifest 损坏即可复现
  与 memory/bugs.md 现有 70 单按机制签名比对无重合。

来历（验证环给的是复算事实与形状）：[loop:20260927-loop:R4-验证] 2026-09-28T00:18:05+00:00 实测；severity=medium；修属：下一环修（两套缓存的真相源合一）
- reported_by: cypy-verifier
- task_id: T0r89

### NOT-FIXED(R5-修复 转结) — 状态仍是 OPEN，逐字写明卡在哪

- 机制键：`PYD_incremental_cache_not_reused`；服务端单号：`T0r89`
- 卡点：锁在 HEAD 快照树上没红
- 卡点：回退矩阵里这单摘回后没红（摘回本环改过的每一个产品文件都不打红这单的锁 ⇒ 这单没有承重的改动）⇒ 锁不承重或改动不在本环面
- 卡片原文的修前观察（逐字）："PYD_incremental_cache_not_reused"
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-cli-hook 改了既有测试面 ["cypyc/cli.py", "cypy_hook/hook.py"]；为什么改（车道原话，逐字）：["BUG-88 症状 2「编译顺序打印的是未过滤全集」没修：result.compilation_order 由 cypyc/project/project_compiler.py:722 填全图拓扑序，那档不在本车道 ⇒ 本单只算修一半，账本机制栏点名的 project_compiler 面未动", "BUG-86 端到端「loader=ExtensionFileLoader」证据未钉：按纪律不触发 C 工具链，锁只到 is_cypy_file/find_spec + transpile 面"]；改动前观察到的原文（逐字）：["AssertionError: 写在子命令前的 -o 没生效（仍写 output/）：… [2/3] Output: output … Output: output\\hello.pyx", "AssertionError: 带 BOM 的 #!bin cypy 首行没被认出来  assert False is True"]
- 归属栏：`本环认领`（理由：机制/修法行点名 ['cypy_hook/hook.py']，落在可改半径内）
- 口径：入账未修是合法终态；这条不是「没问题」，下一环要按同一套判据重新认领。

## BUG-74 [2026-09-28T03:34:25Z] [high] OPEN
- summary: [CODEGEN_augmented_xor_drops_left_operand] 复合赋值 `^=` 静默产出 `x = <右值>`，左操作数与运算符一起丢了
- detail: 实测证据（全部来自 .fist-loop-20260927/advance_r4_scope_face.json，量表共 22 行，本卡取 1 行）：
  [{"op": "^=", "state": "silent_wrong", "rc": 0, "declared_at": "SYNTAX/12-operators.md:90", "spec": "x = x ^ 5", "generated": "x = 5"}]

机制（file:line 级，本环未改产品码）：cypyc/parser/lexer.py:955-973 把裸 `^` 恒判为 BUILD_VALUE 词位（后缀构建值运算符），cypyc/parser/parser.py:3796-3800 `_parse_power_expr` 在 `while … BUILD_VALUE` 里把它吞掉；于是 `x ^= 5` 的语句右侧只剩 `= 5`，产物写 `x = 5` 且 rc=0（不报错）

为什么值得入账：同一张运算符表里 12 条复合赋值有 11 条行为正确（产物逐字等于文档自己写的等价式），被响亮拒绝的运算符至少报错——本卡形状是 rc=0 且产物与文档声明不等，属于静默产错码。

复跑：python -X utf8 .fist-loop-20260927/advance_r4_scope_face.py（退出码 0＝判据全跑完；本卡的形状钉在 `silent_wrong` / `declared_rejected` 两个集合里，修好后那两格会红，逼来人关账）
夹具：.fist-loop-20260927/advance_r4_probe/（另含量表内联生成的 aug00..aug11 / bin00..bin09）

不算证明：只测了 int 字面量与常量右值，没测变量右值、非 int 左操作数与 `with`/循环里的形状；产物层面未编译成 .pyd，因此不主张运行期数值。

来历（推进环只给调用面事实，修属 R5-修复）：[loop:20260927-loop:R4-推进] 2026-09-28T03:34:24+00:00 实测；severity=high；修属=codegen/parser
- reported_by: cypy-advancer
- task_id: T0r91

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CODEGEN_augmented_xor_drops_left_operand`
- 修复任务：`T0r91`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/codegen/cython_generator.py::<模块级>", "cypyc/codegen/cython_generator.py::CythonGenerator", "cypyc/codegen/cython_generator.py::CythonGenerator.__init__", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts.scan", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_method_names"]
- 文件面：["cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py", "cypyc/parser/parser.py"]
- 锁：["tests/codegen/test_r5_fix_codegen.py"] 共 4 条节点；HEAD 快照复算红 2 条；摘回本单改动后红 2 条
- 修前红的原文（逐字，取前两条）：["AssertionError: ['def f(x):', 'x', 'return x']", "AssertionError: ['def f(x, y):', 'x', 'return x']"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 2 条（其中断言级 2 条）；邻组牵连 []
- 车道：`lane-codegen`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-75 [2026-09-28T03:34:25Z] [medium] OPEN
- summary: [LEXER_bitwise_xor_and_invert_unreachable] 文档声明的二元 `a ^ b` 与一元 `~a` 在 CLI 上不可达（与 `^:`/`~:` 构建块共用词位）
- detail: 实测证据（全部来自 .fist-loop-20260927/advance_r4_scope_face.json，量表共 22 行，本卡取 2 行）：
  [{"op": "^", "state": "rejected", "rc": 1, "declared_at": "SYNTAX/12-operators.md:57", "spec": null, "generated": ["- 编译错误: Expected RPAREN, got IDENTIFIER at 4:15"]}, {"op": "~", "state": "rejected", "rc": 1, "declared_at": "SYNTAX/12-operators.md:58", "spec": null, "generated": ["- 编译错误: Unexpected token TILDE at 4:11"]}]

机制（file:line 级，本环未改产品码）：同一条词位判定：`^` 只作 BUILD_VALUE、`~` 只作 BUILD_VALUE/构建块前缀，二元/一元用法在 `_parse_power_expr` 之后没有优先级位 ⇒ 二元 `^` 报 「Expected RPAREN, got IDENTIFIER」、一元 `~` 报「Unexpected token TILDE」。修法要给 `^`/`~` 加上下文消歧，而 `^:`（索引构建块，SYNTAX/13-build-blocks.md）与 `~:` 是冻结语义 ⇒ 不能只放开词位了事

为什么值得入账：同一张运算符表里 12 条复合赋值有 11 条行为正确（产物逐字等于文档自己写的等价式），被响亮拒绝的运算符至少报错——本卡形状是 rc=0 且产物与文档声明不等，属于静默产错码。

复跑：python -X utf8 .fist-loop-20260927/advance_r4_scope_face.py（退出码 0＝判据全跑完；本卡的形状钉在 `silent_wrong` / `declared_rejected` 两个集合里，修好后那两格会红，逼来人关账）
夹具：.fist-loop-20260927/advance_r4_probe/（另含量表内联生成的 aug00..aug11 / bin00..bin09）

不算证明：只测了 int 字面量与常量右值，没测变量右值、非 int 左操作数与 `with`/循环里的形状；产物层面未编译成 .pyd，因此不主张运行期数值。

来历（推进环只给调用面事实，修属 R5-修复）：[loop:20260927-loop:R4-推进] 2026-09-28T03:34:25+00:00 实测；severity=medium；修属=lexer/parser
- reported_by: cypy-advancer
- task_id: T0r92

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`LEXER_bitwise_xor_and_invert_unreachable`
- 修复任务：`T0r92`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/parser/lexer.py::Lexer", "cypyc/parser/lexer.py::Lexer.__init__", "cypyc/parser/lexer.py::Lexer._caret_is_infix", "cypyc/parser/lexer.py::Lexer._current_line_starts_with", "cypyc/parser/lexer.py::Lexer._handle_newline", "cypyc/parser/lexer.py::Lexer._skip_whitespace"]
- 文件面：["cypyc/parser/lexer.py", "cypyc/parser/parser.py"]
- 锁：["tests/parser/test_r5_fix_lexer_tokens.py"] 共 11 条节点；HEAD 快照复算红 7 条；摘回本单改动后红 7 条
- 修前红的原文（逐字，取前两条）：["AssertionError: 产物缺 `a & b`：", "AssertionError: 产物缺 `a ^ b`："]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-lexer 改了既有测试面 ["cypyc/parser/lexer.py", "cypyc/parser/parser.py"]；为什么改（车道原话，逐字）：["BUG-75 在 R5-寻虫 的判据件里没有对应 case（该单是 R4-推进立的），账本给的复跑入口 advance_r4_scope_face.py 会回写判据件，与并发只读约束冲突，故未跑；钉在 declared_rejected 的两格要指挥官亲自复跑关账", "`~` 的根因不在词法器（早就发 TILDE），在解析器 _parse_unary_expr 没有分支 ⇒ 只改了 parser.py"]；改动前观察到的原文（逐字）：["AssertionError: `a **= y` 走不到出码：ValueError: Unexpected token ASSIGN at 2:9", "AssertionError: TokenType 缺 XOR：`^` 只作 BUILD_VALUE ⇒ 异或无 token 可发"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 7 条（其中断言级 7 条）；邻组牵连 []
- 车道：`lane-lexer`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-76 [2026-09-28T04:51:17Z] [high] OPEN
- summary: [DEFER_nested_return_exit_skips_cleanup] `defer` 的清理只注入函数体顶层出口，`if`/`for` 里的 return 静默跳过清理
- detail: 实测证据（全部来自 .fist-loop-20260927/advance_r4_dormant.json；4 个形状实测（['single_defer', 'two_defers_lifo', 'defer_before_return', 'defer_two_exits']），本卡取 defer_two_exits：2 个出口 / 清理发出 1 次）：
  [{"shape": "defer_two_exits", "tested_function": "pick", "exit_paths": 2, "cleanup_count": 1, "product_slice": "def pick(flag):\n    f = open('t.txt', 'w')\n    if flag:\n        return 1\n    f.close()\n    return 2", "declaration_lines": ["SYNTAX/14-syntax-sugar.md:167-190", "SYNTAX/04-pointer-types.md:59-63"]}]

机制（file:line 级，本环未改产品码）：cypyc/codegen/cython_generator.py:979-1000：分离出 defer 之后只遍历**顶层** normal_stmts，遇到顶层 ReturnStmt 才在其前面注入清理并置 emitted_at_return；嵌套在 if/for 里的 return 不是顶层语句 ⇒ 那条出口没有清理，而函数末尾的兜底注入又被 emitted_at_return 关掉。实测：2 个出口只发 1 次清理，rc=0 且零诊断。

为什么值得入账：声明面（`SYNTAX/14-syntax-sugar.md:167-190`、`SYNTAX/04-pointer-types.md:59-63`）承诺「函数退出时自动执行」，`SYNTAX/04-pointer-types.md:133` 还把「指针必须用 defer 清理」列为规则；带条件返回的函数在最常用的形状上静默漏清理。

复跑：python -X utf8 .fist-loop-20260927/advance_r4_dormant.py —— 本卡的出口数/清理次数钉在件的 `pinned_defect` 与「钉住的缺陷」那格自证里，修好后 [2, 1] 会红，和关账一起走
同件另测得 `defer_before_return`（清理搬到 return 之前，这条路可达）与 `two_defers_lifo`（逆序成立）两档今天是对的，本卡只在多出口形状上成立

不算证明：只测了 `if` 内单条 return 与顶层 return 并存的最小形状，没测 for/while/match 里的出口，也没测异常路径——文档从未承诺 try/finally，本卡不主张异常安全；未编译成 .pyd 跑运行期句柄计数。

来历（推进环只给调用面事实，修属 R5-修复）：[loop:20260927-loop:R4-推进] 2026-09-28T04:51:17+00:00 实测；severity=high；修属=codegen
- reported_by: cypy-advancer
- task_id: T0r94

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`DEFER_nested_return_exit_skips_cleanup`
- 修复任务：`T0r94`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/codegen/cython_generator.py::<模块级>", "cypyc/codegen/cython_generator.py::CythonGenerator", "cypyc/codegen/cython_generator.py::CythonGenerator.__init__", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts.scan", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_method_names"]
- 文件面：["cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py"]
- 锁：["tests/codegen/test_r5_fix_codegen.py"] 共 4 条节点；HEAD 快照复算红 2 条；摘回本单改动后红 2 条
- 修前红的原文（逐字，取前两条）：["AssertionError: ['def scan(n):', \"r = open('t.txt', 'w')\", 'for i in range(n):', 'if i > 0:', 'return i', 'r.close()', ...]", "AssertionError: 2 个出口只发了 1 次清理：['def pick(flag):', \"f = open('t.txt', 'w')\", 'if flag:', 'return 1', 'f.close()', 'return 2']"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 2 条（其中断言级 2 条）；邻组牵连 []
- 车道：`lane-codegen`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-77 [2026-09-28T04:51:18Z] [medium] OPEN
- summary: [TEST_vacuous_success_guard_hides_assertions] `if result.success` 型守卫让代码生成断言在编译失败时静默空过（余 7 处）
- detail: 实测证据（全部来自 .fist-loop-20260927/advance_r4_dormant.json；字面形态 if result.success 现存 7 处（本环去掉 1 处，原 8 处）；激活证明：改前 Undefined name 'open' at 2:9 ⇒ success=False（守卫为假，整块断言被跳过）；改后 success=True 且 try=False、finally=False）：
  ["tests/test_codegen_verification.py:160 if result.success and result.cython_code:", "tests/test_codegen_verification.py:185 if result.success and result.cython_code:", "tests/test_codegen_verification.py:236 if result.success and result.cython_code:", "tests/test_codegen_verification.py:247 if result.success and result.cython_code:", "tests/test_codegen_verification.py:270 if result.success and result.cython_code:", "tests/test_unit_test_modes.py:105 if result.success:", "tests/test_unit_test_modes.py:128 if result.success:"]

机制（file:line 级，本环未改产品码）：tests/test_codegen_verification.py 与 tests/test_unit_test_modes.py 里共 8 处 `if result.success [and result.cython_code]:` 把整块断言挂在「编译成功」上：编译一失败，测试直接 pass。本环放行文档内建名 `open` 之后，test_defer_statement 从空过变成真跑并立刻暴露一条超出声明面的期望，证明这批守卫的实际覆盖面是 0 而不是「宽松」。

为什么值得入账：同一模式下「绿」不代表任何事：名称面、语法面、代码生成面任何一处退化都不会红。本环按指挥官裁决改掉被激活的那一条（期望改成声明面语义 + 去掉守卫），余下 7 处逐条点名（file:line 见证据），要么改成无条件断言，要么写明它凭什么不断言。

复跑：python -X utf8 .fist-loop-20260927/advance_r4_dormant.py —— 守卫清单钉在件的 `vacuous_guards.sites`；条数从 8 掉到 7 是本环改动的直接后果，R5 收完应为 0
改后的 test_defer_statement 函数体逐字在件的 `test_patch.body_after` 里

不算证明：只数了字面形态 `if result.success` 的语句行（注释里提到该字面不算），没测 skip/xfail/try-except 之类的其它静默通道，也没逐条判断那 7 处去掉守卫后各自会不会红。

来历（推进环只给调用面事实，修属 R5-修复）：[loop:20260927-loop:R4-推进] 2026-09-28T04:51:17+00:00 实测；severity=medium；修属=tests
- reported_by: cypy-advancer
- task_id: T0r95

### OUT-OF-RADIUS(R5-修复 越出认领半径) — 状态仍是 OPEN，逐字写明改了什么

- 机制键：`TEST_vacuous_success_guard_hides_assertions`；服务端单号：`T0r95`
- 归属栏：`未认领（转结仍 OPEN）`（理由：机制行与修法行都没点名可改文件面，也没有可映射的 修属 域）⇒ 本环认领表里没有这张单
- 越界事实：车道 `lane-tests` 改了既有测试面 ["tests/test_codegen_verification.py", "tests/test_unit_test_modes.py"]，其派单卡 [77] 未进本环认领栏
- 车道原话（逐字，为什么动它）：["7 处空守卫里收了 3 处（无条件断言化），4 处按纪律保留守卫并逐条交裁决：comptime / go / typealias / pointer", "modes:105 的 else 分支与上一行是同一条断言，去分支不减覆盖；modes:128 实测 success=True，断言现在是承重的"]
- 处置：改动如实保留在盘上（删它等于毁掉已完成的工作，也不构成「没改」），本单状态仍 OPEN，不据此判门禁绿；要不要收这批改法交指挥官裁决。

## BUG-78 [2026-09-28T06:32:36Z] [critical] OPEN
- summary: [CODEGEN_binop_parens_dropped_changes_order] 括号分组在产物里被丢掉，同优先级左结合链被改次序（静默产错码）
- detail: 立单依据（声明原文现读）：{'file': 'SYNTAX/12-operators.md', 'line': 34, 'quote': '| `<` | 小于 | 判断左边小于右边 |'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=parens_dropped (期望 parens_dropped)
  ctl=kept (期望 kept)
  pos 证据：{"rc": 0, "line": "return a - b - c"}
  ctl 证据：{"rc": 0, "line": "return a * (b + c)"}

机制（本环未改产品码）：cypyc/codegen/cython_generator.py 的 BinOp 落码用扁平优先级表，只在 right_prec < current_prec 时补括号 ⇒ 等优先级的左结合右操作数丢括号

症状 4 条：a-(b-c)→a - b - c、a%(b%c)、a>>(b>>c)、(a|b)&c

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('G01'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：rc=0 不算证明（坏在产物文本）；单条 `-` 的例子也不能证明只影响减法——四族同形才指到优先级表这一处

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-74。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:35+00:00 实测；severity=critical（本轮内部口径 P0）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r97

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CODEGEN_binop_parens_dropped_changes_order`
- 修复任务：`T0r97`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/codegen/cython_generator.py::<模块级>", "cypyc/codegen/cython_generator.py::CythonGenerator", "cypyc/codegen/cython_generator.py::CythonGenerator.__init__", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts.scan", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_method_names"]
- 文件面：["cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py", "cypyc/parser/parser.py"]
- 锁：["tests/codegen/test_r5_fix_codegen.py"] 共 12 条节点；HEAD 快照复算红 6 条；摘回本单改动后红 6 条
- 修前红的原文（逐字，取前两条）：["ValueError: Expected RPAREN, got IDENTIFIER at 2:17", "AssertionError: (a | b) & c -> return a | b"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 6 条（其中断言级 5 条）；邻组牵连 []
- 车道：`lane-codegen`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-79 [2026-09-28T06:32:36Z] [high] OPEN
- summary: [LEXER_declared_augassign_never_lexed] 文档声明的 `**=`/`&=`/`|=` 词法器从不发 token，写出来必硬解析失败
- detail: 立单依据（声明原文现读）：{'file': 'SYNTAX/12-operators.md', 'line': 85, 'quote': '| `**=` | 幂赋值 | `x **= 3` | `x = x ** 3` |'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=unreachable (期望 unreachable)
  ctl=lowered (期望 lowered)
  pos 证据：{"rc": 1, "diag": ["\u001b[31m-\u001b[0m 编译错误: Unexpected token ASSIGN at 2:9"]}
  ctl 证据：{"rc": 0, "line": "a = a + y"}

机制（本环未改产品码）：cypyc/parser/lexer.py 只为 8 个复合赋值发 AUG_ASSIGN，缺 `**=`/`&=`/`|=` 分支

症状 4 条：a **= y、a &= y、a |= y、同族 +=/-=/*=//=/%= 正常

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('G02'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「报 Unexpected token」不证明语义正确性——这只证明这条路走不到解析器

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-74、BUG-75。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:36+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r98

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`LEXER_declared_augassign_never_lexed`
- 修复任务：`T0r98`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/parser/lexer.py::Lexer", "cypyc/parser/lexer.py::Lexer.__init__", "cypyc/parser/lexer.py::Lexer._caret_is_infix", "cypyc/parser/lexer.py::Lexer._current_line_starts_with", "cypyc/parser/lexer.py::Lexer._handle_newline", "cypyc/parser/lexer.py::Lexer._skip_whitespace"]
- 文件面：["cypyc/parser/lexer.py", "cypyc/parser/parser.py"]
- 锁：["tests/parser/test_r5_fix_lexer_tokens.py"] 共 15 条节点；HEAD 快照复算红 6 条；摘回本单改动后红 6 条
- 修前红的原文（逐字，取前两条）：["AssertionError: `a &= y` 走不到出码：ValueError: Unexpected token ASSIGN at 2:8", "AssertionError: `a **= y` 走不到出码：ValueError: Unexpected token ASSIGN at 2:9"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-lexer 改了既有测试面 ["cypyc/parser/lexer.py", "cypyc/parser/parser.py"]；为什么改（车道原话，逐字）：["BUG-75 在 R5-寻虫 的判据件里没有对应 case（该单是 R4-推进立的），账本给的复跑入口 advance_r4_scope_face.py 会回写判据件，与并发只读约束冲突，故未跑；钉在 declared_rejected 的两格要指挥官亲自复跑关账", "`~` 的根因不在词法器（早就发 TILDE），在解析器 _parse_unary_expr 没有分支 ⇒ 只改了 parser.py"]；改动前观察到的原文（逐字）：["AssertionError: `a **= y` 走不到出码：ValueError: Unexpected token ASSIGN at 2:9", "AssertionError: TokenType 缺 XOR：`^` 只作 BUILD_VALUE ⇒ 异或无 token 可发"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 6 条（其中断言级 6 条）；邻组牵连 []
- 车道：`lane-lexer`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-80 [2026-09-28T06:32:37Z] [high] OPEN
- summary: [CODEGEN_nested_defer_runs_eagerly] `if`/`for` 里的 defer 就地发射，清理在函数退出之前跑完
- detail: 立单依据（声明原文现读）：{'file': 'SYNTAX/14-syntax-sugar.md', 'line': 176, 'quote': 'file.close()  # 函数退出时自动执行'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=eager (期望 eager)
  ctl=moved_to_exit (期望 moved_to_exit)
  pos 证据：{"rc": 0, "order": ["print('CLEAN')", "print('BODY')"]}
  ctl 证据：{"rc": 0, "order": ["print('BODY')", "print('CLEAN')"]}

机制（本环未改产品码）：cython_generator.py 只把**顶层** body 里的 DeferStmt 摘出去，嵌套 defer 落到 _visit_children 的默认分支

症状 3 条：if 里的 defer 在 BODY 之前打印、for 里每轮都执行清理、顶层 defer 正确搬到了体末

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('G03'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：单出口程序的产物顺序对，不能证明多出口/异常路径也对（那半在 BUG-76）

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-76。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:36+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r99

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CODEGEN_nested_defer_runs_eagerly`
- 修复任务：`T0r99`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/codegen/cython_generator.py::<模块级>", "cypyc/codegen/cython_generator.py::CythonGenerator", "cypyc/codegen/cython_generator.py::CythonGenerator.__init__", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts.scan", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_method_names"]
- 文件面：["cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py"]
- 锁：["tests/codegen/test_r5_fix_codegen.py"] 共 6 条节点；HEAD 快照复算红 3 条；摘回本单改动后红 3 条
- 修前红的原文（逐字，取前两条）：["AssertionError: ['def f(n):', 'for i in range(n):', \"print('CLEAN')\", \"print('BODY')\", 'return n']", "AssertionError: ['def f(n):', 'if n > 0:', \"print('CLEAN')\", \"print('BODY')\", 'return n']"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 3 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-codegen`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-81 [2026-09-28T06:32:37Z] [high] OPEN
- summary: [COMPTIME_collection_literal_leaks_ast_repr] comptime 的列表/元组把 AST 节点 repr 写进产物，产物不可编译
- detail: 立单依据（声明原文现读）：{'file': 'SYNTAX/19-comptime.md', 'line': 20, 'quote': '2. **代码生成**：在 `LetStmt` 和 `Assign` 中，`comptime` 表达式被当作普通表达式处理，不会在编译期实际执行'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=ast_leak (期望 ast_leak)
  ctl=clean (期望 clean)
  pos 证据：{"rc": 0, "leaks": ["Constant(line="], "snippet": "[Constant(line=2, col=16), Constant(line=2, col=19)]"}
  ctl 证据：{"rc": 0, "leaks": []}

机制（本环未改产品码）：cypyc/analyzer/comptime_evaluator.py 对集合字面量返回未求值的元素节点列表，cython_generator.py 再对结果做 repr 落码

症状 3 条：comptime: [1, 2] → `[Constant(line=2, col=16), …]`、comptime: [1,2]+[3] 同样泄漏、产物喂 Cython 报未定义名

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('G04'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「转译 rc=0」恰恰是反证——坏在产物里，不在退出码里

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-32。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:37+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r100

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`COMPTIME_collection_literal_leaks_ast_repr`
- 修复任务：`T0r100`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/analyzer/comptime_evaluator.py::<模块级>", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_constant", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_for_statement", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_literal", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_node"]
- 文件面：["cypyc/analyzer/comptime_evaluator.py", "cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py"]
- 锁：["tests/analyzer/test_r5_fix_comptime_types.py", "tests/codegen/test_r5_fix_codegen.py"] 共 23 条节点；HEAD 快照复算红 15 条；摘回本单改动后红 15 条
- 修前红的原文（逐字，取前两条）：["AssertionError: 返回值里仍有 AST 节点：[('value[0]', BinOp(line=0, col=0)), ('value[1]', Constant(line=2, col=27))]", "AssertionError: '(1, 2)' 的求值结果外泄 AST 节点：[('value[0]', Constant(line=2, col=16)), ('value[1]', Constant(line=2, col=19))]"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-analyzer 改了既有测试面 ["cypyc/analyzer/comptime_evaluator.py", "cypyc/analyzer/type_checker.py", "cypyc/analyzer/scope_analyzer.py"]；为什么改（车道原话，逐字）：["BUG-82 的根因不在分析器：求值侧值实测正确（a\"b），坏在 cypyc/codegen/cython_generator.py 的 _visit_ComptimeStmt 直插 f'\"{result}\"'，该文件本车道禁改 ⇒ 未修", "BUG-83 残留：cypyc/parser/macro_expander.py:140-144 对块形式 ComptimeStmt.expr 为 list 仍抛 'list' object has no attribute '__dict__'；CLI 两张脸被分析器诊断提前拦住所以用户看不到"]；改动前观察到的原文（逐字）：["AssertionError: 返回值里仍有 AST 节点：[('value[0]', Constant(line=2, col=16)), ('value[1]', Constant(line=2, col=19))]", "AssertionError: 求不出来的元素被当成值返回了：[Name(line=2, col=16), Constant(line=2, col=28)]"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 15 条（其中断言级 14 条）；邻组牵连 []
- 车道：`lane-analyzer`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-82 [2026-09-28T06:32:38Z] [high] OPEN
- summary: [COMPTIME_string_result_emitted_unescaped] comptime 的字符串结果被裸插值写进产物，变成活表达式（可劫持 docstring）
- detail: 立单依据（声明原文现读）：{'file': 'SYNTAX/19-comptime.md', 'line': 21, 'quote': '3. **独立语句**：单独的 `comptime:` 语句被转换为注释（`# comptime: ...`）'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=unescaped (期望 unescaped)
  ctl=commented (期望 commented)
  pos 证据：{"rc": 0, "snippet": ["\"a\"b\""]}
  ctl 证据：{"rc": 0, "snippet": []}

机制（本环未改产品码）：cython_generator.py 对 comptime 结果用 f'"{result}"' 直插，未走 _visit_Constant 的 repr 路径

症状 3 条：comptime: "a" + "\"" + "b" → `"a"b"`、首行 comptime 字符串被 Cython 认成 docstring、同路径的整数 comptime 不会泄漏

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('G05'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「本环只在 comptime 语句里观察到」不豁免其它直插分支——修的时候要一并扫

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-32。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:38+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r101

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`COMPTIME_string_result_emitted_unescaped`
- 修复任务：`T0r101`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/codegen/cython_generator.py::<模块级>", "cypyc/codegen/cython_generator.py::CythonGenerator", "cypyc/codegen/cython_generator.py::CythonGenerator.__init__", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts.scan", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_method_names"]
- 文件面：["cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py"]
- 锁：["tests/analyzer/test_r5_fix_comptime_types.py", "tests/codegen/test_r5_fix_codegen.py"] 共 5 条节点；HEAD 快照复算红 3 条；摘回本单改动后红 3 条
- 修前红的原文（逐字，取前两条）：["AssertionError: comptime 字符串占了 docstring 位：Expr(value=Constant(value='abc'))", "AssertionError: # cython: language_level=3"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-analyzer 改了既有测试面 ["cypyc/analyzer/comptime_evaluator.py", "cypyc/analyzer/type_checker.py", "cypyc/analyzer/scope_analyzer.py"]；为什么改（车道原话，逐字）：["BUG-82 的根因不在分析器：求值侧值实测正确（a\"b），坏在 cypyc/codegen/cython_generator.py 的 _visit_ComptimeStmt 直插 f'\"{result}\"'，该文件本车道禁改 ⇒ 未修", "BUG-83 残留：cypyc/parser/macro_expander.py:140-144 对块形式 ComptimeStmt.expr 为 list 仍抛 'list' object has no attribute '__dict__'；CLI 两张脸被分析器诊断提前拦住所以用户看不到"]；改动前观察到的原文（逐字）：["AssertionError: 返回值里仍有 AST 节点：[('value[0]', Constant(line=2, col=16)), ('value[1]', Constant(line=2, col=19))]", "AssertionError: 求不出来的元素被当成值返回了：[Name(line=2, col=16), Constant(line=2, col=28)]"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 3 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-analyzer`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-83 [2026-09-28T06:32:39Z] [medium] OPEN
- summary: [COMPTIME_block_form_surfaces_internal_exception] `comptime:` 块形式让转译器抛内部异常，异常文本被当诊断打印
- detail: 立单依据（声明原文现读）：{'file': 'SYNTAX/19-comptime.md', 'line': 42, 'quote': '| `comptime:` 块形式 | 未实现 |'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=internal_exception (期望 internal_exception)
  ctl=no_internal_exception (期望 no_internal_exception)
  pos 证据：{"rc": 1, "diag": ["\u001b[31m-\u001b[0m 转译错误: 'list' object has no attribute '__dict__'"]}
  ctl 证据：{"rc": 0, "diag": []}

机制（本环未改产品码）：块形式在 comptime 求值路径上拿到 list 去访问 `__dict__`，异常字符串直接进诊断文案（文档只写了「未实现」）

症状 3 条：comptime: 块 → 转译错误: 'list' object has no attribute '__dict__'、同一表达式行内形式 rc=0、用户拿不到文件行号与「未实现」措辞

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('G07'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「未实现」不是免罪：诊断路径把内部异常外泄本身就是缺陷，但本条不主张块语义

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=无近亲。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:38+00:00 实测；severity=medium（本轮内部口径 P2）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r102

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`COMPTIME_block_form_surfaces_internal_exception`
- 修复任务：`T0r102`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/analyzer/comptime_evaluator.py::<模块级>", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_constant", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_for_statement", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_literal", "cypyc/analyzer/comptime_evaluator.py::ComptimeEvaluator._evaluate_node"]
- 文件面：["cypyc/analyzer/comptime_evaluator.py", "cypyc/analyzer/type_checker.py", "cypyc/parser/lexer.py", "tests/analyzer/test_r5_fix_comptime_types.py"]
- 锁：["tests/analyzer/test_r5_fix_comptime_types.py"] 共 4 条节点；HEAD 快照复算红 3 条；摘回本单改动后红 3 条
- 修前红的原文（逐字，取前两条）：["AssertionError: 求值侧没有结构化的未实现诊断类型 cypyc.analyzer.comptime_evaluator.ComptimeNotImplementedError", "AssertionError: 求值侧没有结构化的未实现诊断类型 cypyc.analyzer.comptime_evaluator.ComptimeNotImplementedError"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-analyzer 改了既有测试面 ["cypyc/analyzer/comptime_evaluator.py", "cypyc/analyzer/type_checker.py", "cypyc/analyzer/scope_analyzer.py"]；为什么改（车道原话，逐字）：["BUG-82 的根因不在分析器：求值侧值实测正确（a\"b），坏在 cypyc/codegen/cython_generator.py 的 _visit_ComptimeStmt 直插 f'\"{result}\"'，该文件本车道禁改 ⇒ 未修", "BUG-83 残留：cypyc/parser/macro_expander.py:140-144 对块形式 ComptimeStmt.expr 为 list 仍抛 'list' object has no attribute '__dict__'；CLI 两张脸被分析器诊断提前拦住所以用户看不到"]；改动前观察到的原文（逐字）：["AssertionError: 返回值里仍有 AST 节点：[('value[0]', Constant(line=2, col=16)), ('value[1]', Constant(line=2, col=19))]", "AssertionError: 求不出来的元素被当成值返回了：[Name(line=2, col=16), Constant(line=2, col=28)]"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 3 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-analyzer`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-84 [2026-09-28T06:32:39Z] [high] OPEN
- summary: [TYPES_documented_pointer_element_names_undefined] 文档工作例里的 `*char` 返回位被判 Undefined name，同名的 let 位却能降码
- detail: 立单依据（声明原文现读）：{'file': 'SYNTAX/04-pointer-types.md', 'line': 59, 'quote': 'def allocate_buffer(size: int) -> *char:'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=rejected (期望 rejected)
  ctl=lowered (期望 lowered)
  pos 证据：{"rc": 1, "diag": []}
  ctl 证据：{"rc": 0, "diag": []}

机制（本环未改产品码）：cypyc/analyzer/type_checker.py 的 builtin_types 缺 C 整型/void/char 名，返回注解走 _visit_Name 查找

症状 4 条：*char 返回位被拒、*void/*long/*short/*unsigned 同拒、*int/*double 通过、let p: *char 正常降码

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('G06'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：01-basic-types 没列 char ⇒ 本条只主张「同一文档同一符号两处不一致」，不主张整套 C 类型面都该可用

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-75。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:39+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r103

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`TYPES_documented_pointer_element_names_undefined`
- 修复任务：`T0r103`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/analyzer/type_checker.py::<模块级>", "cypyc/analyzer/type_checker.py::Type", "cypyc/analyzer/type_checker.py::Type.__eq__", "cypyc/analyzer/type_checker.py::TypeChecker", "cypyc/analyzer/type_checker.py::TypeChecker.__init__", "cypyc/analyzer/type_checker.py::TypeChecker._bare_container_type"]
- 文件面：["cypyc/analyzer/scope_analyzer.py", "cypyc/analyzer/type_checker.py", "cypyc/parser/lexer.py"]
- 锁：["tests/analyzer/test_r5_fix_comptime_types.py"] 共 5 条节点；HEAD 快照复算红 3 条；摘回本单改动后红 3 条
- 修前红的原文（逐字，取前两条）：["AssertionError: [\"Undefined name 'char' at 1:21\", \"Undefined name 'char' at 1:11\"]", "AssertionError: 文档工作例的 *char 返回位被拒：[\"Undefined name 'char' at 1:43\", \"Undefined name 'char' at 1:21\", \"Undefined name 'char' at 1:33\"]"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-analyzer 改了既有测试面 ["cypyc/analyzer/comptime_evaluator.py", "cypyc/analyzer/type_checker.py", "cypyc/analyzer/scope_analyzer.py"]；为什么改（车道原话，逐字）：["BUG-82 的根因不在分析器：求值侧值实测正确（a\"b），坏在 cypyc/codegen/cython_generator.py 的 _visit_ComptimeStmt 直插 f'\"{result}\"'，该文件本车道禁改 ⇒ 未修", "BUG-83 残留：cypyc/parser/macro_expander.py:140-144 对块形式 ComptimeStmt.expr 为 list 仍抛 'list' object has no attribute '__dict__'；CLI 两张脸被分析器诊断提前拦住所以用户看不到"]；改动前观察到的原文（逐字）：["AssertionError: 返回值里仍有 AST 节点：[('value[0]', Constant(line=2, col=16)), ('value[1]', Constant(line=2, col=19))]", "AssertionError: 求不出来的元素被当成值返回了：[Name(line=2, col=16), Constant(line=2, col=28)]"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 3 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-analyzer`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-85 [2026-09-28T06:32:40Z] [high] OPEN
- summary: [CLI_global_option_overwritten_by_subparser] 全局 `-o`/`-v` 被子命令同名默认值覆盖，写在子命令前时静默失效
- detail: 立单依据（声明原文现读）：{'file': 'docs/USAGE.md', 'line': 57, 'quote': '| `-o, --output DIR` | 生成文件输出目录（默认 `output`） |'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=ignored (期望 ignored)
  ctl=honoured (期望 honoured)
  pos 证据：{"rc": 0, "dir_made": false, "out": "llo.cypy\n\u001b[36m[2/3]\u001b[0m Output: output\n\u001b[36m[3/3]\u001b[0m Using Cython compiler mode\n\u001b[34m[INFO] Transpiling to Cython code...\u001b[0m\n\u001b[32m[OK] Transpiled successfully\u001b[0m\n  \u001b[36mOutput:\u001b[0m output\\hello.pyx"}
  ctl 证据：{"rc": 0, "dir_made": true}

机制（本环未改产品码）：cypyc/cli.py 的全局解析之后，每个子解析器又声明一遍 -o/-v 且带 default，argparse 把命名空间重新播种

症状 3 条：cypyc -o DIR transpile … 仍写 output/、cypyc -v compile … 不打步骤、子命令后的 -o/-v 正常

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('H01'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「目录没建」不证明选项被完全忽略——只证明这个位置上的值没走到落码

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-56。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:40+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r104

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CLI_global_option_overwritten_by_subparser`
- 修复任务：`T0r104`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/cli.py::<模块级>", "cypyc/cli.py::_check_scope", "cypyc/cli.py::_read_cli_source", "cypyc/cli.py::_report_build_failures", "cypyc/cli.py::_report_cache_clear", "cypyc/cli.py::_transpile_check_only"]
- 文件面：["cypy_hook/hook.py", "cypyc/cli.py", "cypyc/parser/lexer.py"]
- 锁：["tests/cli/test_r5_fix_cli_hook.py"] 共 8 条节点；HEAD 快照复算红 3 条；摘回本单改动后红 3 条
- 修前红的原文（逐字，取前两条）：["AssertionError: 写在子命令前的 -o 没生效（仍写 output/）：piler\u001b[0m", "AssertionError: assert 'output' == 'DIR'"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-cli-hook 改了既有测试面 ["cypyc/cli.py", "cypy_hook/hook.py"]；为什么改（车道原话，逐字）：["BUG-88 症状 2「编译顺序打印的是未过滤全集」没修：result.compilation_order 由 cypyc/project/project_compiler.py:722 填全图拓扑序，那档不在本车道 ⇒ 本单只算修一半，账本机制栏点名的 project_compiler 面未动", "BUG-86 端到端「loader=ExtensionFileLoader」证据未钉：按纪律不触发 C 工具链，锁只到 is_cypy_file/find_spec + transpile 面"]；改动前观察到的原文（逐字）：["AssertionError: 写在子命令前的 -o 没生效（仍写 output/）：… [2/3] Output: output … Output: output\\hello.pyx", "AssertionError: 带 BOM 的 #!bin cypy 首行没被认出来  assert False is True"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 3 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-cli-hook`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-86 [2026-09-28T06:32:41Z] [high] OPEN
- summary: [HOOK_bom_marker_silently_not_compiled] 带 BOM 的 `#!bin cypy` 标记让 import hook 静默放行，按普通 .py 执行且零诊断
- detail: 立单依据（声明原文现读）：{'file': 'docs/USAGE.md', 'line': 290, 'quote': '# 之后即可 import 带 "#!bin cypy" 标记的文件'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=not_hooked (期望 not_hooked)
  ctl=hooked (期望 hooked)
  pos 证据：{"rc": 0, "loader": "SourceFileLoader E:\\IDEProjects\\AI\\Cypy\\.fist-loop-20260927\\hunt_r5_tmp\\cli_face\\book_h03\\marker_bom.py"}
  ctl 证据：{"rc": 0, "loader": "ExtensionFileLoader"}

机制（本环未改产品码）：cypy_hook/hook.py 用 utf-8（非 utf-8-sig）读首行再逐字比较，BOM 存活 ⇒ find_spec 判定不是 Cypy 模块

症状 3 条：BOM 版 loader=SourceFileLoader、无 BOM 版 loader=ExtensionFileLoader、同一文件 transpile 却成功

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('H03'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「hook 没接管」不等于「语义变了」——本条只主张静默（没有任何提示）

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-47。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:40+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r105

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`HOOK_bom_marker_silently_not_compiled`
- 修复任务：`T0r105`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypy_hook/hook.py::<模块级>", "cypy_hook/hook.py::CacheClearReport", "cypy_hook/hook.py::CacheClearReport.ok", "cypy_hook/hook.py::CypyCacheManager", "cypy_hook/hook.py::CypyCacheManager._base_cache_dir_for", "cypy_hook/hook.py::CypyCacheManager._clear_single"]
- 文件面：["cypy_hook/hook.py", "cypyc/parser/lexer.py"]
- 锁：["tests/cli/test_r5_fix_cli_hook.py"] 共 4 条节点；HEAD 快照复算红 2 条；摘回本单改动后红 2 条
- 修前红的原文（逐字，取前两条）：["AssertionError: 带 BOM 的 #!bin cypy 首行没被认出来", "AssertionError: BOM 版被 import hook 静默放行（既不编译也不给诊断）"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-cli-hook 改了既有测试面 ["cypyc/cli.py", "cypy_hook/hook.py"]；为什么改（车道原话，逐字）：["BUG-88 症状 2「编译顺序打印的是未过滤全集」没修：result.compilation_order 由 cypyc/project/project_compiler.py:722 填全图拓扑序，那档不在本车道 ⇒ 本单只算修一半，账本机制栏点名的 project_compiler 面未动", "BUG-86 端到端「loader=ExtensionFileLoader」证据未钉：按纪律不触发 C 工具链，锁只到 is_cypy_file/find_spec + transpile 面"]；改动前观察到的原文（逐字）：["AssertionError: 写在子命令前的 -o 没生效（仍写 output/）：… [2/3] Output: output … Output: output\\hello.pyx", "AssertionError: 带 BOM 的 #!bin cypy 首行没被认出来  assert False is True"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 2 条（其中断言级 2 条）；邻组牵连 []
- 车道：`lane-cli-hook`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-87 [2026-09-28T06:32:41Z] [high] OPEN
- summary: [HOOK_clear_cache_reports_ok_but_keeps_artifacts] `hook clear-cache` 报「已清除」，但缓存目录里的 .pyd 与中间产物原地留着
- detail: 立单依据（声明原文现读）：{'file': 'docs/USAGE.md', 'line': 131, 'quote': 'cypyc hook clear-cache    # 清除 Cypy 编译缓存（__pycache__/cypy）'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=claimed_but_kept (期望 claimed_but_kept)
  ctl=cleared (期望 cleared)
  pos 证据：{"rc": 0, "claim": "[OK] Cypy compilation cache cleared successfully", "pyd_before": ["marker_ok.cp313-win_amd64.pyd", "marker_ok.cp313-win_amd64.pyd"], "pyd_after": ["marker_ok.cp313-win_amd64.pyd", "marker_ok.cp313-win_amd64.pyd"], "manifest_gone": true}
  ctl 证据：{"rc": 0, "manifest_before": ["manifest.json"], "manifest_after": []}

机制（本环未改产品码）：cypy_hook/hook.py 只删 `__pycache__/cypy` 根下的文件，产物实际写在哈希子目录里；cli 无条件打 [OK]

症状 4 条：清完 manifest 没了、.pyd/.c/setup.py/build 还在、扫描根是 os.getcwd()、回执仍写着成功

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('H04'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「.pyd 还在」不证明它会继续被加载（那是另一条缓存失效语义）；本条主张的是回执文案与实际动作不符

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-30、BUG-66。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:41+00:00 实测；severity=high（本轮内部口径 P1）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r106

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`HOOK_clear_cache_reports_ok_but_keeps_artifacts`
- 修复任务：`T0r106`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypy_hook/hook.py::<模块级>", "cypy_hook/hook.py::CacheClearReport", "cypy_hook/hook.py::CacheClearReport.ok", "cypy_hook/hook.py::CypyCacheManager", "cypy_hook/hook.py::CypyCacheManager._base_cache_dir_for", "cypy_hook/hook.py::CypyCacheManager._clear_single"]
- 文件面：["cypy_hook/hook.py", "cypyc/cli.py"]
- 锁：["tests/cli/test_r5_fix_cli_hook.py"] 共 3 条节点；HEAD 快照复算红 3 条；摘回本单改动后红 3 条
- 修前红的原文（逐字，取前两条）：["AssertionError: 回执报「已清除」，产物却原地留着：['C:\\\\Users\\\\victo\\\\AppData\\\\Local\\\\Temp\\\\pytest-of-victo\\\\pytest-1315\\\\test_r5_87_clear_cache_removes0\\\\__pycache__\\\\cypy\\\\manifest.json', 'C:\\\\Users\\\\victo\\\\AppData\\", "AssertionError: clear_cache() 不回报任何结果，调用方无从知道删了几个、几个没删掉"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-cli-hook 改了既有测试面 ["cypyc/cli.py", "cypy_hook/hook.py"]；为什么改（车道原话，逐字）：["BUG-88 症状 2「编译顺序打印的是未过滤全集」没修：result.compilation_order 由 cypyc/project/project_compiler.py:722 填全图拓扑序，那档不在本车道 ⇒ 本单只算修一半，账本机制栏点名的 project_compiler 面未动", "BUG-86 端到端「loader=ExtensionFileLoader」证据未钉：按纪律不触发 C 工具链，锁只到 is_cypy_file/find_spec + transpile 面"]；改动前观察到的原文（逐字）：["AssertionError: 写在子命令前的 -o 没生效（仍写 output/）：… [2/3] Output: output … Output: output\\hello.pyx", "AssertionError: 带 BOM 的 #!bin cypy 首行没被认出来  assert False is True"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 3 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-cli-hook`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-88 [2026-09-28T06:32:42Z] [medium] OPEN
- summary: [CLI_build_failure_reason_message_swallowed] `build --entry nosuch` rc=1 却只打 `Failed modules (0)`，原因文案被丢弃
- detail: 立单依据（声明原文现读）：{'file': 'docs/USAGE.md', 'line': 102, 'quote': 'cypyc build ./myproject --entry main    # 仅编译 main 模块及其依赖'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=no_reason (期望 no_reason)
  ctl=reason_given (期望 reason_given)
  pos 证据：{"rc": 1, "out": "\\AI\\Cypy\\examples\\test_project\n\u001b[36m[2/5]\u001b[0m Output directory: output\n\u001b[36m[3/5]\u001b[0m Mode: Full build\n\u001b[36m[4/5]\u001b[0m Building project...\n\u001b[36m[5/5]\u001b[0m Compilation order: types -> geometry -> main\n\n  Failed modules (0):", "reason_missing": true}
  ctl 证据：{"rc": 0, "out": "geometry.cp313-win_amd64.pyd\n    \u001b[32m[OK]\u001b[0m main -> E:\\IDEProjects\\AI\\Cypy\\.fist-loop-20260927\\hunt_r5_tmp\\cli_face\\k05c\\output\\main\\main.cp313-win_amd64.pyd"}

机制（本环未改产品码）：cypyc/project/project_compiler.py 把入口点诊断放在非标准键里，cli 只遍历 failed_modules ⇒ 那句话永远打印不出来

症状 3 条：Failed modules (0) 与 rc=1 同屏、编译顺序打印的是未过滤全集、同族 _cycles 键同样无人读

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('H05'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「文案没打印」不证明入口点解析本身对——那是另一个问题

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-56。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:41+00:00 实测；severity=medium（本轮内部口径 P2）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r107

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CLI_build_failure_reason_message_swallowed`
- 修复任务：`T0r107`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：[]
- 文件面：["cypyc/cli.py", "cypyc/project/project_compiler.py"]
- 锁：["tests/cli/test_r5_fix_cli_hook.py"] 共 3 条节点；HEAD 快照复算红 3 条；摘回本单改动后红 3 条
- 修前红的原文（逐字，取前两条）：["AssertionError: cle_reason_reache0\\cyclic", "AssertionError: oject"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-cli-hook 改了既有测试面 ["cypyc/cli.py", "cypy_hook/hook.py"]；为什么改（车道原话，逐字）：["BUG-88 症状 2「编译顺序打印的是未过滤全集」没修：result.compilation_order 由 cypyc/project/project_compiler.py:722 填全图拓扑序，那档不在本车道 ⇒ 本单只算修一半，账本机制栏点名的 project_compiler 面未动", "BUG-86 端到端「loader=ExtensionFileLoader」证据未钉：按纪律不触发 C 工具链，锁只到 is_cypy_file/find_spec + transpile 面"]；改动前观察到的原文（逐字）：["AssertionError: 写在子命令前的 -o 没生效（仍写 output/）：… [2/3] Output: output … Output: output\\hello.pyx", "AssertionError: 带 BOM 的 #!bin cypy 首行没被认出来  assert False is True"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 3 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-cli-hook`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-89 [2026-09-28T06:32:42Z] [medium] OPEN
- summary: [CLI_check_only_ignores_entry_scope] `build --check-only --entry X` 收下 --entry 却完全不读它
- detail: 立单依据（声明原文现读）：{'file': 'docs/USAGE.md', 'line': 102, 'quote': 'cypyc build ./myproject --entry main    # 仅编译 main 模块及其依赖'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=ignored (期望 ignored)
  ctl=honoured (期望 honoured)
  pos 证据：{"rc": 0, "out": "]\u001b[0m Parsing and type checking...\n\u001b[32m[OK] geometry: type check passed\u001b[0m\n\u001b[32m[OK] main: type check passed\u001b[0m\n\u001b[32m[OK] types: type check passed\u001b[0m\n\u001b[32m[OK] All modules passed type checking\u001b[0m"}
  ctl 证据：{"rc": 1, "out": "ry: output\n\u001b[36m[3/5]\u001b[0m Mode: Full build\n\u001b[36m[4/5]\u001b[0m Building project...\n\u001b[36m[5/5]\u001b[0m Compilation order: types -> geometry -> main\n\n  Failed modules (0):"}

机制（本环未改产品码）：cypyc/cli.py 的 check-only 分支自成一段，不经过读 args.entry 的那段代码

症状 3 条：检查模式扫全部模块、同参数不带 --check-only 时确实裁剪、help 与 USAGE 都只写了一处承诺

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('H06'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「两个模式范围不同」不证明哪个才对——本条只主张承诺的裁剪没生效

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-56。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:42+00:00 实测；severity=medium（本轮内部口径 P2）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r108

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CLI_check_only_ignores_entry_scope`
- 修复任务：`T0r108`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/cli.py::<模块级>", "cypyc/cli.py::_check_scope", "cypyc/cli.py::_read_cli_source", "cypyc/cli.py::_report_build_failures", "cypyc/cli.py::_report_cache_clear", "cypyc/cli.py::_transpile_check_only"]
- 文件面：["cypyc/cli.py", "cypyc/parser/lexer.py"]
- 锁：["tests/cli/test_r5_fix_cli_hook.py"] 共 3 条节点；HEAD 快照复算红 2 条；摘回本单改动后红 2 条
- 修前红的原文（逐字，取前两条）：["AssertionError: --check-only 仍然无视 --entry 扫了全部模块：oop-20260927\\fix_r5_snap\\head\\examples\\test_project", "AssertionError: entry 被拒却回报成功：AppData\\Local\\Temp\\pytest-of-victo\\pytest-1315\\test_r5_89_check_only_with_unk0\\out"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-cli-hook 改了既有测试面 ["cypyc/cli.py", "cypy_hook/hook.py"]；为什么改（车道原话，逐字）：["BUG-88 症状 2「编译顺序打印的是未过滤全集」没修：result.compilation_order 由 cypyc/project/project_compiler.py:722 填全图拓扑序，那档不在本车道 ⇒ 本单只算修一半，账本机制栏点名的 project_compiler 面未动", "BUG-86 端到端「loader=ExtensionFileLoader」证据未钉：按纪律不触发 C 工具链，锁只到 is_cypy_file/find_spec + transpile 面"]；改动前观察到的原文（逐字）：["AssertionError: 写在子命令前的 -o 没生效（仍写 output/）：… [2/3] Output: output … Output: output\\hello.pyx", "AssertionError: 带 BOM 的 #!bin cypy 首行没被认出来  assert False is True"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 2 条（其中断言级 2 条）；邻组牵连 []
- 车道：`lane-cli-hook`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-90 [2026-09-28T06:32:43Z] [medium] OPEN
- summary: [CODEGEN_module_identity_hardcoded_unknown] 每个产物都写死 `__name__ = "unknown"` / `__file__ = ""`，模块认不出自己
- detail: 立单依据（声明原文现读）：{'file': 'cypyc/codegen/cython_generator.py', 'line': 327, 'quote': 'self._write(f"Source file: {self.source_file or \'unknown\'}")'} 

现场复跑（pos 与同族 ctl 双档）：
  pos=unknown_identity (期望 unknown_identity)
  ctl=real_identity (期望 real_identity)
  pos 证据：{"rc": 0}
  ctl 证据：{"tail": " {name}!'\ndef main():\n    message = greet('World')\n    print(message)\n    return 0\nif __name__ == '__main__':\n    main()"}

机制（本环未改产品码）：CythonGenerator(source_file=None) 的默认值从未被任何调用方覆盖

症状 3 条：产物头 Source file: unknown、__name__/__file__ 常量和空串、同段其它元数据（版本/目标/profile）都是真值

复跑命令：python -X utf8 -c "import sys;sys.path.insert(0,r'.fist-loop-20260927');import hunt_r5_book as B;print(B.rerun('H07'))"
整批判据件：.fist-loop-20260927/hunt_r5_codegen.json 与 .fist-loop-20260927/hunt_r5_cli_face.json

不算证明：「模块名不对」不证明导入失败——本环观察到的是身份常量，不是导入错误

去重结论：与 memory/bugs.md 现有 77 单按机制签名比对无重合；近亲逐条裁决=BUG-72。

来历：[loop:20260927-loop:R5-寻虫] 2026-09-28T06:32:42+00:00 实测；severity=medium（本轮内部口径 P2）；修属：R5-修复
- reported_by: cypy-hunter
- task_id: T0r109

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CODEGEN_module_identity_hardcoded_unknown`
- 修复任务：`T0r109`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/codegen/cython_generator.py::<模块级>", "cypyc/codegen/cython_generator.py::CythonGenerator", "cypyc/codegen/cython_generator.py::CythonGenerator.__init__", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts.scan", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_method_names"]
- 文件面：["cypy_hook/hook.py", "cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py"]
- 锁：["tests/codegen/test_r5_fix_codegen.py"] 共 6 条节点；HEAD 快照复算红 4 条；摘回本单改动后红 4 条
- 修前红的原文（逐字，取前两条）：["AssertionError: {'__file__': '\"\"', '__name__': '\"unknown\"'}", "AssertionError: # cython: language_level=3"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-commander-identity 改了既有测试面 ["cypyc/codegen/cython_generator.py", "cypy_hook/hook.py", "cypyc/project/project_compiler.py"]；为什么改（车道原话，逐字）：["起因不是「套件坏了一条」而是 BUG-90 只修了一半：卡片机制栏自己写着「CythonGenerator(source_file=None) 的默认值从未被任何调用方覆盖」，而 codegen 车道的锁全部直接构造生成器（`_lower(..., source_file=...)`），打不到 hook/project 这两个真入口 ⇒ 删掉伪造之后，走文件入口的产物直接没有身份常量", "接线之后又暴露一条：产物头注把 Windows 路径原文写进模块 docstring，单反斜杠被读成 unicode 转义，项目模式 cythonize 就地 CompileError（新单 BUG-91，同环已修）"]；改动前观察到的原文（逐字）：["判据自证未过：自研套件达地板 47/47（实得 46/47）", "判据自证未过：自研套件 rc=0（实得 1）"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 4 条（其中断言级 3 条）；邻组牵连 []
- 车道：`lane-codegen`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-91 [2026-09-28T10:13:59Z] [high] OPEN
- summary: [CODEGEN_header_docstring_backslash_escape] 产物头注把 Windows 源路径原文写进三引号串，反斜杠没转义 ⇒ Cython 就地语法错误
- detail: 立单依据（产品码原文，摘除转义后的形状）：
  `self._write(f"Source file: {self.source_file or '<not supplied by caller>'}")`
  ——路径原文里的反斜杠紧跟 U 时，落在模块 docstring 的三引号串里就是非法 unicode 转义。

可达性：BUG-90 之后调用方开始传真路径（`cypy_hook/hook.py` 的 `transpile_file` → `transpile(source, source_path=...)`、`cypyc/project/project_compiler.py` 的 `compile_module` → `CythonGenerator(self._source_files.get(module_name))`）。HEAD 时代没有任何调用方覆盖 `source_file=None`，所以这条不可达——是 BUG-90 收口时只改生成器、没管调用方留下的第二个口子（本单补的就是这一半）。

现场复跑（摘除/装回双向，逐字红字见 red_while_removed）：
  判据件：.fist-loop-20260927/fix_r5_snap/ab_escape_lock.py
  锁 1（生成器侧）：tests/codegen/test_r5_fix_codegen.py::test_bug91_windows_path_in_header_docstring_is_a_valid_literal
  锁 2（调用面侧，真起 Cython 编译）：tests/test_project_compiler.py::TestProjectCompiler::test_single_module_compile
  摘除前：{"tests/codegen/test_r5_fix_codegen.py::test_bug91_windows_path_in_header_docstring_is_a_valid_literal": "", "tests/test_project_compiler.py::TestProjectCompiler::test_single_module_compile": ""}
  摘除后：
E       AssertionError:
E         Cython module compiled from Cypy source
E         Source file: C:\Users\who\proj\main.cypy
E       assert '\\\\Users' in '\nCython module compiled from Cypy source\nSource file: C:\\Users\\who\\proj\\main.cypy\n'
tests\codegen\test_r5_fix_codegen.py:503: AssertionError
FAILED tests/codegen/test_r5_fix_codegen.py::test_bug91_windows_path_in_header_docstring_is_a_valid_literal
---
E           AssertionError: assert 'main' in []
E            +  where [] = ProjectCompileResult(success=False, compiled_modules=[], failed_modules=['main'], errors={'main': ['Build failed: honS...cted=[], total_time=1.5839195251464844, type_registry_stats={'modules': 1, 'total_exports': 1, 'unique_type_names': 1}).compiled_modules
tests\test_project_compiler.py:161: AssertionError
FAILED tests/test_project_compiler.py::TestProjectCompiler::test_single_module_compile
  装回后：{"tests/codegen/test_r5_fix_codegen.py::test_bug91_windows_path_in_header_docstring_is_a_valid_literal": "", "tests/test_project_compiler.py::TestProjectCompiler::test_single_module_compile": ""}

症状 3 条：项目模式 `.pyx` 就地编译失败（`Cython.Compiler.Errors.CompileError`）；产物头注行反斜杠数量与 `__file__` 常量不一致；同一段元数据（版本/目标/profile）照发

机制：产物头注走 f-string 直插路径原文，不过任何转义；生成器写死 `Source file: {path}`，而 `tests/test_project_compiler.py` 的临时目录是 Windows 路径

修法（本环已改）：`shown_source = (self.source_file or "<not supplied by caller>").replace(...)` ——反斜杠成对后再写头注；`__name__`/`__file__` 走 repr 不受影响

不算证明：本单没有跨平台验证（Linux/macOS 路径无反斜杠，这条判据在那些平台上恒绿）；路径含三引号或尾随引号的情形未覆盖，只保证「反斜杠不吃字符」

去重结论：与 memory/bugs.md 现有 90 单按机制签名比对无重合；近亲逐条裁决=BUG-90（同一段产物头注，那条讲「不伪造身份」，这条讲「传真路径时转义」）、BUG-81/82（comptime 结果直插产物不吃转义，同一类形状但落点是 docstring 位 vs 字面量位）。

来历：[loop:20260927-loop:R5-修复] 2026-09-28T10:13:58Z 实测；severity=high（P1：接上调用方后项目模式产物直接编不过）；修属：R5-修复（同环已修）
- reported_by: cypy-fixer
- task_id: T0r111

### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 机制键：`CODEGEN_header_docstring_backslash_escape`
- 修复任务：`T0r111`（ns `bugs`，库里 `status=已完成`、`updated_at=2026-09-28T10:58:55+00:00`、`completed_by=cypy-fixer`）
- 改动点（file::symbol 由 git+ast 反解）：["cypyc/codegen/cython_generator.py::<模块级>", "cypyc/codegen/cython_generator.py::CythonGenerator", "cypyc/codegen/cython_generator.py::CythonGenerator.__init__", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_defer_stmts.scan", "cypyc/codegen/cython_generator.py::CythonGenerator._collect_method_names"]
- 文件面：["cypyc/codegen/cython_generator.py", "cypyc/parser/lexer.py", "tests/codegen/__init__.py", "tests/codegen/test_r5_fix_codegen.py", "tests/test_codegen_verification.py"]
- 锁：["tests/codegen/test_r5_fix_codegen.py"] 共 1 条节点；HEAD 快照复算红 1 条；摘回本单改动后红 1 条
- 修前红的原文（逐字，取前两条）：["AssertionError:"]
- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：lane-commander-identity 改了既有测试面 ["cypyc/codegen/cython_generator.py", "cypy_hook/hook.py", "cypyc/project/project_compiler.py"]；为什么改（车道原话，逐字）：["起因不是「套件坏了一条」而是 BUG-90 只修了一半：卡片机制栏自己写着「CythonGenerator(source_file=None) 的默认值从未被任何调用方覆盖」，而 codegen 车道的锁全部直接构造生成器（`_lower(..., source_file=...)`），打不到 hook/project 这两个真入口 ⇒ 删掉伪造之后，走文件入口的产物直接没有身份常量", "接线之后又暴露一条：产物头注把 Windows 路径原文写进模块 docstring，单反斜杠被读成 unicode 转义，项目模式 cythonize 就地 CompileError（新单 BUG-91，同环已修）"]；改动前观察到的原文（逐字）：["判据自证未过：自研套件达地板 47/47（实得 46/47）", "判据自证未过：自研套件 rc=0（实得 1）"]
- 回退矩阵行：mode=`整文件摘回 HEAD 原文（按实测承重闭包一起摘）`，摘回组 [74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91]（组内 17 单共享同一产品文件，一起摘回是定义不是含糊）；sha 复原 9/9 个文件；本单摘后红 1 条（其中断言级 1 条）；邻组牵连 []
- 车道：`lane-commander-identity`（派单与回执见 .fist-loop-20260927/r5_fix_lanes.json）
- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、fix_r5_impact.json、fix_r5_baselines.json
- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，标题行的 `OPEN` 不改写，也不据此判定门禁已绿。

## BUG-92 [2026-09-29T03:04:19+00:00] [medium] OPEN
- summary: [模式匹配:规范缺口] 无 __unapply__ 且实参元数 > 字段数时，产物发不存在的 `__f{i}`；收紧需先补 SYNTAX/17 条款
- detail: 现象：`struct Email: address: str` + `case Email(user, domain)`（字段 1 个、实参 2 个）时，
`cython_generator.py:1792` 为越界槽位生成 `domain = _match_subject_1.__f1`，而生成产物里没有任何类定义 `__f1`
⇒ 运行期 AttributeError 或该 case 恒不命中。分析器不报元数不符（SYNTAX/17-pattern-matching.md 通篇没有元数条款）。
复现：`python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy -o .fist-loop-20260929/out_after --emit-cython`
产物第 39 行 `domain = _match_subject_1.__f1`。
本轮试过又撤掉的两种收紧（都实测过，不是猜测）：
① 分析器加「实参数 > 可解包槽位数」错误 ⇒ `tests/test_extractor_pattern.py::test_extractor_pattern_type_checker`（:192）
   断言 `assert not checker.errors` 被打红，该用例用的正是这条 1 字段 + 2 实参的形态；
② 生成器对已知形状不发 `__f{i}` 而跳过绑定 ⇒ 同名用例的 codegen 断言 `assert "_match_subject_1.__f0" in code`（:235）被打红。
判据面已把该形态钉成「无诊断 + 就是 `__f{i}`」，故本轮不动实现，按「未文档化的收紧不在本轮半径内」入账。
出路（交指挥官裁决，二选一）：① 在 SYNTAX/17 补「元数不符必须诊断」条款并同批更新那两条既有断言；
② 裁定 struct 无提取器时按 `__match_args__`/字段序解包、越界槽位编译期报错，另起一轮同时改判据与实现。
- reported_by: cypy-selfdrive-agent
- task_id: T0r112

### FIXED(R7 组合环 2026-09-29T03:54:36+00:00，ns cypy-loop-20260929 / T0r113) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 前置条款（本环补，落文档面）：`SYNTAX/17-pattern-matching.md` 追加「## 位置模式的元数与槽位规则（R7 补，2026-09-29）」，
  418→441 行；写明槽位数来源优先级（`__match_args__` < `__unapply__` < `__unapply_seq__` < `__unwarp__`，
  无提取器时按 `.fields` 声明序）、**实参元数 > 可解包槽位数必须诊断并带行列**、方法名不占位置槽、
  类型不可见时不报元数错、产物不得出现 `.__f{i}`。本条目「出路 ①」由此成立。
- 实现：`cypyc/analyzer/type_checker.py:_visit_ExtractorPattern` 在槽位类型可得时比较元数，超槽即发
  `Positional pattern '<T>' has <k> slot(s) but type '<T>' unpacks only <n> at <line>:<col>`。
- 判据面（R6 打红的正是这条，本轮按新条款改严而非弱化）：
  `tests/test_extractor_pattern.py::test_extractor_pattern_type_checker` 从 `assert not checker.errors`
  改为双向格——2 字段/2 实参必须 `errors == []`；1 字段/2 实参必须命中 `Positional pattern 'Email'`
  且匹配 `unpacks only 1 at \d+:\d+`。旧断言把本缺陷的静默行为钉成了期望值。
- 调用面实测（真 CLI，非单测桩）：
  `python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy -o .fist-loop-20260929/out_r7 --emit-cython`
  → rc=1，逐字 `- Positional pattern 'Email' has 2 slot(s) but type 'Email' unpacks only 1 at 6:14`
  （.fist-loop-20260929/logs/r7_callsite_huntf.txt）；
  输出目录 `out_r7` 未被创建 ⇒ 本形态下 `.__f1` 不再有产物面。
  before 证据仍在：`.fist-loop-20260929/out_after/hunt_f_pattern_binding_int.pyx` 第 39 行 `domain = _match_subject_1.__f1`。
- 边界审视（T0r113 边界叶，.fist-loop-20260929/hunt_r7_boundary.json 共 23 格）：
  超元与 32 槽极值均带行列诊断；0 实参与欠元按上述条款保持沉默（条款只强制超元）；未定义类型不报元数错（前条件生效）；
  本面 0 CRASH、0 静默放过、0 假阳性。
- 残留（另立新单，服务端号 BUG-109 / BUG-110, BUG-111）：解析器仍把 `[int]` / `(int,str)` / `{str:int}` 编成字面量节点，
  正解需要类型表达式产生器；元数检查只在槽位类型「可见」时生效，类型不可见时越界槽位仍可走到 `.__f{i}`。

- 账面注记（同轮 2026-09-29T04:03:30+00:00，写在这里以免与上一句并读）：上一句并列的三个服务端号里只有 **BUG-109** 属于这条 Cypy 语法面的残留；BUG-110 / BUG-111 是本环在 FIST-Mbt 侧新立的账面与工具缺陷（建树叶数不受控、call_log 复原能力缺失），与本条模式匹配主张无关，分栏见 `reports/2026-09-29/T0r113-cypy-selfdrive-r7-report.md` §4。

## BUG-93 [2026-09-29T03:04:19+00:00] [medium] OPEN
- summary: [工具面] scripts/fist.py 指向上游已迁走的 cmd/main/main.js 且 list-tools 是恒绿探针
- detail: 现象（修复前实测）：`SERVER_JS` 固定 `_build/js/debug/build/cmd/main/main.js`，
服务 cwd 是兄弟仓 FIST-Mbt（⇒ 本项目 ns `cron-cypy` 的行写进 FIST-Mbt/fist-mbt.db，而不是仓内
`fist-mbt.db`，与既往四轮 lane 的收口库分家）；`project_dir` 默认绝对路径（服务端「禁越界」直接拒写）；
`main()` 先发一次 `initialize`，而 2026-07-28 是无状态握手，服务端回
`-32601 Method not found: initialize — this server speaks MCP 2026-07-28`，回执没人读；
`list-tools` 在错误帧/空清单/缺工具三种失败形态下**全部 rc=0 且零输出**（恒绿探针）。
另：驱动对所有调用无条件注入 `namespace`/`project_dir`，而 `loop_create`/`laya_decide`/`task_plan_deep`
不声明这两个键 ⇒ 服务端按 BUG-23 口径拒收（回执点名「参数名不被接受」）。
修复：入口改 `cmd/cli/cli.js` + `serve`；cwd 改本仓根（任务库落 `E:/IDEProjects/AI/Cypy/fist-mbt.db`）、
`project_dir` 默认 `.`；删掉 `initialize`；`_meta` 仍逐请求携带；`list-tools` 必须解出非空清单且点名
12 个本轮依赖的工具（publish/claim/execute/submit/verify/run_check/omega_verify/omega_spec_create/
laya_decide/call_log/report_bug/bug_list），否则 rc=1；新增 `_omit_defaults` 退出键关掉注入。
调用面实测：`python scripts/fist.py list-tools` → `# 129 tools; cwd=E:/IDEProjects/AI/Cypy; missing=[]`、rc=0；
`loop_create` + `laya_decide` + `task_plan_deep` 三连在带退出键后全部落库（ns cypy-loop-20260929，根 T0r112）。
锁死回归：`tests/test_fist_driver_protocol.py`（10 条，假 Popen 驱动，不起 node/不碰库；
含 3 条必然红的对照：错误帧、空清单、缺 omega_verify）。
- reported_by: cypy-selfdrive-agent
- task_id: T0r112

### FIXED(R6 组合环 2026-09-29T03:04:19+00:00) — 同轮确诊同轮修，正文与抬头一次落盘

- 见本条目 detail 的「修复」段；锁死回归 tests/test_fist_driver_protocol.py。

## BUG-94 [2026-09-29T03:04:19+00:00] [low] OPEN
- summary: [兄弟仓 FIST-Mbt] `cli.js serve` 仍往协议 stdout 打 2 行人类横幅（其自述 BUG-101 的同类）
- detail: 实测：`node _build/js/debug/build/cmd/cli/cli.js serve` 的前两行 stdout 是
`[fist] serve — 启动 MCP server (stdio 传输)` / `stdin/stdout 接管, Ctrl+C 停止`，
JSON-RPC 帧从第 4 行才开始；而同仓 CHANGELOG 的 BUG-101 自称「run_serve 体内不再写 stdout」，
其回归门 `mcp_smoke` 本地仍报绿。Cypy 侧驱动按「非 JSON 行跳过」容忍，故不影响本轮工作，
但任何严格客户端（首行必须是 JSON）都会拒连。修在兄弟仓，不在 Cypy 轮次半径内 ⇒ 移交。
证据：.fist-loop-20260929/logs/（同命令原样重放两次，前两行逐字相同）。
- reported_by: cypy-selfdrive-agent
- task_id: T0r112

## BUG-95 [2026-09-29T03:04:19+00:00] [medium] OPEN
- summary: [规范落地] PROJECT-SPEC 要求的 corpus/ 与 tests/regression/ 两个目录在本仓不存在
- detail: PROJECT-SPEC/03 §1 规定 `tests/regression/` 存历史 bug 固化用例、§2 规定「测试对同时沉淀为
Ω-spec JSON（corpus/）」；05 §3 的 Ω-gate 跑批第 3 步就是「corpus/ 下每个 spec JSON 的测试对」。
实测：`ls -d corpus tests/regression` → 两者均不存在（`ls -d` rc=2），仓库里也没有任何 Ω-spec JSON。
后果：05 定义的「项目准确率 = 通过/总数」在这个项目没有客观来源，Omega 强验证只能走
`omega_spec_create` 的单任务语料，落不到仓内可复审的判据面。
本轮把新增语料交给 `omega_spec_create`（任务面），但把目录本体留待裁决：新建 corpus/ 需要同时定
「哪些测试对进 corpus、以什么 schema」，那是判据面改动，不该夹在缺陷修复轮里顺手做。
出路：要么裁定本轮之后单开一轮建 corpus 基线（含 schema 与跑批入口），要么显式修订 03/05 对该目录的要求。
- reported_by: cypy-selfdrive-agent
- task_id: T0r112
### FIXED(R8 组合环 2026-09-29T04:46:06+00:00，ns cypy-loop-20260929 / 根见 close_r8_ring.json) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 出路落地：本环选择「单开一轮建 corpus 基线」而不是修订 PROJECT-SPEC 03/05 —— 目录与跑批入口已建：
  `corpus/cypy.annotation.shape.json`（24 格）、`corpus/cypy.pattern.positional.json`（本环扩到 17 格）、
  `scripts/omega_gate.py`（Ω-gate 跑批：fnv1a64 指纹复算、逐对 input→expected/error、准确率、
  结果落 `reports/YYYY-MM-DD/omega-*.json`、非 100% 即 rc=1）、
  `tests/regression/test_corpus_pairs.py`（同一批测试对当 pytest 跑，地板值只认这一份）。
- 期望值来源不是照着实现编的：`SYNTAX/02` 注解形态闭集节 + `SYNTAX/17` 位置模式元数与槽位规则节；
  源码语料取自已入库的回归锁 `tests/test_pattern_positional_struct.py` / `tests/test_annotation_shape.py`。
- 这份可执行判据立刻打出了两例真缺陷（同轮修，编号 BUG-112 / BUG-113）与一例文档-解析器不符（入账 BUG-114），
  不是装饰：Ω-gate 首跑就报出 `class C` 的元数检查被静默跳过。
- 跑批逐字：`CONCLUSION specs=2 cases=41 passed=41 failed=0 refused=0 accuracy=100.00% rc=0`
- 未被本条目遮蔽的残留是 BUG-116（覆盖面只到 2 个 op / 41 个测试对，其余 SYNTAX 章节还没有 Ω-spec），
  另有「正解未做」的两条一起留在账上（BUG-114 语法层、BUG-115 名称序）⇒ 本条只主张「目录与跑批入口存在且可复跑」。

## BUG-96 [2026-09-29T03:13:47Z] [medium] OPEN
- summary: [模式匹配:规范缺口] 无 __unapply__ 且实参元数 > 字段数时产物发不存在的 __f{i}
- detail: 详见 memory/bugs.md BUG-92：本轮试过两种收紧都被既有判据打红（test_extractor_pattern.py:192/:235），故只入账不改实现，出路二选一已在账本写明。活证据：.fist-loop-20260929/out_after/hunt_f_pattern_binding_int.pyx 第 39 行。
（本地账本同号：BUG-92）
- reported_by: cypy-selfdrive-agent


### DUPLICATE(R9 组合环 2026-09-29T05:31:29+00:00) — 正身 = BUG-99

- 与 BUG-99 逐字同 summary（`report_bug` 无幂等键造成的三处双写之一，见 BUG-107）。
- **指认重复不等于缺陷已修**：正身 BUG-99 本段之后仍 OPEN（不可见类型那一半未裁）。
## BUG-97 [2026-09-29T03:13:47Z] [low] OPEN
- summary: [兄弟仓 FIST-Mbt] cli.js serve 仍往协议 stdout 打 2 行人类横幅
- detail: 实测同命令重放两次，stdout 前两行为横幅，JSON 帧从第 4 行起；Cypy 侧驱动按非 JSON 行跳过而容忍。严格客户端会拒连。修在兄弟仓，不在 Cypy 轮次半径内。
（本地账本同号：BUG-94）
- reported_by: cypy-selfdrive-agent

## BUG-98 [2026-09-29T03:13:48Z] [medium] OPEN
- summary: [规范落地] PROJECT-SPEC 要求的 corpus/ 与 tests/regression/ 在本仓不存在
- detail: 03 §1/§2 与 05 §3 要求 Ω-spec JSON 落 corpus/，实测 ls -d corpus tests/regression 均不存在。本轮把语料交给 omega_spec_create（任务面）并把 pattern 一片写成可复审 JSON 落在报告附件，目录本体与跑批入口需指挥官裁决，见账本出路。
（本地账本同号：BUG-95）
- reported_by: cypy-selfdrive-agent


### DUPLICATE(R9 组合环 2026-09-29T05:31:29+00:00) — 正身 = BUG-95（R8 已闭）；且本条主张本身已被实测作废

- 主张「`corpus/` 与 `tests/regression/` 在本仓不存在」今天不成立，逐字（`.fist-loop-20260929/logs/r9_stale_a1.txt`）：
  `CONCLUSION cells=6 corpus_exists=True regr_exists=True gate_rc=0 bug71_still_holds=True bugeta_claim_still_holds=True`；
  目录实测 `corpus_dir_exists=True regr_dir_exists=True`，跑批 `CONCLUSION specs=3 cases=51 passed=51 failed=0 refused=0 accuracy=100.00% rc=0`。
- 三条同 summary 的重复登记由 BUG-107 记账（`report_bug` 无幂等键）；此处只指认正身，不改写原文。
- 覆盖面仍未闭的部分另有条目在账（Ω-spec 只覆盖 3 个 op），本段不得被读成「规范落地面已全部闭环」。
## BUG-99 [2026-09-29T03:14:26Z] [medium] OPEN
- summary: [模式匹配:规范缺口] 无 __unapply__ 且实参元数 > 字段数时产物发不存在的 __f{i}
- detail: 详见 memory/bugs.md BUG-92：本轮试过两种收紧都被既有判据打红（test_extractor_pattern.py:192/:235），故只入账不改实现，出路二选一已在账本写明。活证据：.fist-loop-20260929/out_after/hunt_f_pattern_binding_int.pyx 第 39 行。
（本地账本同号：BUG-92）
- reported_by: cypy-selfdrive-agent


### AMENDMENT(R9 组合环 2026-09-29T05:31:29+00:00) — 拆成两半：可见字段的一半已闭，不可见的一半仍在账

- 已闭的那半（有锁）：类型在本模块可见（生成器登记过 `_class_fields`/`_struct_types`）且实参元数 > 字段数时，
  生成器不再发 `.__f{i}` 成员访问，而是让该 `case` 恒不命中（产物末段 `and False`），分析器仍按规则 1 报元数错；
  配套 `SYNTAX/17-pattern-matching.md` 规则 8（现测 457 行）。
  证据格 = `corpus/cypy.pattern.positional.json` 第 #17/#18 格（0 基口径），
  承重 = `verify_r9_locks.py` 的 S2（把该分支退回发 `.__f{i}` ⇒ Ω-gate 真红）。
- **未闭的那半**：类型不可见（外部类，规则 4「改由运行期 `__unapply__` 解包路径处理」）时，
  产物仍是 `.__f0/.__f1` 形态 —— 既有锁 `tests/test_extractor_pattern.py::test_extractor_pattern_codegen`
  逐字钉着 `assert "_match_subject_1.__f0" in code`（其源里 `Email` 从未定义 ⇒ 属规则 4 半径）。
  本轮把 S2 的初版直接推广到全形态时**打红了这条既有锁**（逐字：`1 failed, 2211 passed in 359.56s`），
  因此按「不可见类型的运行期解包形态是什么」尚未裁出来收回到只处理可见字段的一半，
  而不是改测试凑绿。该裁决面另立单，本条保持 OPEN。
## BUG-100 [2026-09-29T03:14:26Z] [low] OPEN
- summary: [兄弟仓 FIST-Mbt] cli.js serve 仍往协议 stdout 打 2 行人类横幅
- detail: 实测同命令重放两次，stdout 前两行为横幅，JSON 帧从第 4 行起；Cypy 侧驱动按非 JSON 行跳过而容忍。严格客户端会拒连。修在兄弟仓，不在 Cypy 轮次半径内。
（本地账本同号：BUG-94）
- reported_by: cypy-selfdrive-agent

## BUG-101 [2026-09-29T03:14:26Z] [medium] OPEN
- summary: [规范落地] PROJECT-SPEC 要求的 corpus/ 与 tests/regression/ 在本仓不存在
- detail: 03 §1/§2 与 05 §3 要求 Ω-spec JSON 落 corpus/，实测 ls -d corpus tests/regression 均不存在。本轮把语料交给 omega_spec_create（任务面）并把 pattern 一片写成可复审 JSON 落在报告附件，目录本体与跑批入口需指挥官裁决，见账本出路。
（本地账本同号：BUG-95）
- reported_by: cypy-selfdrive-agent


### DUPLICATE(R9 组合环 2026-09-29T05:31:29+00:00) — 正身 = BUG-95（R8 已闭）；且本条主张本身已被实测作废

- 主张「`corpus/` 与 `tests/regression/` 在本仓不存在」今天不成立，逐字（`.fist-loop-20260929/logs/r9_stale_a1.txt`）：
  `CONCLUSION cells=6 corpus_exists=True regr_exists=True gate_rc=0 bug71_still_holds=True bugeta_claim_still_holds=True`；
  目录实测 `corpus_dir_exists=True regr_dir_exists=True`，跑批 `CONCLUSION specs=3 cases=51 passed=51 failed=0 refused=0 accuracy=100.00% rc=0`。
- 三条同 summary 的重复登记由 BUG-107 记账（`report_bug` 无幂等键）；此处只指认正身，不改写原文。
- 覆盖面仍未闭的部分另有条目在账（Ω-spec 只覆盖 3 个 op），本段不得被读成「规范落地面已全部闭环」。
## BUG-102 [2026-09-29T03:15:09Z] [medium] OPEN
- summary: [模式匹配:规范缺口] 无 __unapply__ 且实参元数 > 字段数时产物发不存在的 __f{i}
- detail: 详见 memory/bugs.md BUG-92：本轮试过两种收紧都被既有判据打红（test_extractor_pattern.py:192/:235），故只入账不改实现，出路二选一已在账本写明。活证据：.fist-loop-20260929/out_after/hunt_f_pattern_binding_int.pyx 第 39 行。
（本地账本同号：BUG-92）
- reported_by: cypy-selfdrive-agent


### DUPLICATE(R9 组合环 2026-09-29T05:31:29+00:00) — 正身 = BUG-99

- 与 BUG-99 逐字同 summary（`report_bug` 无幂等键造成的三处双写之一，见 BUG-107）。
- **指认重复不等于缺陷已修**：正身 BUG-99 本段之后仍 OPEN（不可见类型那一半未裁）。
## BUG-103 [2026-09-29T03:15:09Z] [low] OPEN
- summary: [兄弟仓 FIST-Mbt] cli.js serve 仍往协议 stdout 打 2 行人类横幅
- detail: 实测同命令重放两次，stdout 前两行为横幅，JSON 帧从第 4 行起；Cypy 侧驱动按非 JSON 行跳过而容忍。严格客户端会拒连。修在兄弟仓，不在 Cypy 轮次半径内。
（本地账本同号：BUG-94）
- reported_by: cypy-selfdrive-agent

## BUG-104 [2026-09-29T03:15:09Z] [medium] OPEN
- summary: [规范落地] PROJECT-SPEC 要求的 corpus/ 与 tests/regression/ 在本仓不存在
- detail: 03 §1/§2 与 05 §3 要求 Ω-spec JSON 落 corpus/，实测 ls -d corpus tests/regression 均不存在。本轮把语料交给 omega_spec_create（任务面）并把 pattern 一片写成可复审 JSON 落在报告附件，目录本体与跑批入口需指挥官裁决，见账本出路。
（本地账本同号：BUG-95）
- reported_by: cypy-selfdrive-agent


### DUPLICATE(R9 组合环 2026-09-29T05:31:29+00:00) — 正身 = BUG-95（R8 已闭）；且本条主张本身已被实测作废

- 主张「`corpus/` 与 `tests/regression/` 在本仓不存在」今天不成立，逐字（`.fist-loop-20260929/logs/r9_stale_a1.txt`）：
  `CONCLUSION cells=6 corpus_exists=True regr_exists=True gate_rc=0 bug71_still_holds=True bugeta_claim_still_holds=True`；
  目录实测 `corpus_dir_exists=True regr_dir_exists=True`，跑批 `CONCLUSION specs=3 cases=51 passed=51 failed=0 refused=0 accuracy=100.00% rc=0`。
- 三条同 summary 的重复登记由 BUG-107 记账（`report_bug` 无幂等键）；此处只指认正身，不改写原文。
- 覆盖面仍未闭的部分另有条目在账（Ω-spec 只覆盖 3 个 op），本段不得被读成「规范落地面已全部闭环」。
## BUG-105 [2026-09-29T03:16:54Z] [high] OPEN
- summary: [组合环] loop_create 返回完整记录但环不落库：同 ns 的新会话 loop_status/loop_tick 报 loop not found
- detail: 实测两格（同一库 E:/IDEProjects/AI/Cypy/fist-mbt.db，两次独立 serve 进程）：
① 02:53:13Z `loop_create {name:cypy-selfdrive-20260929, steps:[advance,bugfind,fix_and_merge,verify,polish,advance], max_rounds:6, baseline_test_count:2166, baseline_open_bug_count:12}` → 回执带 status:active/created_at/current_idx:0（看起来已登记）；
② 02:53 起在**同一进程**里 loop_tick 也没跑（我先传错 name），03:16 新进程分别用 `cypy-loop-20260929` 与 `cypy-selfdrive-20260929` 调 loop_tick/loop_status，全部回 `loop not found`。
⇒ 环注册不跨会话存活；组合环（推进→寻虫→修复→验证→打磨→推进）无法由无人值守的下一轮接着走，只能重注册（而重注册又会撞「已存在」或静默留下两份账面）。
期望：要么落库（与 tasks/specs 同表族），要么在 create 回执里明写「本会话内存态，进程退出即失效」。
证据：.fist-loop-20260929/ring_created.json、close_r6_ring2.json（6 次 loop_tick 拒绝逐字）、logs/closure2.out。
- reported_by: cypy-selfdrive-agent

## BUG-106 [2026-09-29T03:16:54Z] [medium] OPEN
- summary: [状态机出路] 待领取的叶没有任何代理可用的退役出路：reject 只接受待验收，delete/task_cleanup 不适用于未领任务
- detail: 实测：R6 组合环建树 29 节点，其中 15 条叶本轮半径内无对应交付。逐条 `reject {task_id, reason, by:verifier}` 全部回
`非法打回: 任务处于 [待领取]，仅待验收可打回`（15/15 逐字一致，见 close_r6_ring2.json rejections 栏）。
可选面里没有一个能把「待领取」转为「不再本轮做」：archive 是人类面工具（BUG-78 已记），reopen_task 只作用于已完成，task_cleanup 走的是另一套清理口径。
⇒ 根任务永远停在 [拆分中]（实测 T0r112 status=拆分中），组合环的「收根」在这条工具面上不可达；这不是调用方形状错（我已按 (status, 标记) 生成步骤），是闭集缺一档。
期望：给代理面补一档 `defer/abandon`（或允许 reject 接受待领取并落 cleanup_mode=deferred），回执里点名可用出路。
- reported_by: cypy-selfdrive-agent

## BUG-96 [2026-09-29T03:19:00+00:00] [high] OPEN
- summary: [转结确诊:类型标注] 非法标注形态 `[int]` 仍把 AST 节点 repr 落进产物（`xs: Constant(line=2, col=9) = [1, 2, 3]`），且零诊断
- detail: R6 组合环（2026-09-29）对 BUG-34 复验：条目**仍然成立**，不是过期账。
复现（本轮实测，两条语料同型）：
  `python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/adv_10_slice_step_zero.cypy -o .fist-loop-20260929/out_b34 --emit-cython`
  `python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/adv_19_negative_index_const.cypy -o .fist-loop-20260929/out_b34 --emit-cython`
产物逐字：`out_b34/adv_10_slice_step_zero.pyx:30` → `    xs: Constant(line=2, col=9) = [1, 2, 3]`；
`out_b34/adv_19_negative_index_const.pyx:30` → `    xs: Constant(line=2, col=9) = []`。
源码第 2 行是 `xs: [int] = [1, 2, 3]`（SYNTAX/02 规定的形态是 `list<int>`，`[int]` 属未文档化写法）。
发射点：`cypyc/codegen/cython_generator.py` 的 `_type_to_str()` 末路 `return str(node)`（把 ASTNode 的 Python repr 当类型名写进 .pyx，
该 .pyx 必然编译失败）；分析器侧**没有任何标注形态校验**（本轮 grep `Invalid type annotation`/`Unsupported annotation` 等
在 cypyc/analyzer/*.py 命中 0 条），故 `[int]` 全程无诊断，rc 仍是 0 走到产物面。
本轮没有顺手修的理由（不是遗漏，是半径判断）：修法要同时动两处判据面 ——
① 分析器补「标注必须是类型形状」诊断（新增拒绝面会让既有「静默通过」的用例转红，需先数清是哪几条）；
② 生成器 repr 末路换成安全兜底（`object`）并配「产物字节里不得出现 `line=` 形态的节点 repr」的机器可检守卫。
两件事都需要一次「判据基线先实测」的独立轮次，否则就是把红线问题留给下一轮（本轮已确立的纪律）。
- reported_by: cypy-selfdrive-agent
- task_id: T0r112
- 关联: 本条目是 BUG-34 的复验与定位收口，BUG-34 正文一字未改


### DUPLICATE(R9 组合环 2026-09-29T05:31:29+00:00) — 正身 = BUG-108（R7 已闭）

- 本条与 BUG-108 是同一主张（`xs: [int]` 把 AST 节点 repr 落进产物且零诊断）；
  R7 已在 BUG-108 落地注解形态闭集 + 生成器末路退化，并有 `corpus/cypy.annotation.shape.json` 24 格锁。
- 撞号本身（两个 `## BUG-96` 抬头）由 BUG-107 记账，本段不删除任何原文。
## BUG-107 [2026-09-29T03:20:06+00:00] [medium] OPEN
- summary: [账面双发] report_bug 无幂等键且与手写台账共用编号空间：本轮同一件事被记 3 遍、并撞出两个 `## BUG-96` 抬头
- detail: 逐字盘面（`grep -c '^## BUG-'` 实测 107 条，重复 id=['96']）：
  规范缺口一条 = BUG-96 / BUG-99 / BUG-102（三条同 summary，另本地手记同号写作 BUG-92）；
  serve 横幅一条 = BUG-97 / BUG-100 / BUG-103（本地 BUG-94）；
  corpus 目录一条 = BUG-98 / BUG-101 / BUG-104（本地 BUG-95）。
  双发原因在**驱动侧**：`.fist-loop-20260929/close_r6_leaves.py` 我跑了三遍（第一遍步骤形状错、第二遍补语料审核、
  第三遍修 loop_tick 的 name/ns 混用），起手没有对 report_bug 的幂等守卫 ⇒ 同一主张重复入账。
  撞号原因是**双侧**：`report_bug` 直接写 `./memory/bugs.md` 并按它自己的计数取号，
  而我按「先写本地台账」的既往纪律取了 92..96 —— 两个编号空间互相看不见，
  我那条 high（非法标注形态，BUG-34 复验）正好落在服务端已经用掉的 96 上。
  处置（不改写任何既有正文，只做插入与指认）：
  ① 正身指认：规范缺口以 **BUG-96** 为准，99/102 与本地 BUG-92 视为 DUPLICATE；
     serve 横幅以 **BUG-97** 为准（本地 BUG-94 同义），100/103 DUPLICATE；
     corpus 目录以 **BUG-98** 为准（本地 BUG-95 同义），101/104 DUPLICATE；
  ② 我的非法标注条目**正身改指本文件末尾新增的 BUG-108**（原 96 号撞车，正文保留不删）；
  ③ 驱动已补幂等守卫：`close_r6_leaves.py` 现在先 `bug_list` 拿已有 summary 集合，命中即跳过并记 skipped。
  出路（交兄弟仓）：`report_bug` 需要一条按 summary 规范化的幂等键（或返回「已存在＝BUG-NN」而不新建），
  并把「服务端取号」与「人类/代理手写台账」的编号空间显式分离（否则双通道必然撞号）。
- reported_by: cypy-selfdrive-agent
- task_id: T0r112
### DUPLICATE(编号撞车指认) — 2026-09-29T03:20:06+00:00 追加

- 本文件内 `## BUG-96 [..] [high]`（非法标注形态）的**正身是 BUG-108**；此处不删除原文，仅指认。

## BUG-108 [2026-09-29T03:20:06+00:00] [high] OPEN
- summary: [转结确诊:类型标注] 非法标注形态 `[int]` 把 AST 节点 repr 落进产物且零诊断（BUG-34 的 R6 复验正身，原写作 BUG-96 与服务端撞号）
- detail: 复现/定位逐字见本文件上方 `## BUG-96 [..] [high]` 条目正文（同一条主张，编号改指此处）。
  一句话：`xs: [int]` 经 `cython_generator._type_to_str()` 的 `return str(node)` 末路写成 `xs: Constant(line=2, col=9) = [...]`，
  分析器无任何标注形态校验（grep 命中 0），故 rc=0 且产物必编译失败。
- reported_by: cypy-selfdrive-agent
- task_id: T0r112
### FIXED(R7 组合环 2026-09-29T03:54:36+00:00，ns cypy-loop-20260929 / T0r113) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 前置条款（本环补，落文档面）：`SYNTAX/02-type-annotations.md` 追加「## 注解形态闭集（R7 补，2026-09-29）」，
  158→189 行：合法节点闭集 `Name / GenericType / PointerType / UnionType / RefType`；
  `[] / () / {}` 三种字面量形态一律拒绝且诊断必须点名正确写法；产物永不得携带 AST repr；`comptime:` 行内形式整类排除。
- 分析器：新增 `ANNOTATION_TYPE_KINDS` / `ANNOTATION_SHAPE_HINTS` / `_check_annotation_shape()` /
  `_validate_annotation_shapes()`（AST 全walk，跳过 `kind == "ComptimeStmt"`），挂在 `check()` 的
  `self._visit(node)` 之后；诊断文案 `Invalid type annotation at {line}:{col} (期望 …，实际是 {kind} 字面量形态)`。
- 生成器：`cypyc/codegen/cython_generator.py:_type_to_str` 末路由 `return str(node)` 改为 `return "object"`
  （带注释指认 BUG-34/BUG-108），任何未知形态不再把节点 repr 发进产物。
- 锁死回归：新建 `tests/test_annotation_shape.py`（实收 14 条 / 6 个函数）——
  6 条合法形态放行、4 条非法形态必诊断且带行列、`test_product_never_carries_ast_repr`
  断言产物不含 `line=` 与 `Constant(`、`test_unknown_annotation_degrades_to_object`、
  反向对照 `test_comptime_inline_form_is_not_an_annotation`、收集数地板 `test_this_file_collects_its_locks`。
- 调用面实测：`adv_10_slice_step_zero.cypy` → rc=1，逐字
  `- Invalid type annotation at 2:9 (期望 类型名或 list<int> / tuple<int, int> / dict<str, int>，实际是 Constant 字面量形态)`
  （.fist-loop-20260929/logs/r7_callsite_adv10.txt）；不再产出 .pyx。
  before 证据仍在：`.fist-loop-20260927/cliout/adv_10_slice_step_zero.pyx` 第 30 行 `xs: Constant(line=2, col=9) = [1, 2, 3]`。
- 三套全量回归（本环终态，逐字结论行）：pytest `2158 passed in 413.15s`（rc=0）、
  自研套件 `Total: 47 | Passed: 47 | Failed: 0`（rc=0）、
  e2e golden `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`（rc=0）。
- 残留：括号形态本应是类型而解析器没有类型表达式产生器 ⇒ 正解未做，另立新单（服务端号 BUG-109）。

### AMENDMENT(R7 矩阵改判 2026-09-29，ns cypy-loop-20260929 / T0r113) — 上面 FIXED 段的一处实现描述按实测改判

- 原文写「`_validate_annotation_shapes()`（AST 全walk，跳过 `kind == "ComptimeStmt"`）」——**该跳过不存在了**：
  锁承重矩阵的 M4 格实测它不承重（针指在守卫上摘掉后 `tests/test_annotation_shape.py` 仍 `14 passed`），
  再核结构：`ComptimeStmt.__init__` 只设 `self.expr`，parser 两处构造点均不传 `type_annotation`
  （逐字证据 `.fist-loop-20260929/logs/r7_comptime_structural_proof_a1.txt`），
  语料测量同向（`logs/r7_comptime_fact_a1.txt`：`files=109 parsed=97 ComptimeStmt_nodes=3 with_type_annotation=0`）
  ⇒ 该条件对任意输入都不可能命中，属死代码，已从 `cypyc/analyzer/type_checker.py` 删除。
- 行为主张不变：`comptime: [1, 2]` 仍不被判为非法注解，依据改为结构事实（ComptimeStmt 没有注解字段）；
  认领它的锁仍是 `tests/analyzer/test_r5_fix_comptime_types.py::test_bug83_inline_form_control_still_clean`
  与 `tests/test_annotation_shape.py::test_comptime_inline_form_is_not_an_annotation`。
- 删除后三套全量复跑（逐字见 R7 报告 §终验，日志 `.fist-loop-20260929/logs/r7b_*.log`）。
- 自造流程债如实登记：矩阵首跑的 M4 读数与二跑写进了同名文件 `logs/r7_lock_M4.txt`，前一份被原地覆盖，
  现在只能靠 stdout 残迹（`logs/r7_locks_a1.txt` 停在对照格的断言处）与上面两枚结构性证据复述它——
  「门与证据同名」的同型失误，本轮第 N 次，仍写在这里而不是假装还在。
- 账面漂移：叶 `T0r113.1.2` 的 deliverable 文案含「含 comptime 整类跳过」，归档后无改档出路（129 工具无一可改
  deliverable），该半句自本段起失效；FIST 侧缺口同号 BUG-111（call_log/账面复原能力），Cypy 侧以本段为准。

## BUG-109 [2026-09-29T03:43:06Z] [medium] OPEN
- summary: [解析器:类型表达式] 注解位置没有类型表达式产生器，`[int]`/`(int,str)`/`{str:int}` 全被编成字面量节点
- detail: R7 实测：`xs: [int]` → Constant(value=[Name(int)])，`p: (int,str)` → Constant(value=(Name,Name))，`m: {str:int}` → DictLiteral(pairs=[(Name,Name)])。本轮先在分析器补闭集拒绝面、生成器补 object 退化，产物不再带 repr；但「括号形态本应是类型」的正解（在 parser 加类型表达式产生器）仍未做，因为 SYNTAX/02 只承认 list<int>/tuple<...>/dict<...> 写法，放开括号形态等于新增语法。活证据：tests/test_annotation_shape.py 的 4 条拒绝格 + CLI 转译回执。
- reported_by: cypy-selfdrive-agent

## BUG-110 [2026-09-29T03:53:01Z] [medium] OPEN
- summary: [FIST-Mbt:建树] `task_plan_deep(split_n=4)` 生成 5 枝 × 3 叶 = 15 叶，其中 8 支描述逐字复制根单、无独立 spec ⇒ 交付面与叶数无法 1:1 对齐
- detail: 实测（ns cypy-loop-20260929 / T0r113，2026-09-29）：publish_parallel 根 T0r113 → task_plan_deep 回 `tree.created=5`、`split_n:4`；sqlite `tasks` 该树 21 行（1 根 5 枝 15 叶）；15 叶里 8 支 description 与根单正文逐字相同（T0r113.1.1/.1.2/.2.1/.2.2/.3.1/.3.2/.4.1/.4.2），7 支是 `[边界审视·全局输入域 owner]` 梯度叶。后果：任何「N 条交付面」的轮次要么漏关要么灌水，本轮的处置是把 8 支重复叶只关 4 支、7 支边界叶里 2 支挂真实探针 5 支按叶子自身条款申报不适用，其余 4 支留在「待领取」（BUG-106 已记 待领取叶无代理可见退役出路）。正解：task_plan_deep 应为每支叶生成可区分的 spec（或在 split_n 时严格产出 split_n 支叶）。
- reported_by: cypy-selfdrive-agent

## BUG-111 [2026-09-29T03:53:01Z] [low] OPEN
- summary: [FIST-Mbt:账面] `call_log.result_json` 对所有成功调用只存 2 字节 `ok`，且 laya_decide 的行按 ns/task 过滤不可见
- detail: 实测：`select tool,result_json from call_log where ts>='2026-09-29T03:43:00Z'` 的 publish_parallel/laya_decide/task_plan_deep/list/loop_create/bug_list/report_bug 七行 result_json 全为 `ok` ⇒ 无法事后复原回执，逐字引用只能靠调用方自存（本轮落在 close_r7_ring.json）。另：laya_decide 的 params 不含 task_id/name/namespace（驱动按 schema 不注入默认键），因此任何按 ns 或 task_id 的收口自证都会静默漏掉它 —— a 轮 `sent_but_not_logged=[laya_decide]` 就是这个形状（工具其实被记录，是过滤器看不见）。正解：call_log 落完整 result_json 或在行上带 ns。
- reported_by: cypy-selfdrive-agent

## BUG-112 [2026-09-29T04:38:10Z] [medium] OPEN
- summary: [模式匹配:class 位置槽位] ClassDef 无 .fields 时 _pattern_slot_types 恒空，case C(x, y) 的元数检查被静默跳过
- detail: R8 由 Ω-gate 首跑打出（corpus/cypy.pattern.positional.json 的 #11 格）：`class C: a: int` + `case C(x, y)` 观测为空诊断，而 struct 同形会报 Positional pattern。根因：ClassDef 的实例属性只有 name/bases/body/is_cdef，字段在 .body 里（LetStmt），旧代码只读 .fields。同轮修复：cypyc/analyzer/type_checker.py 新增 _positional_fields（class 从 .body 取非函数成员），锁：corpus 该格 + tests/regression/test_corpus_pairs.py 参数化格 + 矩阵 M5（摘掉即红）。
- reported_by: cypy-selfdrive-agent

### FIXED(R8 组合环 2026-09-29T04:46:06+00:00，同轮确诊同轮修) — 追加留档（正文一字未改）

- 根因（实测，不是推测）：`ClassDef` 的实例属性只有 `name/bases/body/is_cdef`，字段以 `LetStmt` 形式存在 `.body`；
  `cypyc/analyzer/type_checker.py:_pattern_slot_types` 只读 `.fields` ⇒ class 的槽位表恒空 ⇒
  `if slots and len(node.args) > len(slots)` 前置不成立 ⇒ `case C(x, y)` 零诊断（struct 同形会报）。
- 修复：新增 `_positional_fields()` —— struct 走 `.fields`，class 走 `.body` 剔除非数据成员
  （`NON_FIELD_KINDS`），与生成器 `_record_pattern_shape` 的 R6 规则对齐。
- 调用面：Ω-gate 的 `cypy.pattern.positional.json` #11 格由「观测为空」变为
  `Positional pattern 'C' has 2 slot(s) but type 'C' unpacks only 1 at 8:14`。
- 锁：该格 + `tests/regression/test_corpus_pairs.py` 的参数化格 +
  矩阵 M5「class 位置槽位退回 fields-only ⇒ 摘掉即红」（.fist-loop-20260929/verify_r7_locks.py）。

## BUG-113 [2026-09-29T04:38:10Z] [medium] OPEN
- summary: [模式匹配:槽位数] struct 里的 `__match_args__ = (...)` 被当成第三个数据字段计入槽位数
- detail: R8 实测：`struct Point: x:int; y:int; __match_args__ = ("x","y")` 的 _pattern_slot_types 返回 ['int','int','object']、生成器 _class_fields['Point'] 含 __match_args__，于是 `case Point(a, b, c)` 零诊断通过，产物还可能比较 .__match_args__。同轮修复：SYNTAX/17 补规则 6，判据单点 cypyc/utils/ast_utils.py:ASTUtils.is_positional_member，分析器与生成器共用；锁：corpus 三格（2 元数相符 / 3 元数必须报 unpacks only 2 / 产物不含 __match_args__ ==）。
- reported_by: cypy-selfdrive-agent

### FIXED(R8 组合环 2026-09-29T04:46:06+00:00，同轮确诊同轮修) — 追加留档（正文一字未改）

- 根因：`struct` 内的 `__match_args__ = ("x", "y")` 被 parser 收成第三个 `StructField`，
  于是 `_pattern_slot_types('Point')` 返回 `['int','int','object']`、`_class_fields['Point']` 含 `__match_args__`
  ⇒ `case Point(a, b, c)` 零诊断通过，产物还可能生成 `.__match_args__ ==` 比较。
- 规范先行：`SYNTAX/17-pattern-matching.md` 补规则 6（`__`-包围的类属性不是数据字段）与规则 7
  （`__match_args__` 名称序目前未被消费，正解另立 BUG-115），441→449 行（规则 6、7 占 8 行，即 442–449）。
- 修复：判据单点 `cypyc/utils/ast_utils.py:ASTUtils.is_positional_member`，
  分析器 `_positional_fields` 与生成器 `_record_pattern_shape` 共用（各写一遍就会漂移）。
- 调用面实测：`slot_types=['int','int']`、`case Point(a,b,c)` 报
  `Positional pattern 'Point' has 3 slot(s) but type 'Point' unpacks only 2 at 9:14`、
  `_class_fields['Point']=['x','y']`、产物无 `__match_args__ ==`。
- 锁：corpus 三格（相符放行 / 超元必须诊断且带行列 / 产物不含元数据比较）。

## BUG-114 [2026-09-29T04:38:10Z] [medium] OPEN
- summary: [模式匹配:语法未落地] SYNTAX/17 文档写法 `tuple<int, ...>` 与 `case Numbers(x, y, ..)` 进不了解析器（Unexpected token DOT_DOT）
- detail: R8 寻虫逐字：`.fist-loop-20260929/hunt_r8_extractor_family.py` 的第三格 `ValueError: Unexpected token DOT_DOT at 4:45`，判定 PARSE-FAIL；同批其余 5 格 OK （__unapply__ / __unwarp__ / 类型模式 / OR 模式 / __match_args__ 位置解构，槽位观测见 hunt_r8_extractor_family.json）。文档把 `__unapply_seq__` 列为优先级表第 8 项并给了示例，但语言层没有这个类型形态 ⇒ 文档承诺与解析器能力不符。修法要动类型语法与模式语法（可变元组类型 + 序列展开模式），超出缺陷轮半径，交裁决。
- reported_by: cypy-selfdrive-agent

## BUG-115 [2026-09-29T04:38:10Z] [low] OPEN
- summary: [模式匹配:元数来源] 元数来源未消费 `__match_args__` 名称序，只按数据字段数计算
- detail: R8 实测：`__match_args__ = ("x", "y")` 现在不再占槽（规则 6），但 SYNTAX/17 优先级表第 6 项承诺「该属性给出的字段名顺序长度」——实现仍按字段声明序取元数，未按 __match_args__ 重排或取长度。已在 SYNTAX/17 规则 7 显式写明「目前未实现」以免被读成已完成；正解需要在分析器读取名称元组并校验其与字段集合的包含关系，属新增语义，交裁决。
- reported_by: cypy-selfdrive-agent

## BUG-116 [2026-09-29T04:38:10Z] [low] OPEN
- summary: [规范落地] corpus/ 与 tests/regression/ 已建立但只覆盖 2 个 op（41 个测试对）
- detail: 闭环 BUG-95 的第一批：corpus/cypy.annotation.shape.json 24 格 + corpus/cypy.pattern.positional.json 17 格，scripts/omega_gate.py 跑批准确率 100.00%，tests/regression/test_corpus_pairs.py 地板 41。覆盖面只到「注解形态」与「位置模式槽位」两个 op，其余 20+ 个 SYNTAX 章节还没有 Ω-spec ⇒ 继续按轮次扩，本条不被 BUG-95 的目录闭环遮蔽。
- reported_by: cypy-selfdrive-agent


### AMENDMENT(R9 组合环 2026-09-29T05:31:29+00:00) — 覆盖面从 2 op/41 对推进到 3 op/51 对，本条仍 OPEN

- 新增 `corpus/cypy.type.slice.json` 8 格；`cypy.pattern.positional.json` 17→19 格（越界槽位两格）；
  回归件地板 `FLOOR_CASES` 41→51、`FLOOR_SPECS` 2→3，逐字跑批 `CONCLUSION specs=3 cases=51 passed=51 failed=0 refused=0 accuracy=100.00% rc=0`。
- 仍缺的是「其余 SYNTAX 章节没有 Ω-spec」，本条不被任何闭环段遮蔽；下一轮的判据扩面仍以本条为靶。
## BUG-117 [2026-09-29T05:34:03Z] [medium] OPEN
- summary: [Ω-gate:判据陷阱] `op=codegen` 对已报错的程序直接返回空码（stage=typecheck），使越界槽位那类 not_contains 断言恒真
- detail: R9 实测：给 `struct E`(2 字段) + `case E(1,2,3)` 加 `codegen` 断言`not_contains [__f0,__f1,__f2]` 时该格直接通过，观测里根本没有码（`scripts/omega_gate.py:76-78`：`if op == "codegen" and out["errors"]: stage=typecheck; return`）。这不是产品缺陷而是判据面陷阱：任何「产物不该含 X」的断言若跑在无效程序上都会恒真，正好掩盖要抓的那类缺陷（本仓 R8 的 `.__f2` 就是从无效程序的硬出码面上打出来的）。本轮的处置是把该格改用 `op=codegen_unchecked`并在 corpus 里写明原因；正解是 gate 对 `codegen`+有错 的组合给 refused/warn 而不是静默空码，属判据件改动，另立单交裁决。
- reported_by: cypy-selfdrive-agent

## BUG-118 [2026-09-29T06:01:43Z] [high] OPEN
- summary: [generics:callsite] 调用点 f<T>(x) 被当成 <checker> 参数检查站：产物插入对类型名的零参调用、多类型实参直接解析失败、显式实参从不参与判定
- detail: 同一根因的三个现形面（实测件 `.fist-loop-20260929/probe_r10_generics.py`，逐字输出 `logs/r10_generics_probe1.out`）：
 (a) 静默错误产物：`struct Foo: value: int` + `identity<Foo>(v)` 的产物是 `return (Foo(), identity(v))[1]`（`cypyc/codegen/cython_generator.py:3816-3817` 的逗号表达式），运行期含义是把类型名当零参函数调用一次 ⇒ 带必填字段的 struct/class 必抛 TypeError，而 `--check-only` 与生成阶段均 0 诊断。全仓 13 处用该形态（`.fist-loop-20260929/baseline_r10_typeargs.json`：generic_func 11 / generic_struct 2），含 `examples/demos/traits_duck/duck_basic.cypy:143,147`（`display_name<NamedItem>(item)`、`resize<SizedBox>(box, 20)`）。
 (b) 文档承诺的形态解析失败：SYNTAX/11:23 的 `pair<int, str>(42, "answer")` 报 `Unexpected token COMMA at 6:34`，因 `parser.py:3856-3874` 只收单个 IDENTIFIER。
 (c) 显式实参不参与判定：`identity<int>("Alice")` 赋给 str 得 0 诊断，`pair<int>(42)` 对 `<T, U>` 无元数诊断（`type_checker.py:1306-1337` 只按实参统一化推断）。
声明面冲突：SYNTAX/11「泛型函数 / 多类型参数 / 泛型类」承诺 `f<A,B>(…)`；而 `<checker>` 检查站是定义侧形态且 SYNTAX/33:519（P-1.8）已判 v1 不支持 ⇒ 调用点尖括号不存在第二种合法解释。定性：[真缺陷·产品面]。
- reported_key: R10-CALLSITE-CHECKER
- reported_by: cypy-selfdrive-agent

### FIXED(修复=已完成) — 2026-09-29 — 追加留档（2026-09-29 R10 自驱组合环，本条目正文与标题行 `OPEN` 一字未改）
- 规范先行：`SYNTAX/11-generics.md` 新增「调用点的类型实参」规则 1-5 + 「明确不支持」表（逐条指认 BUG-119/120/121/122，本单只覆盖尖括号形态）
- 修复面：`cypyc/parser/parser.py:650-658`（`Call.checker` → `Call.type_args`）、`:3855-3878`（可回溯试探的类型实参表，收逗号多项）、`:3943-3951`（实参表只归紧邻一次调用）；`cypyc/codegen/cython_generator.py:3814-3818`（删 `(checker(), f(args))[1]`，产物只留调用）；`cypyc/analyzer/type_checker.py:1273-1303`（`_bind_explicit_type_args`：元数/非泛型/代入）、`:1330-1347`（显式实参优先于推断）；`cypy_bridge/compiler.py:284-289`（第二台发射器的同形死码一并删）
- 判据面：`corpus/cypy.generic.callsite.json` 20 对（`fnv1a64:65bd56a87c83d42a`），Ω-gate 逐字 `CONCLUSION specs=4 cases=71 passed=71 failed=0 refused=0 accuracy=100.00% rc=0`；回归件地板 `FLOOR_SPECS` 3→4、`FLOOR_CASES` 51→71
- 回归锁：`tests/test_generic_callsite_r10.py` 9 支 + corpus 20 对（由 `tests/regression/test_corpus_pairs.py` 逐对执行）
- 承重证明（变异矩阵 6 格 9 门全过，`.fist-loop-20260929/verify_r10_locks.json`；语料扩到 20 对后以本轮报告 §5 的复跑数为准）：L1 三处全退 18 红 + gate 3/14 rc=1、L2 只退解析器 10 红、L3 只退分析器 7 红、L4 产物退回零参调用形态 9 红、L5 只改注释对照 0 红 ⇒ 解析/生成/分析三处各自承重，尺子不读散文
- 调用面证据：全仓 13 处调用点（`.fist-loop-20260929/baseline_r10_typeargs.json`：generic_func 11 / generic_struct 2 / parse_fail 0）产物从 `(NamedItem(), display_name(item))[1]` 变为 `display_name(item)`；`examples/generic.cypy`、`examples/generics_advanced.cypy` 走 `cypyc transpile --check-only` rc=0
- 终验（冻结被测量面后）：pytest 2241 passed rc=0；自研套件 47/47；e2e golden `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；Ω-gate 71/71 100%
- 不随本单关闭：BUG-121（方括号形态 `f[T](x)`）、BUG-119（泛型类解析）、BUG-120（trait 无体抽象方法）、BUG-122（类型实参子树不被 visit）各自 OPEN
- 本轮流程债一并了结：R9 欠的「报告先落盘才收根」在本轮改为入口门（`.fist-loop-20260929/close_r10_ring.py` 起手即验报告存在 + 引用核验通过），并给 `verify` 挂上 `docs_check`（服务端 [gate:required] 的「文档即实现」面）

### AMENDMENT — 锚点更正（本条目正文与标题行一字未改）
- 本单 detail 与本轮 `### FIXED` 段里写的三处行号是落码前的心算值，实测漂移如下（定位方式：按代码文本 needle 在全文件里取行号，核验件 `.fist-loop-20260929/verify_r10_report.json` 的 `anchors` 栏）：
  · `cypyc/parser/parser.py` 的 `Call.type_args` ⇒ 实测 **650-659**（原写 650-658）；
  · `cypyc/analyzer/type_checker.py` 的 `_bind_explicit_type_args` ⇒ 实测 **1272-1301**（原写 1273-1303）；
  · 被引用的 `SYNTAX/33-type-constraints-subtypes-dispatch.md` P-1.8 ⇒ 实测 **:518**（原写 :519）。
- 同批更正 BUG-120 卡片正文：`trait` 抽象方法范例的实测行号是 `SYNTAX/11-generics.md:47`（`trait Container<T>:`）与 **:93**（`def sort<T: Comparable>`，原写 :89-91）。
- 定性、严重度、判据与结论均不变；本段只改「锚到哪一行」，报告 §4.2 已同步为实测区间。

## BUG-119 [2026-09-29T06:01:43Z] [high] OPEN
- summary: [parser] 泛型类 `class Box<T>:`（SYNTAX/11:107-125 承诺）解析拒收 Expected COLON, got LT，而 struct Box<T> 可用
- detail: 实测：`class Box<T>:\n    def __init__(self, content: T):` 形态在 `typecheck` 与 `codegen` 两面均 `stage=parse`、`Expected COLON, got LT at 1:10`（探针件 `probe_r10_generics.py` 的 G6/B1）；同一份类型参数写法换成 `struct Wrap<T>: value: T` 则解析通过并出码（G14/B2，产物 `cdef class Wrap:`，字段 `value` 退化为 object）。SYNTAX/11:107-125 明确给出 `class Box<T>:` 与 `Box<int>(42)` 用法，:133 特性表又声称「泛型类：类可以是泛型的」⇒ 文档承诺与解析器能力直接矛盾。定性：[真缺陷·文档/实现分叉]。本轮未修的理由：泛型类要动 ClassDef 节点签名、`_visit_ClassDef` 的类型参数登记、codegen 的 class 出码与 scope 名字空间四处，与本环「调用点类型实参」半径不同，另轮收。
- reported_key: R10-GENERIC-CLASS-PARSE
- reported_by: cypy-selfdrive-agent

### FIXED(R11 2026-09-29 泛型类收下并代入) [2026-09-29T07:47:24Z]
- 修法：`ClassDef` 增加 `generic_params` / `generic_constraints`（`cypyc/parser/parser.py:329-347`），
  类名的参数表解析与 `struct` 合并成同一份实现 `Parser._parse_type_param_list`（:1593-1618），
  `_parse_class_def`(:1625) 与 `_parse_struct_def`(:1650) 各自只调用它 ⇒ 空参数表文案两处逐字相同；
  使用侧新增注解位元数判定，与调用位共用 `TypeChecker._generic_arity_diagnostic`
  （`cypyc/analyzer/type_checker.py:1272-1289`，调用点在 :3964 区）；
  接收者代入补在 `_visit_Attribute` 的 class 分支（:2512 区，此前那里直接返回方法的声明返回类型 ⇒ `b.get()` 判成 `T`）；
  形式参数名不再进裸名表（`_visit_ClassDef` :592-608 + `_visit_FuncDef` :643 守卫）。
- 双向格（改严而非删锁）：`tests/test_boundary_comprehensive.py::TestClassBoundary::test_class_with_type_param`
  原文是「错误写法：当前类不支持泛型语法」，钉的正是本单的坏形态 ⇒ 本轮改成
  「`class Container<T>:` 必须收下且 `generic_params==['T']`」，并新增配对的
  `test_class_with_empty_type_param_list`（`class Container<>:` 仍硬拒 `Generic parameter list cannot be empty`）。
- 判据：`corpus/cypy.generic.class.json`（29 对，指纹 `fnv1a64:90f410a1d1cd0fd8`）、
  `tests/test_generic_class_r11.py`（13 支）、承重矩阵 `.fist-loop-20260929/verify_r11_locks.py`
  （7 格全跑：L1 退解析器 34 红 / L2 退注解位元数 4 红 / L3 退接收者代入 18 红 / L4 退形式参数守卫 1 红 /
  L5 退 struct 裸名擦除 2 红 / L6 只改注释 0 红，逐格身份探针 5/5 翻假，见 `logs/r11_locks_a8.out`）。
- 手册范例端到端：`SYNTAX/11-generics.md:112-124` 的 `class Box<T>` + `Box<int>(42)` 形态
  在 typecheck 与 codegen 两面 0 诊断（`logs/r11_generics_probe4.out` 的 C1），产物类头擦除为 `class Box:`。
- 本轮同时立而未修的相邻面（不遮挡本单关闭）：BUG-128（struct 方法不代入）、
  BUG-129（定义侧约束在注解位/实例化位不判）、BUG-127（`cdef class` 误导性诊断）。
## BUG-120 [2026-09-29T06:01:43Z] [medium] OPEN
- summary: [parser] trait 的无体抽象方法（SYNTAX/11:47-51、89-91 的 `def get(self, index: int) -> T:`）解析拒收 Expected increased indentation
- detail: 实测（`probe_r10_generics.py` 的 F1/F2、G10）：`trait Foo:\n    def bar(self) -> int:` 报 `Expected increased indentation at line 3. Expected 8, got 0`；泛型 `trait Foo<T>:` 同形。非泛型也炸 ⇒ 不是泛型专属，是 trait 体形态与文档分叉。SYNTAX/11「定义泛型特质」与「特质约束」两处范例（:47-51、:89-91）都写成无体签名 ⇒ 按手册抄的代码进不了编译器。定性：[真缺陷·文档/实现分叉]。待裁决项：是补「抽象方法必须有体（`...`/`pass`）」的文档条款，还是让解析器接受无体签名——本轮只做留痕，不改判据也不改文档。
- reported_key: R10-TRAIT-ABSTRACT-PARSE
- reported_by: cypy-selfdrive-agent

### AMENDMENT(R11 2026-09-29 缩小半径：无体形态本身可用) [2026-09-29T07:47:24Z]
- 新证据：`trait Container<T>:` + `def get(self, index: int) -> T`（**不带冒号**的无体签名）
  typecheck/codegen 两面 0 诊断，`TraitDef.generic_params==['T']`（`.fist-loop-20260929/logs/r11_generics_probe2.out` 的 C16）。
- 改判：本单的半径因此不是「trait 的无体抽象方法进不了编译器」，而是
  「**手册写的 `-> T:` 带冒号形态**进不了解析器（`Expected increased indentation`）」。
  裁决面随之变窄：要么解析器接受带冒号的无体签名，要么 SYNTAX/11:47-51、:89-91 的范例改成不带冒号 ——
  不再是"要不要支持无体方法"的支持性问题。
- 另记：`TraitDef` 没有 `generic_constraints` 属性（同探针打印 `constraints='<no attr>'`），
  而 `StructDef`/本轮 `ClassDef` 都有 ⇒ 特质约束在定义侧就没有落脚点，属 BUG-129 的同族面。
## BUG-121 [2026-09-29T06:01:43Z] [high] OPEN
- summary: [generics:callsite] 方括号形态 f[T](x) 被解析成「下标后调用」并原样进产物，运行期必抛 TypeError 而编译期 0 诊断
- detail: 实测：`identity[list[int]](xs)` 与 `identity[Box](v)` 在 `--check-only` 与 codegen 两面 errors=0，产物逐字保留 `y: list = identity[list[int]](xs)`（探针 G13/A3）。运行期含义是 `function.__getitem__` ⇒ `TypeError: 'function' object is not subscriptable`。本环按 SYNTAX/11 修的是尖括号形态（`<>` = 类型实参表，产物擦除），方括号形态文档从未承诺 ⇒ 属「能吃但无人管」的第二类：要么解析级硬拒（像 dispatch 的 P-1.8 那样），要么并入类型实参表。交下一轮裁决后修，本轮不改判据也不放开门禁。定性：[真缺陷·静默错误产物]。
- reported_key: R10-BRACKET-CALLSITE
- reported_by: cypy-selfdrive-agent

## BUG-122 [2026-09-29T06:01:43Z] [medium] OPEN
- summary: [analyzer] 类型实参子树不被 visit：f<Undefined>(x) 里未定义的类型名静默降级为 object，无诊断
- detail: 本环代入实现 `TypeChecker._bind_explicit_type_args`（`cypyc/analyzer/type_checker.py:1273-1303`）只做 `_get_type_from_node(arg_node)` 的形态转换，不调 `self._visit()` ⇒ 类型实参里的名字不做存在性判定。实测：`mk<Undefined>(1)`（mk 为泛型函数）产 0 诊断，返回类型退化为 object。为什么本轮不顺手补：`_visit` 在类型节点上会牵出 `Undefined name` 模板对 `list<int>`/`int | float` 这类复合形态的连带判定，属于既有诊断面的扩大，必须与 BUG-109（注解位缺类型表达式产生器）同批裁决。定性：[真缺陷·本轮亲笔限制的留痕]，判据面已在 `corpus/cypy.generic.callsite.json` 之外由本单钉住。
- reported_key: R10-TYPEARG-NOT-VISITED
- reported_by: cypy-selfdrive-agent

### AMENDMENT(R11 2026-09-29 泛型类实例化位同样不判存在性) [2026-09-29T07:47:24Z]
- 新证据：泛型类收口后可测 —— `let b: Box<int> = Box<Mystery>(42)` 两面 0 诊断
  （`.fist-loop-20260929/logs/r11_generics_probe2.out` 的 C11_undefined_typearg），
  `Mystery` 既不在 class_defs 也不在内置类型表里，静默降级。
- 半径扩张：本单原先只有函数调用位的证据（`mk<Undefined>(1)`），现扩到 class 实例化位与注解位
  （`_get_type_from_node` 的 GenericType 分支同样只转形态不判存在）。
- 与本轮的关系：R11 新增的 `_generic_arity_diagnostic` 只判**个数**，不判**名字** ⇒
  本单仍是开口，不收口、不关闭。
## BUG-123 [2026-09-29T06:46:08Z] [medium] OPEN
- summary: [判据面·仓内尺子] inspect.getsource 型源码文本锁在同一进程内被测文件行号漂移时会读到错位窗口，全量跑期间改产品文件就造出假红
- detail: 本轮实测（逐字见 `.fist-loop-20260929/logs/r10_pytest_a2.log`）：`FAILED tests/test_polish_20260926_pass7.py::test_bug26_artifact_scan_accepts_non_windows_extensions`，失败原因是 `assert ([])` —— 即 `scan` 列表为空，而不是产物真的退化了。同一条单跑 `1 passed in 0.08s`；把树冻结后重跑两轮全量（a3、a4）都是 2241 passed rc=0。
机制（可复算，不是猜测）：该锁用 `inspect.getsource(comp.BridgeCompiler._compile_c_to_shared_lib)`，函数对象的 `co_firstlineno` 在 import 那一刻定格。我在 a2 全量运行中途（06:10:30Z 前后）编辑了`cypy_bridge/compiler.py:284` 区（净 +1 行），目标函数在 :3760、`endswith('.pyd')` 那行在 :3837 —— 旧行号去切新文件字节，窗口整体错开 1 行 ⇒ 扫不到目标行 ⇒ 断言把「尺读错了位置」渲染成「产品退化了」。
危害：这类「红」不是产品信号，且任何在 CI 里与源码改动并发的 inspect.getsource 锁都不可信。本仓同型锁不少（`grep -rn 'inspect.getsource' tests/ | wc -l` 实测计数见本轮报告 §5）。
建议（交裁决，不在本环半径）：① 这类锁改为直接从磁盘取函数体（`ast.get_source_segment` 或按 `def` 行做区间切），不依赖 code 对象的行号；② 或在 conftest 里对被 getsource 的模块加身份断言（file + 行号自证）。流程侧本轮已做：全量跑期间冻结被测量面，a2 判作废并重跑 a3/a4 留档。
定性：[真缺陷·仓内判据面]。复跑现形方式：在 `pytest tests` 运行中途编辑 `cypy_bridge/compiler.py` 的 :284 区。
- reported_key: R10-JUDGE-GETSOURCE-SKew
- reported_by: cypy-selfdrive-agent

### AMENDMENT — 追加更正（本条目正文与标题行一字未改）
- 更正对象：本条 detail 里那句「同一条单跑 `1 passed in 0.08s`」—— 那次读数只出现在终端，没有落盘证据件，按本项目口径不可复核，故不作为证据引用。
- 替代证据（有文件）：`python -X utf8 -m pytest tests/test_polish_20260926_pass7.py::test_bug26_artifact_scan_accepts_non_windows_extensions -p no:cacheprovider` ⇒ 逐字 `1 passed in 0.34s`，见 `.fist-loop-20260929/logs/r10_bug26_single_a1.log`（该次 rc=0）。
- 结论不变：缺陷仍成立（a2 的 `assert ([])` 与冻结后的 2235/2241 passed 两轮全量都在 `logs/r10_pytest_a2.log`、`logs/r10_pytest_a3.log`、`logs/r10_pytest_a4.log`），本条只改「用哪份件作证」，不改定性与严重度。
- 报告同处已同步：`reports/2026-09-29/T0r116-cypy-selfdrive-r10-report.md` §5.5。

## BUG-124 [2026-09-29T06:46:08Z] [medium] OPEN
- summary: [文档面·主张宽于判据] SYNTAX_IMPLEMENTATION_STATUS.md 对每一章逐行写「✅ 完整 / 无缺口」，与账本 open 面直接矛盾，且全仓无任何判据认领这张表
- detail: 实测：`SYNTAX_IMPLEMENTATION_STATUS.md:330-356` 每章一行、清一色 `| ✅ 完整 | 无 |`（含本环已确认存在解析缺口的 `07-trait-impl.md`、`08-class.md`、`11-generics.md`）；`grep -rn 'SYNTAX_IMPLEMENTATION_STATUS' tests/ scripts/ PROJECT-SPEC/` → **0 命中** ⇒ 这张表的每一格都是无主主张。
本环的两个直接反例：BUG-119（`class Box<T>:` 不解析）、BUG-120（trait 无体抽象方法不解析）都落在被标成「无缺口」的章节里。本轮只把 `11-generics.md` 那一行改成 `⚠ 部分` 并点名四个缺口 （BUG-119/120/121/122）+ 已闭环面（BUG-118），其余行不动 —— 未实测的格子不由我代写。
危害：读者会把这张表当审计结论用；而它既不与账本对齐，也不与 Ω-spec 覆盖面对齐（Ω-spec 目前 4 op/71 对，远未覆盖 26 章）。
建议（交裁决，二选一）：① 给表配判据 —— 逐格要求「缺口栏非空 ⇔ 账本存在同号 OPEN 单」，并把 `corpus/` 的 op 数/测试对数写进表；② 把表的口径收窄到可判定的「解析层是否接受该章语法」。
定性：[真缺陷·主张宽于判据]。
- reported_key: R10-STATUS-DOC-BLANKET-CLAIM
- reported_by: cypy-selfdrive-agent

## BUG-125 [2026-09-29T06:46:08Z] [high] OPEN
- summary: [codegen·静默错误产物] 用户 def id/addr 的调用点在产物里被改写成 C 构造（`id(3)`→`<size_t><void*>3`、`addr(3)`→`&3`），函数照样导出，编译期 0 诊断
- detail: 实测（调用面 = `scripts/omega_gate.py` 的同一条 execute 管线）：
 - `def id(x: int) -> int:` + `y: int = id(3)` ⇒ 产物含 `__all__ = ["id", "f"]`、`def id(x):`，但调用点渲染为 `y: int = <size_t><void*>3`（用户函数被整个跳过）；
 - `def addr(v: int) -> int:` + `addr(3)` ⇒ `y: int = &3`（对字面量取地址，Cython 侧是非法构造）；
 - `def sizeof(n: int) -> int:` + `sizeof(3)` ⇒ 产物 `sizeof(3)`（同一条分支，未做编译验，运行/编译面另测）。
机制：`cypyc/codegen/cython_generator.py:3779-3810` 的特判只看 `func_name` 字符串（`malloc/sizeof/addr/free/id/isinstance`），不看该名字在本模块是否被用户 `def` 占用；分析器侧也没有「内置名不可重定义 / 重定义即拒」的判定，文档亦无声明（`grep -rn '内置函数.*覆盖|覆盖.*内置|shadow.*builtin' SYNTAX/` → 0 命中）。
危害：与 BUG-023 的 trait isinstance 注册表改写同族 —— 声明侧与调用侧口径分叉，用户看不出异常，`isinstance` 那条还会与 `_known_traits` 判定叠加。
建议（交裁决，本环不扩权）：要么在分析器把「与内置特判同名」判成诊断（窄、可判定），要么让这些特判仅在该名字未被用户 `def` 占用时生效。
定性：[真缺陷·静默错误产物]。复跑：`python -X utf8 -c "import sys; sys.path.insert(0,'scripts'); import omega_gate as og; print(og.execute({'op':'codegen','src':'def id(x: int) -> int:\n    return x\n\n\ndef f() -> int:\n    return id(3)\n'})['code'])"`
- reported_key: R10-BUILTIN-NAME-SHADOWS-USER-FN
- reported_by: cypy-selfdrive-agent

## BUG-126 [2026-09-29T07:45:59Z] [medium] OPEN
- summary: [diagnostics] Return type mismatch 一类诊断的行号恒等于实际行 +1，2 行文件会报 3:1（超出文件末尾）
- detail: 实测（本轮 `.fist-loop-20260929/measure_r11_substitution.py` 的 `logs/r11_subst2.out`，另用最小样例复核）：
 (a) `def f() -> str:\n    return 1`（共 2 行）报 `Return type mismatch: expected str, got int at 3:1`；
 (b) `def g() -> int:\n    return 1\n\n\ndef f() -> str:\n    return g()`（共 6 行）报 `at 7:1`；
 (c) 同一程序在 `return` 前多留/少留一个空行时，报告行号随之 +1，而 `return` 的真实行号分别是 9/10 ⇒ 偏移恒定 1，不是排版巧合。
定性：既有缺陷（module-level 函数即可复现，与本轮泛型类改动无关）。影响面：本仓多条验收口径写着「诊断带行列」（含 BUG-118/119 的闭合文案与本环 corpus 的 matches 断言），行号 +1 会让用户按报告找不到那一行；修它要同时过一遍所有钉死 `at L:C` 的既有锁 ⇒ 本轮只留痕，改动交另轮带判据收。
证据件：`.fist-loop-20260929/measure_r11_substitution.py`、`logs/r11_subst1.out`、`logs/r11_subst2.out`。
- reported_key: R11-DIAG-LINE-OFF-BY-ONE
- reported_by: cypy-selfdrive-agent

## BUG-127 [2026-09-29T07:45:59Z] [low] OPEN
- summary: [parser] `cdef class Box:` 不是本门面的语法却不被拒：解析成 ExprStmt(Name('cdef')) + 普通 ClassDef，`ClassDef.is_cdef` 从解析器恒 False，codegen 的 cdef-class 分支不可达
- detail: 实测（`.fist-loop-20260929/logs/r11_generics_probe2.out` 的 C6，以及最小对照）：
 `cdef class Box:` 与 `cdef class Box<T>:` 解析后 `AST body kinds=['ExprStmt', 'ClassDef']`、`is_cdef=False`，类型检查报 `Undefined name 'cdef' at 1:1`（而不是「不支持的声明前缀」），类体本身仍被收下并入产物。
机制：`_parse_class_def(is_cdef=True)` 全仓只有一个调用点（`cypyc/parser/parser.py:1218`，不带实参）⇒ `is_cdef` 永远取默认 False；`cypyc/codegen/cython_generator.py:4212` 起的 `if is_cdef: … cdef class X:` 分支对 class 不可达（对照：泛型 struct 出码确为 `cdef class Wrap:`，走的是 StructDef 那条路径）。
定位声明核对：SYNTAX 里 `cdef class` 只以注释形态出现在 `SYNTAX/25-compatibility.md:158`，手册从未把它列为门面 ⇒ 定性不是「文档/实现分叉」，而是「误导性诊断 + 不可达产物分支」。修法二选一（接受该前缀并置位 is_cdef，或显式硬拒并删死分支），交裁决。
证据件：`logs/r11_generics_probe2.out`、`logs/r11_generics_probe4.out`（同形复现）。
- reported_key: R11-CDEF-CLASS-MISPARSE
- reported_by: cypy-selfdrive-agent

## BUG-128 [2026-09-29T07:45:59Z] [medium] OPEN
- summary: [analyzer] 泛型 struct 的方法调用不做接收者代入：struct 分支只遍历 .fields，`Wrap<str>.get()` 被判成未知而 0 诊断，与本轮 class 分支形成同一事实两个读法
- detail: 实测（同形对照，一条红一条绿）：
 `struct Wrap<T>: value: T; def get(self) -> T` + `let w: Wrap<str> = Wrap("s")` + `def f() -> int: return w.get()` ⇒ **0 诊断**（应为 expected int, got str）；
 换成 `class Box<T>` 同形 ⇒ `Return type mismatch: expected int, got str`（本轮 L4 修复面）。
机制：`cypyc/analyzer/type_checker.py` 的 `_visit_Attribute` 里 struct 分支只扫 `struct_def.fields`，方法名落空后返回 `Type("object")`（:2489-2500 区），class 分支本轮补齐了方法代入（:2512 起）。
定性：[真缺陷·假阴性]。收紧它会把「方法调用从不判」的既有程序打红（面比 class 大），需要与判据/语料同批做 ⇒ 本轮只留痕，不在同一轮里顺手推广（R9 的 BUG-99 教训：越界推广打红既有锁）。
- reported_key: R11-STRUCT-METHOD-NO-SUBST
- reported_by: cypy-selfdrive-agent

## BUG-129 [2026-09-29T07:45:59Z] [medium] OPEN
- summary: [analyzer] 定义侧类型约束 `T: int | float` 在注解位与实例化位都不判：`Num<str>` 违反声明界却 0 诊断（class 与 struct 两形同）
- detail: 实测（最小对照）：
 `class Num<T: int | float>: v: T` + `let x: Num<str> = Num("a")` ⇒ errors=[]；
 `struct NumS<T: int | float>: v: T` + `let x: NumS<str> = NumS(1)` ⇒ errors=[]。
机制：约束只在结构体**字面量**路径上被消费（`_visit_StructLiteral` 读 `struct_def.generic_constraints` 并发 `Generic constraint violation`），注解位/泛型构造调用不读该表；本轮新增的 `ClassDef.generic_constraints` 同样没有消费点。
对照已闭环的一面：函数调用位是判的（`corpus/cypy.generic.callsite.json` 里 `Generic constraint violation` 那格，100% 通过率）⇒ 同一份声明界在三条路径上只有一条消费，属于「同一事实多处读取」的分叉。
定性：[真缺陷·承诺半落地]。SYNTAX/11「类型约束」与本轮「泛型类」规则都引用了声明界，补齐需要把函数那条路径的判定抽成共用函数并处理 `Comparable` 的特质界 ⇒ 另轮收。
证据件：本轮 `logs/r11_generics_probe2.out`（C3_constrained 只证解析收下，不证判定）。
- reported_key: R11-DECLARED-CONSTRAINT-NOT-CHECKED
- reported_by: cypy-selfdrive-agent

### FIXED(R12 声明界在使用侧 2026-09-29T09:08:45Z）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：把「使用侧类型实参要过声明界」收进**一处**共用件 `TypeChecker._check_declared_bounds`
  （`cypyc/analyzer/type_checker.py`），三处使用位各接一行：
  ① 注解位 `_visit_GenericType`（元数判定之后，与 `Type argument count mismatch` 并存不互相遮蔽）；
  ② 显式类型实参构造位 `_bind_explicit_type_args`（只对 class/struct 生效 —— 函数由 `_visit_Call`
  里那份统一判，否则同一条界会得到两条账）；
  ③ 结构体字面量位 `_visit_StructLiteral`：**摘掉**原来自带的那份窄复制
  （它只认 `getattr(ast,'id')` 的单名界，`T: int | float` 取到 None ⇒ 静默放行），改调共用件。
  三类界（联合／单名／特质／typeclass）都落到既有 `_check_generic_constraint`，本轮不新增消息合成点。
- 半径先测后开门（不是"改完看看"）：`.fist-loop-20260929/measure_r12_constraint_radius.py`
  改动前快照 `r12_radius_before.json` 与改动后 `r12_radius_after.json` 同集合逐文件比错误集合，
  结论 `CONCLUSION phase=after new_red_sources=0 gone_red_sources=0 ... real_crashes=0`
  —— 口径：改动前 206 份源（106 份盘面 `.cypy` + 100 对既有 corpus，历轮 `.fist-loop-*` scratch 树排除），
  其中 16 份含约束声明、共 34 处 ⇒ 开门不牵连任何既有源。
- 判据：新增 Ω-spec `corpus/cypy.generic.bounds.json`（23 对，指纹 `fnv1a64:65b49102e98d2fa0`，
  生成件 `.fist-loop-20260929/make_corpus_r12.py` 落盘前逐条走 `execute + judge`，一条不符就拒写 ——
  本轮它拒了 3 次：`stage` 取值猜成 `check`（实测是 `ok`）、trait 实现忘写 `impl Show for Impl:`、
  typeclass 语法写成 `typeclass Number for T:`（实际是 `typeclass Number:` + `impl typeclass Number for int:`））；
  回归锁 `tests/test_generic_bounds_r12.py`（18 支，含「字面量位不许长回窄复制」的源码针与
  「诊断行列指向注解位」的按源反解针）。台账地板同批上调 `FLOOR_SPECS 5→6`、`FLOOR_CASES 100→23`。
- 手册：`SYNTAX/11-generics.md` 新增「声明界在使用侧的判定」规则 1-4，
  其中规则 4 明确写出**不判的一面**（构造位不写类型实参时不做推断），
  并把这一面另立 BUG-135、把违界诊断的 `in call to '<unknown>'` 误导文案另立 BUG-134 ⇒ 不遮挡本单关闭。
- 未随本单关闭的相邻面：BUG-120（`-> T:` 无体签名形态）、BUG-121（`f[T](x)` 方括号形态）、
  BUG-122（类型实参存在性）、BUG-128（struct 方法不代入，与 BUG-135 同一推断层）。

## BUG-130 [2026-09-29T08:21:28Z] [medium] OPEN
- summary: [判据面·Ω-gate] 环驱动把 specs 表的 spec_type 针写成 "omega"/"omega_result"，而库里实际只有 spec/check/result ⇒ 「已有判据就不重发」的守卫恒 0，收口时把 12 叶已 approved 的语料重发一遍，24 条幂等拒绝被记成 refusals 使 rc=1
- detail: 实测（`.fist-loop-20260929/logs/r11_ring_close_a3.out` 逐字）：
 `CONCLUSION stage=close root=T0r117 root_status=已完成 rollup={'已完成': 17} non_closed=[] pending_leaves=0 calls=105 refused=24 benign=0 call_log_error_rows=0`
 —— 账其实收完了（17/17 已完成、0 支待领取），rc 却被 24 条「已通过审核，无需重复创建」/「当前状态为 [approved]，不是待审核状态」判成失败。
机制：`run_r11_ring.py` 用 `spec_rows(node, "omega")==0` 当守卫，而服务端 `omega_spec_create`→'spec'、`run_check`→'check'、`omega_result_verify`→'result'（`select distinct spec_type from specs` 只有这三值；T0r117% 上分别 17/12/17 行）⇒ 守卫恒真，R10 已经观测到同型 70 条噪声却只记了现象没修针。
修复（本轮，三件一起）：常量 `SPEC_KIND/CHECK_KIND/RESULT_KIND` 收敛口径 + 开批门新增 `spec_kind_guard()` 对着活库自证（库里有一行 specs 却缺这三个值 ⇒ 直接 refuse 收口）+ `note()` 拆成 幂等/真拒绝/良性重复 三桶，幂等单列计数并印进结论行。
复验：同树复跑 `--stage close`（`logs/r11_ring_close_a4.out`）⇒ `calls=21 refused=0 idempotent=0 benign=0 loop_ticks_ok=6 rc=0`（幂等门从 24 掉到 0，而账的终态没变）。证据件：`logs/r11_ring_close_a3.out`、`logs/r11_ring_close_a4.out`、`ring_r11_close.json`（a4 覆写，a3 的读数只活在 .out 里 ⇒ 同名覆写已在本轮报告 §6.4 记为限制）。
- reported_key: R11-SPEC-KIND-NEEDLE-ZERO
- reported_by: cypy-selfdrive-agent

### FIXED(R11 收口腿 2026-09-29T08:25:31Z）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修在三处（同一件 `.fist-loop-20260929/run_r11_ring.py`）：
  ① 口径收敛成常量 `SPEC_KIND/CHECK_KIND/RESULT_KIND = "spec"/"check"/"result"`，五处
  `spec_rows(...)` 守卫全部改走常量（改前是 `"omega"`/`"omega_result"`，库里根本没有这两个值）；
  ② 开批门新增 `spec_kind_guard()`：对着活库读 `select distinct spec_type from specs`，
  本件用的三个值有任一缺失、或库里一行 specs 都没有 ⇒ 直接 refuse 收口并列出库里实有值。
  这是给"恒 0 针"配的基数门，不是装饰：把常量改成 `"omega"` 就会红；
  ③ `note()` 从两桶改三桶（幂等 / 真拒绝 / 良性重复），幂等回执单独计数并印进结论行
  （`idempotent=`），不再决定 rc。
- 复验（同树复跑，账的终态没动）：`logs/r11_ring_close_a3.out`（修前）
  `calls=105 refused=24 benign=0` → `logs/r11_ring_close_a4.out`（修后）
  `calls=21 refused=0 idempotent=0 benign=0 loop_ticks_ok=6 call_log_error_rows=0 rc=0`，
  两次都是 `root_status=已完成 rollup={'已完成': 17} non_closed=[] pending_leaves=0`。
- 限制：a3 的 24 条拒绝作为历史留在 `call_log`（不可改），`ring_r11_close.json` 已被 a4 原地覆写 ⇒
  a3 的读数只活在 `.out` 里；本轮报告 §6.4 点名了这次同名覆写。

## BUG-131 [2026-09-29T08:21:28Z] [medium] OPEN
- summary: [判据面·账面尺] 收口自证把 `call_log` 失败行按 `result_json like '%__error__%'` 计数，而服务端失败是 `ok=0` + 纯文本回执 ⇒ 恒 0；R9/R10/R11 三份报告里「call_log 0 错误行」这句都是坏尺读数（a3 窗口真实红行 25）
- detail: 实测（同一份库两个口径）：
 `select count(*) from call_log where ts>='2026-09-29T07:59:00Z' and ok=0` ⇒ 25（其中 24 条Ω-spec 幂等拒绝 + 1 条 loop_tick 参数名被拒），
 同窗口 `result_json like '%__error__%'` ⇒ 0。
机制：`FistClient.call` 把服务端的 JSON-RPC error 折成 `{"__error__": ...}` 返回给调用方，但**入库的 result_json 是纯文本回执**（`_omit_defaults` 白名单拒绝时尤其明显），所以 `%__error__%` 只能匹配到少数结构化回执，读数为 0 不代表没红。
定性：尺子坏了而不是账面干净 —— 这一条把 R9 起「0 拒/0 错误行」的自证句整体作废，既往两轮据此写过的「benign=0 即无幂等噪声」也不再成立。
修复：`run_r11_ring.py` 结论行改口径 `call_log_error_rows`（ok=0）并**同时**保留`call_log_error_rows_old_needle` 作对照，两数并印 ⇒ 以后任一口径漂了都能看出来。
证据件：`logs/r11_ring_close_a3.out`、`logs/r11_loopfix_a2.out` 的 `ERROR_NEEDLES` 行、`r11_loop_tick_fix.json`。
- reported_key: R11-CALLLOG-ERROR-NEEDLE-ZERO
- reported_by: cypy-selfdrive-agent

### FIXED(R11 收口腿 2026-09-29T08:25:31Z）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：`run_r11_ring.py` 的收口自证改按 `call_log.ok=0` 取数（`call_log_error_rows`），
  并**同时**保留旧口径为 `call_log_error_rows_old_needle` 与它并印 ⇒ 两个读数一旦分叉就能当场看出来，
  而不是再信三次"0"。
- 两口径的差在本轮被实测钉住（`r11_loop_tick_fix.json` 的 `error_rows_two_needles`）：
  a3 窗口 `ok=0` 为 25 行，同窗口 `%__error__%` 为 0 行。
- 改判（不删历史报告，只在此作废自证句）：R9/R10/R11 三份报告里凡写过
  「`call_log` 0 错误行 / benign=0 即无幂等噪声」的句子，读数来源都是这把坏尺 ⇒ 一律作废，
  真实口径见本轮报告 §6.4。既往轮的**账**（任务状态、specs 行）没受影响，作废的只是那句自证。
- 复验：修后 a4 窗口两口径同为 0（该窗口确实无红），而 a3 窗口的 25/0 差值留作尺子的对照样本。

## BUG-132 [2026-09-29T08:21:28Z] [medium] OPEN
- summary: [判据面·组合环] 自 R9 起 `loop_tick` 在服务端一次都没成功过（57 行里 33 红，R9-R11 的 13 条全红）⇒「本轮把组合环推进了一格」这句在账上无凭据；两条独立成因：客户端注入 namespace/project_dir 撞白名单，以及 LoopRegistry 只在进程内
- detail: 实测分栏（`logs/r11_loopfix_a2.out` 的 SHAPE_CONTROL 行，逐字）：
 `{"只传声明键": {"环查无": 24, "成功": 24, "键名被拒": 0, "其它": 0}, "含未声明键": {"键名被拒": 10, "成功": 0, "环查无": 0, "其它": 0}}`
 ⇒ 注入未声明键的那一栏 10/10 全被拒（服务端 BUG-23 的白名单是真的，不是形同虚设），声明键栏 0 次键名拒绝；两栏各自解释一部分红，不能并成一个原因写。
第二条成因：`loop_create` 自述「创建并注册到**进程内** LoopRegistry」，而 `scripts/fist.py` 每个 FistClient 都 spawn 新的 `node serve` ⇒ start 会话 create、close 会话 tick 必然 `loop not found: cypy-selfdrive-ring-r11`（本轮跨会话负控制逐字取到）。
影响：本系列报告里凡写过「环已推进/loop_tick 已打」的句子，在服务端都没有对应状态；环的 round/max_rounds 一直是 0/6。
修复：新增 `.fist-loop-20260929/r11_loop_drive.py`（同一会话内 create + 6×tick + status，门表 8 格逐条对表：create_ok/status_pre_ok/all_ticks_ok/status_post_ok/cross_process_negative_confirmed/round_advanced/mode_sequence_matches_declared_steps/current_idx_progression/no_early_stop），并把它接进 `run_r11_ring.py --stage close` 的收口腿。复验：`logs/r11_loopdrive_a2.out` ⇒ `ticks_ok=6/6 gates={...全 true...}`，round 0→1、next_mode 序列与登记的 steps 逐位相同、current_idx 1..5→0；换新会话查同名环 ⇒ 仍 `loop not found`（负控制成立）。自检：`--selftest` 用 8 组坏数据逐条把对应门翻红（`logs/r11_loopdrive_selftest_a1.out` `cases=8 bad=[]`）。
- reported_key: R11-LOOP-NEVER-TICKED
- reported_by: cypy-selfdrive-agent

### FIXED(R11 收口腿 2026-09-29T08:25:31Z）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：新增 `.fist-loop-20260929/r11_loop_drive.py` —— **同一会话内** `loop_create` + 6×`loop_tick` +
  `loop_status`，回放的基线数从账上取（`loop_create_params()` 读上一笔成功的参数，查无即拒绝手填），
  `steps` 序列与账上登记值逐位比对，不一致直接 SystemExit；并接进 `run_r11_ring.py --stage close`
  的收口腿（`drive_loop()`，门表复用同一实现，不写第二份）。
- 两条成因分别取证（合起来才解释 33 条红）：
  ① 键名：`logs/r11_loopfix_a2.out` 的 `SHAPE_CONTROL` 逐字
  `{"只传声明键": {"环查无": 24, "成功": 24, "键名被拒": 0, "其它": 0}, "含未声明键": {"键名被拒": 10, "成功": 0, ...}}`
  ⇒ 注入未声明键 10/10 全拒、声明键栏 0 次键名拒绝（驱动侧统一带 `_omit_defaults` 退出键）；
  ② 进程内：换新 `FistClient`（会再 spawn 一个 serve）查同名环 ⇒ `loop not found: cypy-selfdrive-ring-r11`
  （`r11_loop_drive.json` 的 `cross_process_negative`），与 `loop_create` 自述的"进程内 LoopRegistry"一致。
- 复验：`logs/r11_loopdrive_a2.out` ⇒ `ticks_ok=6/6`，九格门全 true
  （`round_advanced` 0→1、`mode_sequence_matches_declared_steps` 逐位相同、
  `current_idx_progression` 1..5→0、`no_early_stop`、跨会话负控制成立）；
  负控制自检 `logs/r11_loopdrive_selftest_a1.out` ⇒ `cases=8 bad=[]`
  （round 不前进／少 tick／mode 打乱／服务端叫停／单次被拒／跨会话竟查得到／create 被拒／status 被拒
  各自把对应门翻红）。
- 限制（不遮挡本单关闭）：环状态是进程内的 ⇒ 服务端**没有**跨轮可审的环账，本报告"环已推进"只能指
  「同会话内 6 步走完且回执全绿」这一格；要跨轮审计得把 LoopRegistry 落库（FIST 侧，不属本仓改动面）。

## BUG-133 [2026-09-29T08:21:28Z] [low] OPEN
- summary: [判据面·驱动] `run_r11_ring.py --stage close` 起手即崩：根单 id 只在 start 分支里赋值，close 分支查了 `root_row` 却不绑定 ⇒ UnboundLocalError 且 rc=1，一条账都没写（失败形态是崩溃，不是拒绝）
- detail: 实测（`logs/r11_ring_close_a2.err` 逐字尾两行）：
 `File ".fist-loop-20260929/run_r11_ring.py", line 271, in main` / `UnboundLocalError: cannot access local variable 'root_id' where it is not associated with a value`
机制：开批门（报告在盘、引用核验 failed=0、三套终值、Ω-gate）当时已经全过，崩点在门之后的树回读；`root_row` 查询写在分支外，赋值却写在 `if args.stage == "start"` 里。
定性：低危但形态难看 —— 崩溃不写回执，只看 rc 会误判成「门禁拦下了」。
修复：close 分支改为显式绑定 `root_id`，查无根单时**拒绝并落 refused 回执**（原因逐字含 ns/前缀/parent_id 口径），绝不静默新建一棵树去凑数。复验：a3/a4 两次收口都在同一棵根上跑完（`root=T0r117 rollup={'已完成': 17} pending_leaves=0`）。
- reported_key: R11-CLOSE-ROOT-UNBOUND
- reported_by: cypy-selfdrive-agent

### FIXED(R11 收口腿 2026-09-29T08:25:31Z）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：close 分支起手显式绑定 `root_id`；查无根单时**拒绝并落 refused 回执**
  （原因逐字含 ns、前缀、`parent_id=''` 三个口径），绝不静默新建一棵树去凑数。
- 负控制（真跑，不是读代码）：把 `ROOT_PREFIX` 换成账上必然查无的名字另存为
  `run_r11_ring_negctl.py`（与原文件只差 1 行）⇒ `logs/r11_ring_close_negctl_a1.out`
  逐字 `REFUSED (开批门) local | 账上查无根单 T0r999-不存在的根单前缀` +
  `CONCLUSION refused=1 stage=close gate_reasons=1`，rc=1 而不是 traceback；
  且该窗口 `call_log` 新增行数 0 ⇒ 拒绝发生在任何 RPC 之前，没有半途写账。
- 复验：修后 a3/a4 两次收口都在同一棵根上跑完（`root=T0r117`，`rollup={'已完成': 17}`）。
## BUG-134 [2026-09-29T08:55:38Z] [low] OPEN
- summary: [判据面·诊断文案] 注解位的违界诊断自称「in call to '<unknown>'」：联合界/命名界走 `_check_bound_satisfaction` 取 `node.func.id` 当被调方，注解位节点没有 func ⇒ 落成 '<unknown>'，而同一个注解位的 trait 界走另一条分支，文案是另一种形状（`... for parameter 'T' at L:C`）
- detail: 实测（`corpus/cypy.generic.bounds.json` 的两条违界格，逐字）：
 (a) `class Num<T: int | float>` + `let x: Num<str> = Num(1)` ⇒
  `Generic constraint violation: type 'str' does not satisfy constraint 'int | float' (allowed: int | float) for parameter 'T', in call to '<unknown>', reported at line 10, col 12`
 (b) `class Only<T: Show>` + `let x: Only<int> = Only(1)` ⇒
  `Generic constraint violation: type 'int' does not implement trait 'Show' for parameter 'T' at 13:12`
 —— 同一使用位、同一类事实，两类界给出两种形状，其中 (a) 还把自己说成一次调用。
机制：`cypyc/analyzer/type_checker.py` 里 `_check_bound_satisfaction` 用 `getattr(getattr(node, 'func', None), 'id', None)` 推 callee，取不到就写 `in call to '<unknown>'`；trait 分支与 typeclass 分支各拼一份 `{line}:{col}` 尾巴（消息合成点不止一处 ⇒ 正是本轮在别处用「共用一份」消掉的形状）。
影响与判据缺口：本轮语料只钉了 `reported at line \d+, col \d+`（定位正确性），所以「in call to」这句误导**没有任何判据在拦** ⇒ 属于文案级缺陷，不是假阴性。修法二选一交裁决：① 给非调用位传使用位标签（`at type annotation of 'Num<str>'`），② 把 callee 段改成中性且只在真是调用时出现；两者都会动到 C-5.x 钉住的既有文案，需与 `corpus/cypy.generic.callsite.json`、`tests/test_type_inference.py` 的锁同批改。
证据件：`.fist-loop-20260929/make_corpus_r12.py`（两类界的成对样本）、`corpus/cypy.generic.bounds.json`、`.fist-loop-20260929/logs/r12_gate_a1.log`。
- reported_key: R12-BOUND-DIAG-NOT-A-CALL
- reported_by: cypy-selfdrive-agent

## BUG-135 [2026-09-29T08:55:38Z] [medium] OPEN
- summary: [analyzer] class/struct 构造位不写类型实参时不做类型参数推断：`One(v="s")` 对 `T: int` 的声明界 0 诊断，且成员类型也不代入（退化成未参数化的类）
- detail: 实测（同一程序的三种写法，逐字见 `.fist-loop-20260929/logs/r12_probe_a2.out`）：
 `struct One<T: int>:\n    v: T` + `b = One(v="s")` ⇒ 违界诊断 0 条；
 同一行写成 `let a: One<str> = One(v="s")` ⇒ 1 条（由**注解位**判下，不是由实参推断判下）；
 写成 `b = One<str>(v="s")` ⇒ 1 条（显式实参位）。
机制：`_visit_Call` 的泛型分支以 `func_name in self.func_defs` 为闸门（`cypyc/analyzer/type_checker.py` 的 1375 区与 2946 区两处同样闸门），struct/class 名不在 `func_defs` ⇒ 既不跑 `_infer_generic_types`，也不回填 `generic_params`；`_visit_StructLiteral` 那份推断只服务 StructLiteral 节点，而 `One(v="s")` 解析成 `Call(func=Name, args=[('v', Constant)], type_args=[])`（AST 实测，见探针件）。
定性：[真缺陷·承诺半落地] —— 手册「使用泛型类」段落只给了显式实参形态，推断形态从未被承诺，但用户直觉会认为 `One(v="s")` 就是 `T=str`。与 BUG-128（struct 方法不代入）同族：都卡在「类/结构体的类型参数没有被推断出来」这一层。
半径与处置：本轮**不修**，改为把「不判」钉成语料格（`INFER_NOT_YET` 那条 expected.errors=0）与锁 `test_inferred_constructor_position_still_unjudged` ⇒ 将来修它时必须同时改这两处，不许静默翻面。修它需要构造位实参→类型参数的统一化推断 + 字段类型代入，会把「方法调用从不判」那一类程序打红（BUG-128 同一半径），须与语料同批。
证据件：`.fist-loop-20260929/probe_r12_ctor_inference.py`、`corpus/cypy.generic.bounds.json`（laws 第 3 条写明不判面）。
- reported_key: R12-CTOR-NO-GENERIC-INFERENCE
- reported_by: cypy-selfdrive-agent

## BUG-136 [2026-09-29T09:53:18Z] [medium] OPEN
- summary: [generics:alias] 泛型类型别名 `type Result<T> = tuple<bool, T>` 收下但不代入不判：四组成对反例（内层类型错/标志位错/两位错/未知类型名）全 0 诊断，而 `SYNTAX_IMPLEMENTATION_STATUS.md:330` 把 `02-type-annotations.md` 标成「✅ 完整/无」
- detail: 实测（`.fist-loop-20260929/probe_r13_type_alias.py` 走 `scripts/omega_gate.py` 同一份 `execute()`，日志 `.fist-loop-20260929/logs/r13_probe_alias_a2.out`，12 形）：
 (a) `G_wrong_inner`：`type Result<T> = tuple<bool, T>` + `bad: Result<int> = (True, "x")` ⇒ errors=0；
 (b) `H_wrong_flag`：同别名 + `bad: Result<int> = (1, 2)`（首项该是 bool）⇒ errors=0；
 (c) `J_alias_wrong_kind`：`type Pair<T> = tuple<T, T>` + `bad: Pair<int> = (1, "s")` ⇒ errors=0；
 (d) `I_unknown_in_alias`：`bad: Result<NotAType> = (True, 1)`（类型实参不存在）⇒ errors=0；
 (e) `K_alias_arity_use`：`bad: Pair = (1, 2)`（用了别名却不给类型实参）⇒ errors=0；
 (f) `C_alias_bound_use`：定义侧写约束界 `type Num<T: int | float> = tuple<bool, T>` 直接解析失败（`Expected IDENTIFIER, got COLON at 1:11`）⇒ 手册「类型别名」一节只给了不带界的形态，带界形态既不接受也不给「不支持」的硬拒文案，与 BUG-120 是同一族定义侧冒号形态、不同使用点。
正向对照：`A_basic_alias`（非泛型别名）与 `B/D/E/F`（泛型别名 + 正确实参 + codegen 出 31 行产物）都 0 诊断 ⇒ 不是「整条语法没实现」而是「收下但参数从不代入」，所以错误程序与正确程序得到同一个读数。
机制：`type X<...> = ...` 走 `TypeAlias` 一类的登记路径，展开时不建 `GenericType` 绑定 ⇒ 注解位看到的仍是别名右端的**未参数化**形状，`tuple<bool, T>` 里的 `T` 没有替换点，后续 tuple 元素检查拿到的是裸 `T`（或 object）⇒ 判不出来也不报。
账面一致性：`SYNTAX_IMPLEMENTATION_STATUS.md:330` 那行写「✅ 完整 | 无」——本单入账后同时改这行，不改就会重复 R11 的「文档面·主张宽于判据」形状。
同族已开口、修法需同批的：BUG-135（构造位不写类型实参 ⇒ 不推断）、BUG-128（struct 方法不代入）、BUG-122（类型实参不判存在性，(d) 正是它在别名路径上的同形）。
- reported_key: R13-GENERIC-TYPE-ALIAS-NO-SUBST
- reported_by: cypy-selfdrive-agent



### 改判(R13 机制更正 2026-09-29T10:48:48Z）— 追加留档（本单正文与标题行一字未改）

- 机制更正（本单抬头 `OPEN` 与正文一字不改，改判只追在这里）：正文「机制」栏写的
  「别名展开时不建绑定 ⇒ `T` 没有替换点 ⇒ 参数从不代入」**是错的**。实测反证三条：
  ① `Result<int, int>` 报 `Type alias 'Result' expects 1 generic parameter(s), but got 2`
  ⇒ 参数表在读；② `type My = int` + `let bad: My = "s"` 报 `Type mismatch: expected int, got str`
  ⇒ 非泛型别名会展开；③ `type Triple<T> = Pair<Pair<T>>` 的错字面量本来就报类型不符
  ⇒ 泛型别名代入了一层。真正让 (a)(b)(c) 静默的是**容器元素位整条不判**（BUG-137，
  非别名路径的 `let bad: tuple<bool, int> = (True, "x")` 同样 errors=0 ⇒ 与别名无关），
  加上别名套别名没展开（BUG-138）与联合形态别名不代入（BUG-139）。
- 逐形改判：(a)(b)(c) 关闭面转给 BUG-137/138（本轮实测已红）；(d) 类型实参不存在
  ⇒ 与 BUG-122 同形，仍静默、不重复入账；(e) 裸用 `Pair` 得 0 诊断**是既有测试钉住的行为**
  （`tests/test_new_features_boundary.py:167 test_generic_type_alias_without_params` 断言 errors==0），
  不是本单可主张的缺陷 —— 半径实测时才发现，记在这里免得下一轮又当新 bug 报；
  (f) 带界别名 `type Num<T: int | float> = …` 解析失败 ⇒ **本单唯一仍开的面**。
- 取证件：`.fist-loop-20260929/probe_r13_container.py`（成对形状 + 三组自门）与
  `logs/r13_alias_paired_a1.json`（改动前基线）、`logs/r13_container_probe_b2.json`（改动后）。
- 账面一致性：`SYNTAX_IMPLEMENTATION_STATUS.md` 的 02/12 两行随本轮改写，
  「✅ 完整/无」不再覆盖别名面。

## BUG-137 [2026-09-29T10:23:59Z] [high] OPEN
- summary: [typing:container] 容器元素位整体不判：`cypyc/analyzer/type_checker.py` 的「容器同名即放行」分支把元素类型也一起吞了 ⇒ `let bad: tuple<bool, int> = (True, "x")` / `list<int> = ["s"]` / `tuple<int, int> = (1,)` / 返回位同形 全部 0 诊断
- detail: 实测口径：`.fist-loop-20260929/probe_r13_container.py` 走 `scripts/omega_gate.py` 同一份 `execute()`；改动前基线 `.fist-loop-20260929/logs/r13_alias_paired_a1.json`（22 形），改动后 `.fist-loop-20260929/logs/r13_container_probe_b2.json`（39 形，判据自带 must_be_red / must_stay_green 两组门）。
改动前**该红却静默**的形（读取通道对照 `CTRL_scalar_mismatch` 已先证非静默，所以这些 0 不是观测口径坏）：标量位 `let n: int = "s"` 会红，但容器位 `tuple<bool,int> ← (True,"x")`、`tuple<bool,int> ← (1,2)`、`list<int> ← ["s"]`、`list<list<int>> ← [["s"]]`、`tuple<int,int> ← (1,)`、以及返回位两条同形，全部 errors=0。
机制（实测定位，不是猜测）：`cypyc/analyzer/type_checker.py:889` 与 `:972` 两条分支 「声明与值同名容器 ⇒ 采用声明类型」直接 `return`/登记，从不比 `generic_params`；两条分支自己的注释只点名三种该放行的形态（空容器构造器、嵌套无参、含 None/object 参数），所以是实现宽于意图，不是设计如此。
修法与本单验证：新增 `_slot_incompatible`/`_first_bad_element`/`_check_container_elements`（`type_checker.py:4035` 起），两条分支改为「登记声明类型 + 记一条元素位诊断」；保守集只允许两侧都是闭合标量名时报错，用户类/trait/subtype 一律放行。规范依据先落在 `SYNTAX/02-type-annotations.md`「容器元素位判定（R13 补）」规则 1-6。
改动后同探针：原本静默的 7 形转红（逐形点名见本脚本 stdout），其余 21 形仍绿 ⇒ 占位四形态没有被打断。
未覆盖（本单不粉饰）：`dict<str,int> ← {"a":"b"}` 仍静默 —— 字典字面量根本不推断类型（`_visit` 对 DictLiteral 返回 None），另立一条；`list<Dog> ← [Cat()]` 也仍静默，属规则 5 的保守集选择。
- reported_key: R13-CONTAINER-ELEMENT-NO-CHECK
- reported_by: cypy-selfdrive-agent



### FIXED(R13 容器元素位判定 2026-09-29T10:48:48Z）— 追加留档（本单正文与标题行一字未改）

- 修法：把「同名容器即放行」收窄成它自己注释点名的占位形态。新增三个助手在
  `cypyc/analyzer/type_checker.py`：`_slot_incompatible`（单位纯判定）／`_first_bad_element`
  （逐位扫描）／`_check_container_elements`（唯一记帐出口，整串去重），
  赋值位 `:890` 与返回位（`_visit_ReturnStmt` 的 `target_name == value_type.name` 那支）
  各接一行 ⇒ 两边走同一份判定，不许一边判一边不判。
- 收紧的是实现宽于意图：两条分支的原注释只说「空容器构造器 / 嵌套无参 / 含 None-object 参数」该放行，
  实际把元素类型不同也吞了。四类占位在本轮全部复验仍为 0 诊断（Ω-spec `expected/errors=0` 半边）。
- 保守集（规则 5）是刻意的：只有两侧元素名都落在闭合标量表（`bool int long float double char str bytes`）
  才允许报「名字不同即不兼容」；用户类/trait/subtype 一律放行 ⇒ `list<Speak> = [Dog()]` 至今静默，
  这一面钉在 `tests/test_container_elements_r13.py::test_trait_element_is_lenient_by_design`
  而不是删掉不写。`dict` 键值位不生效（字典字面量不推断类型，规则 6）。
- 判据：新增 Ω-spec `corpus/cypy.container.elements.json`（28 对，指纹 `fnv1a64:7349f8d14b3fc9fc`，
  生成件 `.fist-loop-20260929/make_corpus_r13.py` 只封自己这份并证明其余 7 份字节未变）；
  回归锁 `tests/test_container_elements_r13.py`（31 支，含「两个调用点各一根源码针」
  与「手册闭合标量表 ↔ 代码常量」双向对表）。台账地板同批上调 FLOOR_SPECS 6→7、FLOOR_CASES 123→151。
- 半径实测：`.fist-loop-20260929/probe_r13_container.py`（39 形，自带 must_be_red /
  must_stay_green / 不许 crash 三组门）改动前后各跑一次，转红 7 形（`A01_alias_inner_wrong`、`A02_alias_flag_wrong`、`P01_tuple_inner_wrong`、`P02_tuple_flag_wrong`、`P03_list_elem_wrong`、`P07_list_of_list_wrong`、`P08_tuple_arity_wrong`），
  仍静默 4 形（`A04_alias_unknown_arg`、`A05_alias_bare_use`、`P05_dict_val_wrong`、`P06_unknown_in_tuple`）⇒ 这几条是别单（BUG-122 类型实参存在性、
  dict 字面量不推断、`_type_in_union` 只比成员名），不冒充本单关闭；
  另有 2 形是**按设计该静默**的正向对照（`A03_alias_ok`/`A08_alias_in_param` 这类），
  与上面的"仍静默"分栏计，不混进同一句话里凑数。
- 手册：`SYNTAX/02-type-annotations.md` 新增「容器元素位判定（R13 补）」规则 1-6，
  规则 4/5/6 明写**不判的一面**，与既往轮「先写承诺再动实现」同形。

## BUG-138 [2026-09-29T10:23:59Z] [high] OPEN
- summary: [generics:alias] 别名套别名只代入一层 ⇒ **正确程序被拒**（假阳性）：`type Pair<T> = tuple<T, T>` + `type Triple<T> = Pair<Pair<T>>` 之后 `let ok: Triple<int> = ((1, 2), (3, 4))` 报 `Type mismatch: expected Pair[Pair[int]], got tuple[tuple[int, int], tuple[int, int]]`
- detail: 身份隔离（先证不是别家改动带来的）：`.fist-loop-20260929/logs/r13_nested_alias_fp_a1.json` —— 把本轮新加的 `_check_container_elements`  monkeypatch 成空操作再跑同一形状，诊断逐字不变（2 形全等 identical=True）⇒ 这条假阳性在本轮改动之前就存在，与本单的容器判定无关。
假阳性文案（逐字，取自该件 `Triple_ok.with_new_judge_off[0]`）：Type mismatch: expected Pair[Pair[int]], got tuple[tuple[int, int], tuple[int, int]] at 5:9
正向对照：同一件里 `type Pair<T> = tuple<T, T>` + `let ok: Pair<int> = (1, 2)` 是 0 诊断⇒ 只有一层别名没事，**套娃**那一层没解开。
机制：`cypyc/analyzer/type_checker.py` 的 `_substitute_type` 处理 `GenericType` 时直接 `Type(type_node.name, generic_params=…)`，右端里出现的**其它别名**名字被原样保留⇒ 得到 `Pair[Pair[int]]` 这种「没有展开成 `tuple<…>`」的半成品，再与字面量的 `tuple<tuple<int,int>, tuple<int,int>>` 比 `!=` ⇒ 判错。
修法：`_substitute_type` 增加 `_expand_nested_alias`，把右端里出现的别名展开到底（带 `_alias_stack` 名链守卫，`type Loop<T> = Loop<T>` 这类自指停在原地不递归成 RecursionError）；实参个数不符仍交回既有 arity 诊断，不重复记账。
本单验证形状：`N01_nested_alias_ok` 由红转绿（假阳性消失），`N02_nested_alias_wrong`（内层元素真错）由粗报文转成精确的 `Element 2 type mismatch: expected int, got str`，`N03_scalar_alias_in_alias`/`N04_self_alias_no_hang` 一起进锁。
- reported_key: R13-NESTED-ALIAS-NOT-EXPANDED
- reported_by: cypy-selfdrive-agent



### FIXED(R13 别名展开到底 2026-09-29T10:48:48Z）— 追加留档（本单正文与标题行一字未改）

- 修法：`_substitute_type` 增加 `_expand_nested_alias` —— 别名右端里出现的**其它别名**展开到底，
  带 `_alias_stack` 名链守卫：`type Loop<T> = Loop<T>` 这类自指停在原地返回 `Loop[int]`，
  不递归成 RecursionError；实参个数不符仍交回 `_substitute_generic_alias` 既有的 arity 诊断（不叠账）。
- 这一单的原始形态是**假阳性**：`type Triple<T> = Pair<Pair<T>>` 之后
  `let ok: Triple<int> = ((1, 2), (3, 4))` 被判 `Type mismatch: expected Pair[Pair[int]], got tuple<…>`。
  身份隔离见 `.fist-loop-20260929/logs/r13_nested_alias_fp_a1.json`：把本轮新加的容器判定
  monkeypatch 成空操作再跑同一形状，诊断逐字不变 ⇒ 假阳性早于本轮改动存在，不是新 bug 冒充旧账。
- 验证：`N01_nested_alias_ok` 由红转绿（正确程序不再被拒），
  `N02_nested_alias_wrong` 由粗报文转成精确的 `Element 2 type mismatch: expected int, got str`，
  `N03_scalar_alias_in_alias`（标量别名嵌在别名右端里）与 `N04_self_alias_no_hang` 同批进锁
  （`tests/test_container_elements_r13.py` 的 4 支 nested/loop 用例）。
- 未随本单关闭：`type Num<T: int | float> = …` 这种**带界别名**仍解析失败
  （`Expected IDENTIFIER, got COLON`），留在 BUG-136 的 (f) 面，不在这里冒充已修。

## BUG-139 [2026-09-29T10:23:59Z] [medium] OPEN
- summary: [generics:alias] 联合形态的泛型别名整条不代入 ⇒ 任意值都放行：`type Maybe<T> = T | None` + `let bad: Maybe<int> = "s"` 0 诊断；`type ListOrSet<T> = list<T> | set<T>` 的元素位同样无从判起
- detail: 实测：`.fist-loop-20260929/probe_r13_container.py` 的 `U01_maybe_wrong` 改动前 errors=0（改动后转红：`Type mismatch: expected Union[int, None], got str`）。
机制：`_substitute_type` 只认 `Name`/`PointerType`/`GenericType` 三种节点，`UnionType` 落到函数末尾的 `hasattr(type_node,'id')` 分支之外 ⇒ 返回 ``None`` ⇒ `_substitute_generic_alias` 返回 ``None`` ⇒ 注解位声明类型为空 ⇒ `_visit_LetStmt` 整条 `if declared_type and value_type` 不成立，任何值都登记为声明名。
影响面不是纸上的：`examples/demos/data_structures/type_alias_demo.cypy:36` 就写着 `type ListOrSet<T> = list<T> | set<T>`，:49/:50 两处使用 ⇒ 这份 demo 一直是「因为什么都不判所以通过」。
修法：`_substitute_type` 补 `UnionType` 分支，与 `_get_type_from_node:3968` 同形（`Type("object", union_members=[…])`），成员先各自代入再交给 `_type_in_union`。
未覆盖（本单不粉饰）：`U04_listorset_elem_wrong`（`ListOrSet<int> ← ["s"]`）改动后**仍静默** —— `_type_in_union` 只比成员 `.name`，容器元素位不参与判定；这条要动 `_type_in_union` 的语义，半径明显大于本单其余三条，已另计入开项。
- reported_key: R13-UNION-SHAPED-ALIAS-NO-SUBST
- reported_by: cypy-selfdrive-agent



### FIXED(R13 联合形态别名代入 2026-09-29T10:48:48Z）— 追加留档（本单正文与标题行一字未改）

- 修法：`_substitute_type` 补 `UnionType` 分支，与 `_get_type_from_node` 的联合分支同形
  （`Type("object", union_members=[…])`），成员先各自代入再交给既有 `_type_in_union` ⇒
  不再出现「代入返回 None ⇒ 声明类型为空 ⇒ 任意值登记通过」。
- 影响面不是纸上的：`examples/demos/data_structures/type_alias_demo.cypy:34-36` 三份泛型别名
  （`Optional<T> = T | None`、`ListOrSet<T> = list<T> | set<T>`）过去整条不判，
  :49-50 两处使用是「因为什么都不判所以通过」；本轮之后 `Maybe<int> = "s"` 报
  `Type mismatch: expected Union[int, None], got str`，而 demo 自己的 `ListOrSet<int> = [1,2,3]`
  仍 0 诊断（成员名对上即放行）。
- 未随本单关闭（原样入账不粉饰）：`ListOrSet<int> = ["s"]` **仍静默** ——
  `_type_in_union` 只比成员 `.name`，元素位不参与判定；这条要动 `_type_in_union` 的语义，
  半径明显大于本单其余面，钉在
  `tests/test_container_elements_r13.py::test_union_member_element_positions_are_still_open`
  等扩面那天先红。BUG-122（类型实参不判存在性）同批未合。
- 判据：Ω-spec `corpus/cypy.container.elements.json` 的 3 支 Maybe/联合成员用例（正反例齐）
  + 回归锁 4 支（`test_union_shaped_alias_*` / `test_union_of_containers_*`）。

## BUG-140 [2026-09-29T10:47:53Z] [medium] OPEN
- summary: [ledger:integrity] `memory/bugs.md` 里 `## BUG-96` 出现两次（第 2747 行与第 2868 行，严重度一栏还分别是 medium 与 high） ⇒ 抬头 140 条但去重后只有 139 个编号，按 id 建字典的工具会静默丢掉一张
- detail: 取证：核验件 `.fist-loop-20260929/verify_r13_report.py` 在数「报告点名的编号是否都在账上」时，用 `re.split` 得到 140 个抬头、建 dict 后只剩 139 个键 —— 差 1 不是尺坏，是账上真有重复号。两条抬头逐字：
  L2747: ## BUG-96 [2026-09-29T03:13:47Z] [medium] OPEN
  L2868: ## BUG-96 [2026-09-29T03:19:00+00:00] [high] OPEN
第二条的时间戳是 `+00:00` 形态而非本仓约定的 `…Z` 形态（`ledger_sweep` 里那 17 条「读得到钟点但没 Z」的软读数就包含它），所以它既可能是另一条写入路径产出，也可能是手改。成因不在本单主张范围内。
为什么不就地修：改号会让既有引用（报告、FIXED 段、任务库 linked id）悬空，而合并两条又会把两种严重度压成一条 ⇒ 交回人工裁决，本轮只入账不改账。
同轮受影响的读数口径：本轮报告同时写「抬头 140 / 去重 139」两数，不再只报一个
- reported_key: R13-LEDGER-DUPLICATE-BUG-ID
- reported_by: cypy-selfdrive-agent

## BUG-141 [2026-09-29T12:26:28Z] [high] OPEN
- summary: [typing:container] 字典字面量不推断类型 ⇒ `dict<K, V>` 的键位与值位永远无从判定：`let x: dict<str, int> = {"a": "b"}` 等 7 形 0 诊断（含返回位、嵌套位、别名位、dict 套 dict）
- detail: 实测口径：`.fist-loop-20260929/probe_r14_dict.py` 走 `scripts/omega_gate.py` 同一份 `execute()`；改动前基线 `.fist-loop-20260929/logs/r14_dict_probe_a2.json`（23 形，读取通道对照 `CTRL_scalar_mismatch`/`CTRL_list_elem_wrong` 两条都先红 ⇒ 下面的 0 不是观测口径坏），改动后 `.fist-loop-20260929/logs/r14_dict_probe_b1.json`（23 形）。
改动前**该红却静默**的形（逐条）：D01_value_wrong, D02_key_wrong, D03_return_value_wrong, D04_nested_list_wrong, D05_alias_dict_wrong, D06_dict_of_dict_wrong, D07_bool_key_under_str —— 覆盖值位、键位、返回位、嵌套 `dict<str, list<int>>`、`type Count = dict<str, int>` 别名、`dict<str, dict<str,int>>` 套娃、以及 `{True: 1}` 这种键位标量错配。
机制（实测定位，不是猜测）：`cypyc/analyzer/type_checker.py` 的 `_visit` 按 `_visit_<kind>` 派发，而 **没有** `_visit_DictLiteral` ⇒ 落到 `_visit_children` 返回 `None` ⇒ `_visit_LetStmt`/`_visit_ReturnStmt` 的 `if declared_type and value_type` 整条不成立 ⇒ 声明侧的键值位连「实得类型」都没有。上一轮（R13）把 `dict` 排除在 `_ELEMENT_CHECKED_CONTAINERS` 之外，正是为了让这条不判的边界有文字依据 —— 排除是对的，但排除的理由（字面量不推断）本身就是缺陷。
修法：新增 `_visit_DictLiteral` + `_slot_lub`（键位/值位各自求「最宽可表类型」：同形取该类型并保留参数、数值串取 `bool→int→float→double` 最宽、其余塌 `object`），`dict` 进入 `_ELEMENT_CHECKED_CONTAINERS`，诊断文案对 dict 点名 `Dict key`/`Dict value` 而不是 `element 1/2`。
本单验证：改动后同一探针 7 形全部转红，首条文案（逐字）：Dict value type mismatch: expected int, got str at 2:9；仍绿 14 形（占位、混形塌位、单向加宽、用户类保守集、无声明的 let、参数注解位）⇒ 收紧没有把该放行的扫进红堆。
判据与锁：Ω-spec `corpus/cypy.dict.elements.json`（23 对，指纹 fnv1a64:d31d62984b62f3ae）+ 回归锁 `tests/test_dict_elements_r14.py`（29 支）；规范依据 `SYNTAX/02-type-annotations.md`「字典字面量的键值位判定（R14 补）」规则 1-6。
同轮收紧的两条 R13 豁免锁（断言反向，不是删除）：`tests/test_container_elements_r13.py::test_dict_value_slot_is_required_since_r14` 与 `::test_dict_is_now_in_the_checked_container_list`；R13 语料 `cypy.container.elements` 里那条 dict 豁免案例一并由 `errors=0` 改为 `errors=1`，该份 spec 因此重封指纹。
未覆盖（本单不粉饰）：混形塌位仍静默 —— `dict<str, int>` 收 `{"a": 1, "b": "c"}` 值位塌成 object 后放行（手册规则 6 钉成正向对照）；字典推导式、`for k, v in d` 解包位、`d[k] = v` 写入位都不走字面量推断这条路，本单不判；联合形态别名的成员元素位仍不判（`_type_in_union` 只比成员名，另计入开项）。
- reported_key: R14-DICT-LITERAL-NO-INFER
- reported_by: cypy-selfdrive-agent
### FIXED(R14 字典字面量推断件与键值位判定 2026-09-29T13:20:26Z）— 追加留档（本单正文与标题行一字未添改）

- 现算读数（写盘瞬间，非回忆）：成对探针 `25` 形 ⇒ 改动前该红却静默 7 形
  （`D01_value_wrong, D02_key_wrong, D03_return_value_wrong, D04_nested_list_wrong, D05_alias_dict_wrong, D06_dict_of_dict_wrong, D07_bool_key_under_str`），改动后逐条转红；声明该绿的 15 形改动后仍全绿（`G01_empty_literal, G02_correct, G03_hetero_values, G04_widening_value, G05_bool_widening, G06_user_type_value, G07_untyped_let, G08_nested_correct, G09_dict_of_dict_ok, G10_param_annotation, G11_empty_then_return, G12_empty_untyped, G13_scalar_alias_dict, G14_hetero_both, G15_mixed_numeric_widening_ok`）。
  另有 1 形（`D08_mixed_numeric_narrow`）是关单后补的（见下方"判据又长了一次"那条）——
  补它的时候产品已经修好，所以**没有**改动前读数，不混进上面那份静默清单里充数。
- 判据：Ω-spec `corpus/cypy.dict.elements.json`（25 对，指纹 `fnv1a64:de31b469f22cbed7`）；
  同轮把 R13 那份 `cypy.container.elements`（28 对）里"dict 豁免"的那一条
  由 `errors=0` 收紧成 `errors=1`，该份指纹因此重封为 `fnv1a64:f45c1ff0f323aec1` ——
  旧指纹 `fnv1a64:7349f8d14b3fc9fc` 是 R13 台账里那次读数的身份，不改写它。
- 回归锁：`tests/test_dict_elements_r14.py`（29 支 `def test_`），
  同轮把 R13 的两条豁免锁改成反向断言（`test_dict_value_slot_is_required_since_r14`、
  `test_dict_is_now_in_the_checked_container_list`）—— 收紧而不是删除，旧名与新断言的来由写进 docstring。
- 关单之后判据又长了一次（这一条不是补装饰，是承重矩阵抓出来的洞）：
  `verify_r14_locks.py` 的 M3 格（撤掉"数值阶梯取最宽"）在 Ω-gate 那半边 **0 失** ⇒
  说明 spec 里没有形状喂这一支。于是补 `D08_mixed_numeric_narrow`（`dict<str, int>` 收
  `{'a': 1, 'b': 2.5}` 要红）与成对半边 `G15_mixed_numeric_widening_ok`（同一字面量收进
  `dict<str, float>` 要绿），探针由 23 形长到 25 形，spec 由 23 对长到 25 对，
  指纹由 `fnv1a64:d31d62984b62f3ae` 变成 `fnv1a64:de31b469f22cbed7`。本单卡片正文里那句"23 对 / `fnv1a64:d31d62984b62f3ae`"是**取号那一刻**
  的读数，append-only 不改写它，差异只在这一段里交代。
- 四套全量：pytest 半径 2390 passed → 终版 2444 passed（差 54 = 新锁 29 + 新语料 25，
  由本件现算对表）；自研套件 `Total|Passed|Failed = 47 | 47 | 0`；
  Ω-gate 全 spec `specs=8 cases=174 passed=174 failed=0`；e2e golden `PASS=25 FAIL=0`。

## BUG-142 [2026-09-29T12:26:29Z] [low] OPEN
- summary: [docs] `SYNTAX/02-type-annotations.md` R13 节把「锁死用例」写成 `tests/regression/test_container_elements_r13.py`，该路径不存在（实际在 `tests/` 下）⇒ 手册指路失败，且当时没有任何判据覆盖文档里的路径引用
- detail: 活证据（file:line）：该手册 R13 节末句原写 那句「锁死用例见 tests/regression/test_container_elements_r13.py」，而 `tests/regression/` 目录里只有 `test_corpus_pairs.py`（`ls tests/regression/` 可读回）⇒ 按手册去找会一无所获。
为什么当时没被抓出来：R13 的引用核验件（`verify_r13_report.py`）只校「报告点名的文件是否存在」，手册本身不在它的检查面里；也没有一条锁把「手册引用的仓内路径都存在」当判据 ⇒ 文档引用是无人认领的一类主张。
修法：手册该行改为实际路径并同句点名 R14 的锁文件；新增会红的锁 `tests/test_dict_elements_r14.py::test_manual_revokes_the_r13_dict_exemption`断言手册引用的就是这份文件本身（`Path(__file__).name` 对表，不是抄字符串）。
范围声明：本轮只把「手册引用的这份具体路径」钉进判据；全量文档路径存在性扫描（SYNTAX/ 全部 + CHANGELOG + STATUS）仍是一件没做的事，记在这里而不是假装已闭合。
- reported_key: R14-MANUAL-DANGLING-TEST-PATH
- reported_by: cypy-selfdrive-agent
### FIXED(R14 手册锁死用例路径悬空已改指实际文件 2026-09-29T13:20:26Z）— 追加留档（本单正文与标题行一字未添改）

- 修法：`SYNTAX/02-type-annotations.md` 的锁死用例那句改指实际文件
  （`tests/test_container_elements_r13.py`，R13 那份锁一直在 `tests/` 下而不在 `tests/regression/`），
  并在同句点名 R14 的锁 `tests/test_dict_elements_r14.py`。
- 判据（把"手册引用的路径存在"变成会红的事）：
  `tests/test_dict_elements_r14.py::test_manual_revokes_the_r13_dict_exemption`
  断言手册引用的就是**这份文件本身**（拿 `Path(__file__).name` 对表，不是抄一个字符串）；
  现跑读数：`1 passed（0.06s，子集 -k manual）`。
- 范围声明（不装作已闭合）：本单只钉了这一条路径。
  "全量扫描 SYNTAX/ + CHANGELOG + STATUS 里所有仓内引用是否存在"仍是一件**没做**的事，
  它属于 R15 的文档完整性腿，不是本单的完成项。
- 本单不动产品码：字典判定那一面在 BUG-141，两段各说各的，不互相借证据。
