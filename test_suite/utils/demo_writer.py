"""
DEMO 自动写入工具
将测试通过的代码自动写入 DEMO 目录
"""
import os
from typing import List, Dict
from ..core.test import TestResult


class DemoWriter:
    def __init__(self, demo_dir: str = None):
        self.demo_dir = demo_dir or os.path.join(os.path.dirname(__file__), '..', '..', 'DEMO')
        self.demo_dir = os.path.abspath(self.demo_dir)
    
    def write_demo(self, category: str, name: str, source: str) -> str:
        """
        将测试通过的代码写入 DEMO 目录
        
        :param category: 分类（parser/analyzer/codegen/integration）
        :param name: 示例名称
        :param source: 源代码
        :return: 写入的文件路径
        """
        category_dir = os.path.join(self.demo_dir, category)
        os.makedirs(category_dir, exist_ok=True)
        
        # 生成安全的文件名
        safe_name = name.replace('/', '_').replace('\\', '_').replace(':', '_').replace(' ', '_')
        file_path = os.path.join(category_dir, f"{safe_name}.cypy")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(source)
        
        return file_path
    
    def sync_from_tests(self, test_results: List[TestResult]) -> Dict[str, List[str]]:
        """
        从测试结果同步通过的示例
        
        :param test_results: 测试结果列表
        :return: 分类到文件路径列表的映射
        """
        result_map: Dict[str, List[str]] = {}
        
        for result in test_results:
            if result.success and result.has_demo:
                category = result.demo_category
                name = result.demo_name or result.test_name
                source = result.demo_source
                
                if category not in result_map:
                    result_map[category] = []
                
                file_path = self.write_demo(category, name, source)
                result_map[category].append(file_path)
        
        return result_map
    
    def list_demos(self, category: str = None) -> List[str]:
        """
        列出 DEMO 目录中的所有示例
        
        :param category: 分类（可选）
        :return: 文件路径列表
        """
        demos = []
        
        if category:
            category_dir = os.path.join(self.demo_dir, category)
            if os.path.exists(category_dir):
                for file in sorted(os.listdir(category_dir)):
                    if file.endswith('.cypy'):
                        demos.append(os.path.join(category_dir, file))
        else:
            for cat in ['parser', 'analyzer', 'codegen', 'integration']:
                cat_dir = os.path.join(self.demo_dir, cat)
                if os.path.exists(cat_dir):
                    for file in sorted(os.listdir(cat_dir)):
                        if file.endswith('.cypy'):
                            demos.append(os.path.join(cat_dir, file))
        
        return demos
    
    def clean_demo(self, category: str = None) -> int:
        """
        清理 DEMO 目录
        
        :param category: 分类（可选，不指定则清理所有）
        :return: 删除的文件数量
        """
        deleted = 0
        
        if category:
            category_dir = os.path.join(self.demo_dir, category)
            if os.path.exists(category_dir):
                for file in os.listdir(category_dir):
                    if file.endswith('.cypy'):
                        os.remove(os.path.join(category_dir, file))
                        deleted += 1
        else:
            for cat in ['parser', 'analyzer', 'codegen', 'integration']:
                cat_dir = os.path.join(self.demo_dir, cat)
                if os.path.exists(cat_dir):
                    for file in os.listdir(cat_dir):
                        if file.endswith('.cypy'):
                            os.remove(os.path.join(cat_dir, file))
                            deleted += 1
        
        return deleted
    
    def get_demo_content(self, category: str, name: str) -> str:
        """
        获取 DEMO 内容
        
        :param category: 分类
        :param name: 示例名称（不含 .cypy 后缀）
        :return: 源代码内容
        """
        safe_name = name.replace('/', '_').replace('\\', '_').replace(':', '_').replace(' ', '_')
        file_path = os.path.join(self.demo_dir, category, f"{safe_name}.cypy")
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
