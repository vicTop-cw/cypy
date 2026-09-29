#!/usr/bin/env python3
"""Probe: does ProjectCompiler.type_check_module drop ScopeAnalyzer diagnostics?

Three measurements in one run, same AST source:
  1. ScopeAnalyzer alone            -> what the analyzer actually found
  2. TypeChecker alone              -> what the project path currently reports
  3. ProjectCompiler.type_check_module -> the value both callers gate on

Defect reproduced when 1 is non-empty while 3 is (True, []).
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

SOURCES = {
    "uses_undefined.cypy": "def f() -> int:\n    return not_a_real_name\n",
    "struct_in_func.cypy": ("def f() -> int:\n"
                            "    struct Inner:\n"
                            "        x: int\n"
                            "    return 1\n"),
    # 名字冲突族：ScopeAnalyzer 的 _check_redefinition 负责，TypeChecker 未必看
    "dup_type_constraint.cypy": "type Thing = int\nconstraint Thing = int | float\n",
    "dup_let.cypy": "let a: int = 1\nlet a: int = 2\n",
    "dup_subtype_class.cypy": "subtype Money <: int\nclass Money:\n    x: int\n    def get_x(self) -> int:\n        return self.x\n",
    "dup_func.cypy": "def f() -> int:\n    return 1\ndef f() -> int:\n    return 2\n",
}


def main():
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
    from cypyc.analyzer.type_checker import TypeChecker
    from cypyc.project.project_compiler import ProjectCompiler

    with tempfile.TemporaryDirectory() as tmpdir:
        for name, src in SOURCES.items():
            with open(os.path.join(tmpdir, name), "w", encoding="utf-8") as f:
                f.write(src)

        pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
        pc.discover_modules()
        pc.parse_all_modules()
        pc.build_dependency_graph()
        pc.collect_type_exports()

        print("modules:", sorted(pc._ast_cache))
        for module_name, ast in sorted(pc._ast_cache.items()):
            scope = ScopeAnalyzer()
            scope.analyze(ast)
            tc = TypeChecker()
            tc.check(ast)
            ok, errors = pc.type_check_module(module_name)
            print(f"--- {module_name}")
            print(f"  1 ScopeAnalyzer.errors = {scope.errors!r}")
            print(f"  2 TypeChecker.errors   = {tc.errors!r}")
            print(f"  3 type_check_module    = ok={ok} errors={errors!r}")
            leaked = bool(scope.errors) and ok and not errors
            print(f"  => {'DROPPED (defect reproduced)' if leaked else 'no drop'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
