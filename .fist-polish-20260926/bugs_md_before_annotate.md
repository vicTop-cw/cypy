## BUG-1 [2026-09-26T05:31:45Z] [high] OPEN
- summary: [cache] cypy_bridge/compiler.py:3656 clear_cache 把 .pyd 删除失败当成功：裸 except 吞掉后仍从 manifest 删条目
- detail: 现象：`clear_cache(module_name)` 在 `try: os.remove(pyd_path) except: pass`（:3656-3659）之后无条件 `del manifest[cache_key]` + `_save_manifest(manifest)`；全量分支（:3668-3671）同样吞掉删除失败并无条件 `_save_manifest({})`。
后果：Windows 上被 import 的扩展模块文件锁是常态（同文件 :3760 附近就有为绕开 file lock 而换临时目录的逻辑），删除失败时磁盘上的 .pyd 仍在，但 manifest 已声称没有 → 上层按 manifest 判断「已清理」，可继续命中陈旧二进制；表现为「清了缓存但行为没变」，且全程零诊断。
复现（确定性、不编译）：构造 BridgeCacheManager，写一条 manifest 指向临时 .pyd，monkeypatch `os.remove` 抛 OSError，再调 `clear_cache(name)`；断言「删除失败 ⇒ 条目仍在 manifest 或返回值/日志能观察到失败」。当前实现两条都不满足。
判据实测：`grep -n 'except:' cypy_bridge/compiler.py` → 3658、3670 两处（全仓三包裸 except 共 2 处、`except … : pass` 共 20 处，见 `.fist-polish-20260926/markers_baseline.json`）。
建议：删除失败就不动 manifest 条目（保持「未清理」的事实），并把失败收集成可判定结果（例如返回 (cleared, failed) 或记 warning），不要静默写空 manifest。
- reported_by: cypy-polisher
- task_id: T0r6

## BUG-2 [2026-09-26T05:31:45Z] [high] OPEN
- summary: [subprocess] cypy_bridge/compiler.py:3795 subprocess.run 无 timeout；同仓做同一件事的另外两处都有 timeout=120
- detail: 现象：桥接编译 `subprocess.run([sys.executable, setup_file, 'build_ext', '--inplace'], capture_output=True, cwd=tmp_dir)` 缺 `timeout`；对照 `cypyc/project/project_compiler.py:599-604`（`timeout=120`）与 `cypy_hook/hook.py:513-518`（`timeout=120`）。三包内 subprocess.run 共 3 处：2 处有超时、1 处没有。
后果：setuptools / Cython / 链接器任一环节挂死（文件锁、弹窗、交互式提示、杀软扫描）时调用线程永久阻塞——无退出码、无诊断，整条构建链卡死。另两处早已按 120 s 收口，说明这里缺失是不一致而非设计。
复现：`grep -n 'subprocess.run' cypyc/project/project_compiler.py cypy_bridge/compiler.py cypy_hook/hook.py` 三条对照，只有 bridge 那条不带 `timeout=`。
建议：补 `timeout=120`，并在 `subprocess.TimeoutExpired` 分支终止子进程、清理临时目录、产出可诊断错误（注意同文件的裸 except 家族会把这类失败一并吞掉）。
- reported_by: cypy-polisher
- task_id: T0r7

## BUG-3 [2026-09-26T05:31:45Z] [high] OPEN
- summary: [silent-fail] cypyc/project/project_compiler.py:826 增量重解析异常被吞：失败后仍用陈旧 AST 计算影响集并报告已传播
- detail: 现象：:817-831 里 `try: self._reparse_module(module_name) except Exception: pass`，紧接着无条件 `get_affected_modules({module_name})` 并写入 `affected[file_path]`。
后果：重解析失败（语法错误、编码问题、解析器缺陷）时依赖图里留的是旧 AST，但该文件被登记为「已处理且影响已传播」，增量构建据此产出陈旧结果并返回成功。这是增量编译最难定位的一类故障：改坏了不报错，产物是旧的。
复现（确定性）：monkeypatch `_reparse_module` 抛异常，调用受影响模块收集入口，断言「该文件不得出现在 affected 结果里，或 errors 列表必须记录该失败」；当前实现两条都不满足。
判据实测：`grep -n 'except Exception:' cypyc/project/project_compiler.py` → :826。
建议：失败即记入 errors 且把该文件从 affected 剔除——宁可让上层判定「增量失效、需全量重建」，也不要用陈旧 AST 谎报成功。
- reported_by: cypy-polisher
- task_id: T0r8

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

