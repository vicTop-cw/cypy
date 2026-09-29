"""预处理器回归测试（2026-Q3 审计 T0r61.2.2）。

覆盖两个缺陷族：

1. 缺陷 01 —— ``#include`` 文件名此前用 f-string 直接拼接，并在失败后回退到
   ``open(filename)``，于是 ``<../../x>``、``..\\..\\x``、引号形式、绝对路径、
   CWD 相对路径都能读到搜索根之外的任意文件；找不到的头文件还被静默吞掉。
   现在：绝对路径 / ``..`` 上溯显式报错，解析后用 realpath 做包含性检查，
   配置了搜索根时“找不到”也是显式错误。
   兼容性决策：``cypy_hook/hook.py:91``/``:212`` 以空 include_paths 构造预处理器，
   因此在**没有任何搜索根**时仍保留旧的宽松行为（相对 CWD 读取，读不到就跳过），
   但逃逸类写法（绝对路径、``..``、逃出 CWD）在任何配置下都被拒绝。

2. 缺陷 04 —— ``_process_macros`` 曾对每个宏做一次无界 ``str.replace``，
   字符串字面量和注释里的同名标识符会被改写、且替换值会被再次扫描。
   现在替换在词法单元层面进行（见 cypyc/parser/preprocessor.py:iter_code_chunks）。
"""
import os

import pytest

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.parser.preprocessor import (
    IncludeError,
    IncludeEscape,
    IncludeNotFound,
    Preprocessor,
)

OUTSIDE_TEXT = "TOP-SECRET-OUTSIDE-ROOT-LINE-4D7A1"
LEGIT_TEXT = "let legit_var: int = 1"


@pytest.fixture
def tree(tmp_path):
    """构造：tmp_path/OUTSIDE_MARKER.txt、tmp_path/inc/incroot/legit.inc、tmp_path/cwdrel/CWD_MARKER.txt"""
    search_root = tmp_path / "inc" / "incroot"
    nested = search_root / "sub"
    nested.mkdir(parents=True)
    (tmp_path / "cwdrel").mkdir()
    (search_root / "legit.inc").write_text(LEGIT_TEXT + "\n", encoding="utf-8")
    (nested / "deep.inc").write_text("let deep_var: int = 2\n", encoding="utf-8")
    (tmp_path / "OUTSIDE_MARKER.txt").write_text(OUTSIDE_TEXT + "\n", encoding="utf-8")
    (tmp_path / "cwdrel" / "CWD_MARKER.txt").write_text(
        "TOP-SECRET-CWD-RELATIVE-B8E50\n", encoding="utf-8")
    return {"tmp": tmp_path, "root": search_root}


def pp(*roots):
    preprocessor = Preprocessor()
    preprocessor.set_include_paths([str(r) for r in roots])
    return preprocessor


# --------------------------------------------------------------------------
# 缺陷 01：include 路径校验
# --------------------------------------------------------------------------

