from typing import Dict, Optional, List


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
            "Vec": "list",
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
        
        self.numeric_types = {"int", "float", "double"}
        
        self.lz_generic_types = {
            "List": self._map_list_type,
            "Option": self._map_option_type,
            "Result": self._map_result_type,
            "Dict": self._map_dict_type,
            "Tuple": self._map_tuple_type,
        }

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

    def is_lz_generic_type(self, type_name: str) -> bool:
        return type_name in self.lz_generic_types

    def map_lz_generic_type(self, type_name: str, type_args: List[str]) -> str:
        if type_name in self.lz_generic_types:
            return self.lz_generic_types[type_name](type_args)
        return f"{type_name}[{', '.join(type_args)}]"

    def _map_list_type(self, type_args: List[str]) -> str:
        return "list"

    def _map_option_type(self, type_args: List[str]) -> str:
        if type_args:
            return f"{type_args[0]} | None"
        return "object"

    def _map_result_type(self, type_args: List[str]) -> str:
        if len(type_args) >= 2:
            return f"({type_args[0]}, Exception)"
        elif len(type_args) == 1:
            return f"({type_args[0]}, Exception)"
        return "object"

    def _map_dict_type(self, type_args: List[str]) -> str:
        return "dict"

    def _map_tuple_type(self, type_args: List[str]) -> str:
        return "tuple"