## BUG-5 [2026-09-26T05:31:45Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/hot_reload.py:110 与 :125 状态快照/回滚吞掉 getattr/setattr 异常（含用户 property 执行失败）
- detail: 现象：`_save_state` 在 `for name in dir(self._actual_module)` 里 `try: value = getattr(...) … except Exception: pass`（:99-111）；`_restore_state` 同样吞 setattr 失败（:120-126）。
后果：getattr 会执行模块级 property / 描述符 / 惰性导入。用户代码在这里抛错被当成「该属性不存在」跳过 ⇒ 快照不完整；热重载后只回滚了部分状态，模块停在新旧混合态，且零诊断。setattr 失败同理被吞。
判据实测：`grep -n 'except Exception:' cypyc/incremental/hot_reload.py` → :110、:125、:247、:272、:326、:451 共 6 处；本单聚焦 110/125 这一对，其余 4 处同文件同性质，修复时一并研判并逐条给结论。
建议：只捕明确不该致命的类型（AttributeError 等），把被跳过的属性名与异常记入调试日志；快照/回滚发生跳过时应让调用方可判定（例如返回跳过的名字列表）。
- reported_by: cypy-polisher
- task_id: T0r10

## BUG-6 [2026-09-26T05:31:46Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/file_monitor.py:58 读不到 .py 首行即判定「不是 Cypy 文件」，变更被静默漏掉
- detail: 现象：`_is_cypy_file` 对 .py 文件读首行判断 `#!bin cypy` 头，`except Exception: pass` 后 `return False`（:54-61）。
后果：文件此刻被占用 / 无权限 / 正在被写（监控器天然与写入方并发，同文件 :63 起就有 debounce 锁）时，读失败被当成「确定不是 Cypy 文件」→ 该文件的变更不触发重编译且无任何记录。这是把「检测失败」误当成「检测结论为否」的分类错误。
复现：monkeypatch `builtins.open` 抛 OSError，调用 `_is_cypy_file("x.py")`，断言结果不能是「静默 False 且无记录」。
判据实测：`grep -n 'except Exception:' cypyc/incremental/file_monitor.py` → :58。
建议：区分「读失败」与「读到但首行不匹配」：前者保留为待判定（延后重试或按候选处理）并落 warning，不能静默 return False。
- reported_by: cypy-polisher
- task_id: T0r11

## BUG-7 [2026-09-26T05:31:46Z] [low] OPEN
- summary: [diagnostics] cypy_hook/hook.py:926 与 cypy_bridge/compiler.py:3583 manifest 损坏与「文件不存在」不可区分，静默按无缓存继续
- detail: 现象：两处 `_load_manifest` 都是 `if os.path.exists(path): try: json.load(...) except (json.JSONDecodeError, IOError): pass` 然后 `return {}`。
后果：manifest JSON 被截断/写坏（并发写、磁盘满、进程被杀）与「首次运行没有 manifest」返回值完全相同 → 上层认为没有缓存，重建后直接覆盖，损坏证据永久消失，任何人都无法判断发生过什么。缓存子系统里这是最贵的一类静默降级。
判据实测：`grep -n 'except (json.JSONDecodeError, IOError)' cypy_hook/hook.py cypy_bridge/compiler.py` → 2 命中（hook.py:926、compiler.py:3583）。
建议：损坏时先把原文件改名留证（如 `bridge_manifest.json.corrupt-<ts>`）并落 warning，再按空 manifest 继续；返回值带 `was_corrupt` 之类的可判定信号。
- reported_by: cypy-polisher
- task_id: T0r12