class TestIncludeContainment:
    def test_in_root_include_is_inlined(self, tree):
        out = pp(tree["root"]).process("#include <legit.inc>\n")
        assert LEGIT_TEXT in out

    def test_nested_dir_inside_root_is_allowed(self, tree):
        out = pp(tree["root"]).process("#include <sub/deep.inc>\n")
        assert "let deep_var: int = 2" in out

    @pytest.mark.parametrize("form", ["<../%s>" % "OUTSIDE_MARKER.txt",
                                      "<..\\%s>" % "OUTSIDE_MARKER.txt",
                                      '"../../OUTSIDE_MARKER.txt"'])
    def test_parent_traversal_rejected(self, tree, form):
        with pytest.raises(IncludeEscape):
            pp(tree["root"]).process(f"#include {form}\n")

    def test_parent_traversal_rejected_even_two_levels_up(self, tree):
        # 原始缺陷形态：#include <../../OUTSIDE_MARKER.txt>
        with pytest.raises(IncludeError):
            pp(tree["root"]).process("#include <../../OUTSIDE_MARKER.txt>\n")

    def test_quoted_parent_traversal_rejected(self, tree):
        with pytest.raises(IncludeError):
            pp(tree["root"]).process('#include "../../OUTSIDE_MARKER.txt"\n')

    def test_absolute_path_rejected_with_roots(self, tree):
        marker = str(tree["tmp"] / "OUTSIDE_MARKER.txt")
        with pytest.raises(IncludeEscape):
            pp(tree["root"]).process(f'#include "{marker}"\n')

    def test_absolute_path_rejected_without_roots(self, tree):
        # cypy_hook 形态（空 include_paths）也必须拒绝绝对路径
        marker = (str(tree["tmp"] / "OUTSIDE_MARKER.txt")).replace("\\", "/")
        with pytest.raises(IncludeEscape):
            pp().process(f"#include <{marker}>\n")

    def test_absolute_path_rejected_with_drive_letter(self):
        with pytest.raises(IncludeEscape):
            pp().process("#include <C:/Windows/win.ini>\n")

    def test_cwd_relative_include_not_read_when_roots_configured(self, tree, monkeypatch):
        monkeypatch.chdir(tree["tmp"])
        with pytest.raises(IncludeNotFound):
            pp(tree["root"]).process("#include <cwdrel/CWD_MARKER.txt>\n")

    def test_missing_include_is_an_explicit_error(self, tree):
        with pytest.raises(IncludeNotFound):
            pp(tree["root"]).process("#include <does_not_exist.inc>\nlet x: int = 1\n")

    def test_no_roots_keeps_permissive_cwd_read(self, tree, monkeypatch):
        # cypy_hook/hook.py:91 传空 include_paths：无搜索根时保持旧的宽松行为，
        # 否则普通构建会从“可编译”变成“硬失败”。
        monkeypatch.chdir(tree["tmp"])
        out = pp().process("#include <cwdrel/CWD_MARKER.txt>\n")
        assert "TOP-SECRET-CWD-RELATIVE-B8E50" in out

    def test_no_roots_missing_file_is_skipped_not_fatal(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert pp().process("#include <nowhere.inc>\nlet x: int = 1\n") == "let x: int = 1\n"

    def test_no_roots_parent_traversal_still_rejected(self, tree, monkeypatch):
        monkeypatch.chdir(tree["tmp"])
        with pytest.raises(IncludeEscape):
            pp().process("#include <../OUTSIDE_MARKER.txt>\n")

    def test_empty_include_name_rejected(self, tree):
        with pytest.raises(IncludeError):
            pp(tree["root"])._read_include_file("   ")

    def test_escaping_never_reads_the_file(self, tree):
        # 内容既不落进输出，也不产生部分展开
        out = ""
        with pytest.raises(IncludeError):
            out = pp(tree["root"]).process("#include <../../OUTSIDE_MARKER.txt>\n")
        assert OUTSIDE_TEXT not in out

    def test_realpath_containment_helper(self, tree):
        root = str(tree["root"])
        inside = str(tree["root"] / "legit.inc")
        outside = str(tree["tmp"] / "OUTSIDE_MARKER.txt")
        assert Preprocessor._is_inside(inside, root)
        assert not Preprocessor._is_inside(outside, root)
        assert not Preprocessor._is_inside(os.path.join(root, "..", "x.inc"), root)


# --------------------------------------------------------------------------
# 缺陷 04：宏替换在词法单元层面进行
# --------------------------------------------------------------------------

PP_SRC = (
    'def report():\n'
    '    print("BUFF bytes allocated")   # note: BUFF is the default\n'
    '    let BUFF_SIZE: int = 8\n'
    '    let BUFFSIZE: int = 9\n'
    '    let name: str = "BUFF"\n'
    '    return 0\n'
)


class TestDefineSubstitution:
    def test_identifier_outside_strings_and_comments_is_replaced(self):
        preprocessor = Preprocessor()
        preprocessor.add_macro("BUFF", "1024")
        out = preprocessor.process("let size: int = BUFF\n")
        assert out == "let size: int = 1024\n"

    def test_strings_comments_and_substrings_are_untouched(self):
        preprocessor = Preprocessor()
        preprocessor.add_macro("BUFF", "1024")
        out = preprocessor.process(PP_SRC)
        assert '"BUFF bytes allocated"' in out          # 字符串字面量不被改写
        assert "# note: BUFF is the default" in out      # 注释不被改写
        assert "let BUFF_SIZE: int = 8" in out           # 词边界：不是子串替换
        assert "let BUFFSIZE: int = 9" in out
        assert '"1024' not in out

    def test_substituted_text_is_not_rescanned(self):
        # 缺陷 04 的“二次扫描”形态：BUFF 的值里含有另一个宏名 MAX，
        # 替换后的文本不应再被 MAX 展开。
        preprocessor = Preprocessor()
        preprocessor.add_macro("MAX", "BUFF")
        preprocessor.add_macro("BUFF", "MAX")
        out = preprocessor.process("let v: int = BUFF\n")
        assert out == "let v: int = MAX\n"

    def test_non_identifier_macro_name_substituted_once(self):
        preprocessor = Preprocessor()
        preprocessor.add_macro("MAX(BUFF)", "0")
        preprocessor.add_macro("BUFF", "1")
        out = preprocessor.process("let v: int = MAX(BUFF)\n")
        assert out == "let v: int = 0\n"

    def test_preprocessed_output_still_parses(self):
        preprocessor = Preprocessor()
        preprocessor.add_macro("BUFF", "1024")
        tokens = list(Lexer(preprocessor.process(PP_SRC)).tokenize())
        ast = Parser(tokens).parse()
        assert ast.body and ast.body[0].name == "report"

    def test_single_quoted_string_is_untouched(self):
        preprocessor = Preprocessor()
        preprocessor.add_macro("BUFF", "1024")
        out = preprocessor.process("let s: str = 'BUFF'\n")
        assert out == "let s: str = 'BUFF'\n"

    def test_no_macros_is_identity(self):
        assert Preprocessor().process(PP_SRC) == PP_SRC


class TestPreprocessorMisc:
    def test_extract_metadata_still_works(self):
        meta = Preprocessor().extract_metadata(
            '#pragma cypy version = 1.2.0\n'
            '#pragma cypy requires = a, b\n'
            '#pragma cypy features = x\n')
        assert meta["version"] == "1.2.0"
        assert meta["requires"] == ["a", "b"]
        assert meta["features"] == ["x"]

    def test_hook_flow_with_empty_include_paths_is_unaffected(self):
        # cypy_hook 构造 Preprocessor() 后直接 process()，普通源码必须原样通过
        src = "def main():\n    print(\"hi\")   # BUFF\n    return 0\n"
        assert Preprocessor().process(src) == src


class TestFixtureWiring:
    """test_suite 夹具曾调用不存在的 Preprocessor.preprocess()（应为 process()），
    夹具一跑就 AttributeError，预处理器因此完全得不到覆盖。"""

    def test_parser_fixture_preprocess_is_wired(self, tmp_path, monkeypatch):
        pytest.importorskip("test_suite.fixtures.parser")
        from test_suite.fixtures.parser import ParserFixture

        monkeypatch.chdir(tmp_path)
        (tmp_path / "local.inc").write_text("let local_var: int = 7\n", encoding="utf-8")
        fixture = ParserFixture()
        assert fixture.preprocess("let x: int = 1\n") == "let x: int = 1\n"
        assert "let local_var: int = 7" in fixture.preprocess("#include <local.inc>\n")
        with pytest.raises(IncludeEscape):
            fixture.preprocess("#include <../escape.inc>\n")
