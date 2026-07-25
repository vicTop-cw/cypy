from typing import Dict, Optional


class TypeMapper:
    def __init__(self):
        self.cypy_to_cython: Dict[str, str] = {
            "int": "int",
            "float": "float",
            "str": "str",
            "bool": "bool",
            "None": "None",
            "list": "list",
            "dict": "dict",
            "set": "set",
            "tuple": "tuple",
            "Never": "NoReturn",
            "double": "double",
        }

        self.cypy_to_c: Dict[str, str] = {
            "int": "int",
            "float": "double",
            "str": "char*",
            "bool": "bint",
            "None": "void*",
            "Never": "void",
            "double": "double",
        }
        
        # 数值类型集合，用于类型检查和隐式转换
        self.numeric_types = {"int", "float", "double"}

    def to_cython(self, cypy_type: str) -> str:
        return self.cypy_to_cython.get(cypy_type, cypy_type)

    def to_c(self, cypy_type: str) -> str:
        return self.cypy_to_c.get(cypy_type, cypy_type)

    def is_builtin(self, type_name: str) -> bool:
        return type_name in self.cypy_to_cython

    def add_custom_type(self, name: str, cython_type: str, c_type: str) -> None:
        self.cypy_to_cython[name] = cython_type
        self.cypy_to_c[name] = c_type

    def get_pointer_type(self, base_type: str) -> str:
        c_type = self.to_c(base_type)
        return f"{c_type}*"

    def get_ref_type(self, base_type: str) -> str:
        c_type = self.to_c(base_type)
        return f"{c_type}&"