## BUG-8 [2026-09-26T06:09:13Z] [medium] OPEN
- summary: [silent-fail] cypyc/parser/macro_expander.py:380 宏展开后的代码块解析失败时静默返回原块，整条宏语句从输出中消失且无任何告警
- detail: 现象: `_reparse_code()` 末尾 `try: Lexer/Parser ... except Exception as e:` 直接把未解析的原文包成 `BacktickBlock(code, '', line, col)` 返回，异常对象 `e` 被丢弃、无任何 stderr 输出。模块自己的实现约束注释（同文件 :20-23）就写着「这条降级路径会让整条宏调用语句从输出里消失」，即已知其危害，但用户/CI 看不到任何线索。
复现（确定性，零依赖）: `MacroExpander.__new__(MacroExpander)._reparse_code('def (', 7, 3)` → 返回 BacktickBlock 且 capsys 捕获的 stderr 为空串。见 `tests/test_polish_20260926.py::test_bug8_macro_reparse_degradation_is_reported`（修复前该条 1 failed / err == ''）。
影响: 宏实参渲染或插值产出的文本一旦不可解析，展开结果被原样透传给 codegen，该语句在生成的 .pyx 里消失——编译「成功」但少了一条语句，属静默数据丢失；与本轮 BUG-3/BUG-4/BUG-5/BUG-6/BUG-7 同族。
建议: 不改降级语义（仍返回 BacktickBlock，避免打破 23 条既有 macro 用例），只在 except 分支打一条点名 行/列/原始代码/底层异常的 stderr 告警；彻底修复（把失败上报到 diagnostics 并非零退出）属语义面变更，需单独立项。
- reported_by: cypy-polisher
- task_id: T0r13

## BUG-9 [2026-09-26T06:37:48Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/hot_reload.py:253 HotReloadEngine 的模块级状态快照/回滚仍是 `except Exception: pass`，BUG-5 的修复只覆盖了 CypyProxyModule 那一份平行实现
- detail: 现象: `_save_module_state()`(:248-254) 与 `_restore_module_state()`(:276-279) 对 getattr/setattr 失败一律 `pass`，而同文件同族缺陷 BUG-5 只改了代理模块路径的 `_save_state/_restore_state`（helper `_warn_state` 就在 :53）。
复现（确定性，零依赖）: `pytest tests/test_polish_20260926.py -q -k 'bug9_module or bug10'` → 4 failed，capsys 的 stderr 为空串；原始输出 .fist-polish-20260926/pytest_second_sweep_red.log。
影响: 热重载带着状态空洞继续跑——模块全局被静默丢弃或写不回去，用户只看到『重载成功』；与本轮 BUG-3/BUG-4/BUG-5/BUG-6/BUG-7/BUG-8 同族。
建议: 两处 except 复用已有的 `_warn_state()`，不改快照/回滚语义与返回值。
- reported_by: cypy-polisher
- task_id: T0r14

## BUG-10 [2026-09-26T06:37:48Z] [medium] OPEN
- summary: [silent-fail] cypyc/incremental/hot_reload.py:457 热重载把依赖分析与增量缓存更新的解析失败整段吞掉（:332 与 :457 两处，注释即『解析失败不影响热重载』）
- detail: 现象: `_analyze_module_dependencies()` 的函数体整块包在 try 里、`except Exception: pass`（:433-458），`_compile_and_reload_module()` 更新增量缓存的那段同样静默（:325-333）。解析或 analyze_changes 一旦抛错，模块级反向依赖图就缺边，后续热重载只重编触发文件本身、漏掉依赖方——漏重载比报错更难查。
复现（确定性，零依赖）: monkeypatch `cypyc.parser.parser.Parser` 抛错后调用两个入口，stderr 全空；见 .fist-polish-20260926/pytest_second_sweep_red.log 里 test_bug10_dependency_analysis_parse_failure_warns 与 test_bug10_cache_update_parse_failure_warns 两条 failed。
影响: 增量/热重载的正确性静默降级；BUG-3 修的是 project_compiler 那份重解析，hot_reload 这两份是同一缺陷类的未覆盖面。
建议: 两处各打一条点名 阶段/源文件/底层异常 的 stderr 告警，不改控制流（仍继续热重载），彻底上报到 diagnostics 属语义面变更需另立单。
- reported_by: cypy-polisher
- task_id: T0r15

