"""Build the polish round's report_bug batch from triaged findings.

Every entry carries: file:line, measured grep evidence, a deterministic repro command,
and a fix suggestion. Only confirmed defects belong here -- false positives found during
the same triage (cypyc/cli.py:36, cypy_bridge/pointer.py:142/412) are deliberately NOT
filed; they are listed in the polish report instead.
"""
import io
import json
import os

OUT = os.path.dirname(os.path.abspath(__file__))

BUGS = [
    dict(sev="high",
         summary="[cache] cypy_bridge/compiler.py:3656 clear_cache 把 .pyd 删除失败当成功：裸 except 吞掉后仍从 manifest 删条目",
         detail="""现象：`clear_cache(module_name)` 在 `try: os.remove(pyd_path) except: pass`（:3656-3659）之后无条件 `del manifest[cache_key]` + `_save_manifest(manifest)`；全量分支（:3668-3671）同样吞掉删除失败并无条件 `_save_manifest({})`。
后果：Windows 上被 import 的扩展模块文件锁是常态（同文件 :3760 附近就有为绕开 file lock 而换临时目录的逻辑），删除失败时磁盘上的 .pyd 仍在，但 manifest 已声称没有 → 上层按 manifest 判断「已清理」，可继续命中陈旧二进制；表现为「清了缓存但行为没变」，且全程零诊断。
复现（确定性、不编译）：构造 BridgeCacheManager，写一条 manifest 指向临时 .pyd，monkeypatch `os.remove` 抛 OSError，再调 `clear_cache(name)`；断言「删除失败 ⇒ 条目仍在 manifest 或返回值/日志能观察到失败」。当前实现两条都不满足。
判据实测：`grep -n 'except:' cypy_bridge/compiler.py` → 3658、3670 两处（全仓三包裸 except 共 2 处、`except … : pass` 共 20 处，见 `.fist-polish-20260926/markers_baseline.json`）。
建议：删除失败就不动 manifest 条目（保持「未清理」的事实），并把失败收集成可判定结果（例如返回 (cleared, failed) 或记 warning），不要静默写空 manifest。"""),
    dict(sev="high",
         summary="[subprocess] cypy_bridge/compiler.py:3795 subprocess.run 无 timeout；同仓做同一件事的另外两处都有 timeout=120",
         detail="""现象：桥接编译 `subprocess.run([sys.executable, setup_file, 'build_ext', '--inplace'], capture_output=True, cwd=tmp_dir)` 缺 `timeout`；对照 `cypyc/project/project_compiler.py:599-604`（`timeout=120`）与 `cypy_hook/hook.py:513-518`（`timeout=120`）。三包内 subprocess.run 共 3 处：2 处有超时、1 处没有。
后果：setuptools / Cython / 链接器任一环节挂死（文件锁、弹窗、交互式提示、杀软扫描）时调用线程永久阻塞——无退出码、无诊断，整条构建链卡死。另两处早已按 120 s 收口，说明这里缺失是不一致而非设计。
复现：`grep -n 'subprocess.run' cypyc/project/project_compiler.py cypy_bridge/compiler.py cypy_hook/hook.py` 三条对照，只有 bridge 那条不带 `timeout=`。
建议：补 `timeout=120`，并在 `subprocess.TimeoutExpired` 分支终止子进程、清理临时目录、产出可诊断错误（注意同文件的裸 except 家族会把这类失败一并吞掉）。"""),
    dict(sev="high",
         summary="[silent-fail] cypyc/project/project_compiler.py:826 增量重解析异常被吞：失败后仍用陈旧 AST 计算影响集并报告已传播",
         detail="""现象：:817-831 里 `try: self._reparse_module(module_name) except Exception: pass`，紧接着无条件 `get_affected_modules({module_name})` 并写入 `affected[file_path]`。
后果：重解析失败（语法错误、编码问题、解析器缺陷）时依赖图里留的是旧 AST，但该文件被登记为「已处理且影响已传播」，增量构建据此产出陈旧结果并返回成功。这是增量编译最难定位的一类故障：改坏了不报错，产物是旧的。
复现（确定性）：monkeypatch `_reparse_module` 抛异常，调用受影响模块收集入口，断言「该文件不得出现在 affected 结果里，或 errors 列表必须记录该失败」；当前实现两条都不满足。
判据实测：`grep -n 'except Exception:' cypyc/project/project_compiler.py` → :826。
建议：失败即记入 errors 且把该文件从 affected 剔除——宁可让上层判定「增量失效、需全量重建」，也不要用陈旧 AST 谎报成功。"""),
    dict(sev="medium",
         summary="[silent-fail] cypyc/transformer 五个 transformer 把递归调用包进 except (AttributeError, TypeError)，子树真实异常被吞、收集静默截断",
         detail="""现象（`cypyc/transformer/defer_transformer.py:45-54` 为例，enum/generic/struct/trait 四个同形状）：
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
建议：把守卫收窄到 `getattr` 本身（`getattr(node, attr_name, None)` 或只捕 AttributeError），递归调用移出 try，TypeError 必须向上冒。回归测试用「子节点属性是抛 TypeError 的 property」这种最小 AST 断言异常必须传播。"""),
    dict(sev="medium",
         summary="[silent-fail] cypyc/incremental/hot_reload.py:110 与 :125 状态快照/回滚吞掉 getattr/setattr 异常（含用户 property 执行失败）",
         detail="""现象：`_save_state` 在 `for name in dir(self._actual_module)` 里 `try: value = getattr(...) … except Exception: pass`（:99-111）；`_restore_state` 同样吞 setattr 失败（:120-126）。
后果：getattr 会执行模块级 property / 描述符 / 惰性导入。用户代码在这里抛错被当成「该属性不存在」跳过 ⇒ 快照不完整；热重载后只回滚了部分状态，模块停在新旧混合态，且零诊断。setattr 失败同理被吞。
判据实测：`grep -n 'except Exception:' cypyc/incremental/hot_reload.py` → :110、:125、:247、:272、:326、:451 共 6 处；本单聚焦 110/125 这一对，其余 4 处同文件同性质，修复时一并研判并逐条给结论。
建议：只捕明确不该致命的类型（AttributeError 等），把被跳过的属性名与异常记入调试日志；快照/回滚发生跳过时应让调用方可判定（例如返回跳过的名字列表）。"""),
    dict(sev="medium",
         summary="[silent-fail] cypyc/incremental/file_monitor.py:58 读不到 .py 首行即判定「不是 Cypy 文件」，变更被静默漏掉",
         detail="""现象：`_is_cypy_file` 对 .py 文件读首行判断 `#!bin cypy` 头，`except Exception: pass` 后 `return False`（:54-61）。
后果：文件此刻被占用 / 无权限 / 正在被写（监控器天然与写入方并发，同文件 :63 起就有 debounce 锁）时，读失败被当成「确定不是 Cypy 文件」→ 该文件的变更不触发重编译且无任何记录。这是把「检测失败」误当成「检测结论为否」的分类错误。
复现：monkeypatch `builtins.open` 抛 OSError，调用 `_is_cypy_file("x.py")`，断言结果不能是「静默 False 且无记录」。
判据实测：`grep -n 'except Exception:' cypyc/incremental/file_monitor.py` → :58。
建议：区分「读失败」与「读到但首行不匹配」：前者保留为待判定（延后重试或按候选处理）并落 warning，不能静默 return False。"""),
    dict(sev="low",
         summary="[diagnostics] cypy_hook/hook.py:926 与 cypy_bridge/compiler.py:3583 manifest 损坏与「文件不存在」不可区分，静默按无缓存继续",
         detail="""现象：两处 `_load_manifest` 都是 `if os.path.exists(path): try: json.load(...) except (json.JSONDecodeError, IOError): pass` 然后 `return {}`。
后果：manifest JSON 被截断/写坏（并发写、磁盘满、进程被杀）与「首次运行没有 manifest」返回值完全相同 → 上层认为没有缓存，重建后直接覆盖，损坏证据永久消失，任何人都无法判断发生过什么。缓存子系统里这是最贵的一类静默降级。
判据实测：`grep -n 'except (json.JSONDecodeError, IOError)' cypy_hook/hook.py cypy_bridge/compiler.py` → 2 命中（hook.py:926、compiler.py:3583）。
建议：损坏时先把原文件改名留证（如 `bridge_manifest.json.corrupt-<ts>`）并落 warning，再按空 manifest 继续；返回值带 `was_corrupt` 之类的可判定信号。"""),
]


def main() -> int:
    calls = [{"tool": "report_bug",
              "args": {"project_dir": ".", "severity": b["sev"], "summary": b["summary"],
                       "detail": b["detail"], "publish_task": True,
                       "reported_by": "cypy-polisher"}} for b in BUGS]
    path = os.path.join(OUT, "bugs_batch.json")
    json.dump(calls, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("bugs prepared:", len(calls))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