## BUG-11 [2026-09-26T07:13:26Z] [medium] OPEN
- summary: [silent-fail] cypyc/project/project_compiler.py:539 项目模式 type_check_module 只上送 TypeChecker 诊断，ScopeAnalyzer 已报出的重名/类型级冲突（SYNTAX/33 C-3.1）被静默丢弃——同一份源码在单文件模式 cypy_hook/hook.py:250 会报错，两个入口给出相反裁决
- detail: 现象: type_check_module() 调用 ScopeAnalyzer().analyze(ast) 后从不读 scope_analyzer.errors（:539-540），只把 type_checker.errors 收进返回值；而单文件管线 cypy_hook/hook.py:250-257 两处都收。因此作用域通道独有的诊断（重名定义、类型级名字冲突、非模块级定义）在项目模式整个消失，cypyc/cli.py:737-744 的 --check-only 会打印 'type check passed' 并以 0 退出。
复现（确定性，零依赖）: 三份源文件各建一次性项目，python .fist-polish-20260926/probe_scope_drop.py 打印三行 DROPPED —— ScopeAnalyzer 有诊断、TypeChecker 为空、type_check_module 返回 ok=True errors=[]：dup_func（def f 写两次）、dup_subtype_class（subtype Money <: int 撞 class Money）、dup_type_constraint（type Thing = int 撞 constraint Thing）。对照：uses_undefined 一条不丢，因为 TypeChecker 自己会报同一句 Undefined name —— 丢的正是作用域独有的那一类。
锁死回归: tests/test_polish_20260926.py::test_bug11_project_type_check_reports_scope_errors + ::test_bug11_type_level_name_collision_is_reported；改前 .fist-polish-20260926/pytest_third_sweep_red.log → 2 failed, 20 deselected（两条都红在 ok=True errors=[]，且用例里的前提自证断言先确认 ScopeAnalyzer 确实报出了这个名字）。
影响: 项目/多模块构建带着重复定义继续编译，codegen 按后写覆盖前写产出 .pyd，用户拿到的模块身份与源码不一致；与本轮 BUG-3（同一文件的重解析异常被吞）同族。
建议: 在 type_check_module 里 errors.extend(scope_analyzer.errors)，并对两条通道逐字重复的诊断按序去重（dict.fromkeys），不改任何判定规则、不新增诊断文案。
- reported_by: cypy-polisher
- task_id: T0r16

## BUG-12 [2026-09-26T08:27:00Z] [medium] OPEN
- summary: [error-masking] cypy_bridge/nogil.py:73 GilState.__exit__ 无条件 acquire，with 体内提前归还 GIL 后再抛用户异常时，退出路径用 NoGilError('GIL is not released') 顶掉用户异常——同一族的嵌套覆盖问题本模块已在 NoGilContext 修过，GilState 这条退出路径漏修
- detail: 现象: GilState.__exit__（:73-76）直接 self.acquire()，而 acquire()（:58-59）在 _released 已为 False 时抛 NoGilError。因此 `with GilState() as st: st.acquire(); raise ValueError(...)` 这种「区域内提前归还 GIL」的合法写法，退出时 __exit__ 抛出的 NoGilError 会替换正在传播的 ValueError，用户既拿不到自己的异常类型，也看不到自己的消息；异常链里只留下 'GIL is not released'。
复现（确定性，零依赖）: python .fist-polish-20260926/repro_sweep4_nogil.py → `escaped exception type = NoGilError`、`[repro A] ... REPRODUCED`。同脚本的 B 项（nogil_thread 一次性调用是否泄漏执行器线程）实测没有复现——12 次调用只余 1 个临时 worker，会被回收，故 B 按误报不入账。
锁死回归: tests/test_polish_20260926.py::test_bug12_gilstate_exit_does_not_replace_user_exception（改前红：AssertionError: GIL 退出路径把用户的 ValueError 换成了 NoGilError）+ ::test_bug12_gilstate_exit_still_restores_state（防过度修复：退出时仍须把 released 复位，改前即绿，改后仍绿）。
影响: cypy_bridge 公开导出 GilState/release_gil/acquire_gil（__init__.py:119-121、224-226），任何用它包 CPU 密集段并在段内手动归还 GIL 的调用方，报错信息都会指向 nogil 本身而不是真正的失败点，排查方向被带偏；与本轮 BUG-4/BUG-9「异常在兜底路径变形或消失」同族，但这条不是静默吞掉，是替换。
建议: __exit__ 里改为 `if self._released: self.acquire()`，保持 return False （不吞任何异常），不改 release/acquire 自身的报错语义，也不改 nogil 的对外契约。
- reported_by: cypy-polisher
- task_id: T0r17

## BUG-13 [2026-09-26T10:07:36Z] [medium] OPEN
- summary: [judge-brittleness] tests/test_incremental.py:547 TestDigestCost 用墙钟阈值 `digest_elapsed < 2.0` 判性能，代价取决于同进程里先跑过多少用例（CPython 循环 GC 要扫既有堆）——同一份产品代码在单跑时 0.5s、整文件跑后 3.385s，判据跨收集顺序不可复现，把门禁 ① 变成抛硬币
- detail: 现象: 终态全量 `python -m pytest tests/ -q` 从 1 红变 2 红，新增的红条是 tests/test_incremental.py::TestDigestCost::test_digest_cost_on_ten_thousand_line_module，原文 `AssertionError: digest cost too high: 3.223s`（sweep5）与 `3.385s`（只跑 tests/test_incremental.py 单文件，1 failed, 37 passed）。同一条用例单独跑（1 passed in 6.12s）与只跑 TestStructuralDigest+本用例（21 passed）都是绿的——判据结论随收集顺序翻面。
被测量本身没有变慢：`meas_digest_cost.out.txt` 用同一份 tests/test_incremental.py 里的 _large_module/parse_source/ASTDiffer 复测，1100 个顶层定义的摘要 CPU 时间 0.391/0.406/0.422s（三次），墙钟 0.510/0.530/0.708s。`meas_digest_gc.out.txt` 再把机制钉住：往同一进程灌 1.5M 个循环对象（alloc_blocks 135568→3135582）后 CPU 时间仍 0.42→0.47s 不变，墙钟 0.793→0.945s；对这些对象执行 gc.freeze()（活对象数不变）墙钟又回落到 0.544s。⇒ 超时的那 2~3s 花在 GC 扫描进程既有堆 + 被抢占（同脚本纯 CPU 校准循环 wall/cpu 比 1.28~1.40，即约三成墙钟根本不在 CPU 上），不花在 cypyc 的摘要计算上。
定性: 产品侧 [误报]（cypyc/incremental/ast_differ.py 自 2026-09-25 16:39 未改，本轮 sweep4→sweep5 之间唯一产品改动是 cypy_bridge/nogil.py 的异常传播守卫，不在被测路径上）；判据侧 [真缺陷] → 入账本单。门禁 ① 的「全绿」因此不可复现：任何一次全量都可能因为无关用例先跑而红。
建议（择一，都属改既有判据，交指挥官裁决，本轮不自行落地）: ① 计时改用 `time.process_time()`（或取 wall 与 cpu 的较大者）并保留同量级阈值；② 计时前 `gc.collect()` 后 `gc.disable()`、并对堆做 `gc.freeze()`，使代价只随被测 AST 规模增长；③ 把该用例标 `@pytest.mark.perf` 并默认不收集，只在专用 `-m perf` 单进程运行里判；④ 把绝对阈值改成同进程内的相对比值（例如 digest 成本 / 一次 parse 成本），堆噪声自然抵消。
本轮处置: 不修、不降阈值（红线：tests/ 只补回归不改语义；门禁只能破红线转正时交回指挥官）。终态报告按收集顺序披露，并给出上面三条可复跑证据日志。
- reported_by: cypy-polisher
- task_id: T0r18

