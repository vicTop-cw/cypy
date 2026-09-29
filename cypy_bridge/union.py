"""
Cypy Bridge Union Types
实现Cython风格的联合类型支持，允许一个值可以是多种类型之一。
"""

import ctypes
from typing import Any, Type, Tuple, Union, Optional, List
from .core import BridgeError, TypeConversionError


class UnionTypeError(BridgeError):
    """联合类型相关错误"""
    pass


class CUnion:
    """联合类型封装类
    
    联合类型允许一个内存位置存储多种不同类型的值，但同一时间只能存储一种类型。
    
    示例：
        # 创建联合类型（成员是 ctypes 类型或 C 类型名字符串）
        from ctypes import c_int, c_double
        my_union = CUnion(c_int, c_double)      # 等价：CUnion("int", "double")

        # 设置值
        my_union.value = 42  # 存进 int 成员
        my_union.value = 3.14  # 存进 double 成员

        # 获取值（按当前活跃成员解释）
        print(my_union.value)  # 3.14
    """
    
    def __init__(self, *member_types: Type):
        """
        创建联合类型
        
        参数：
            member_types: 联合成员类型（可以是ctypes类型或类型名称字符串）
        """
        if not member_types:
            raise UnionTypeError("Union must have at least one member type")
        
        # 解析成员类型
        self._member_types = []
        self._member_names = []
        
        for i, mtype in enumerate(member_types):
            if isinstance(mtype, str):
                from .types import _type_mapper
                ctype = _type_mapper.to_ctypes(mtype)
                name = mtype
            elif isinstance(mtype, type) and mtype.__module__ == 'builtins':
                # Python 内建类型没有 ctypes 的宽度口径（`ctypes.sizeof(int)` 直接抛
                # "this type has no size"），映射成 c_int 还是 c_long 是个未定的语义
                # 选择 ⇒ 在这里拒绝并给出口径，而不是让 ctypes 抛一条看不懂的错。
                raise UnionTypeError(
                    f"Union member {mtype.__name__!r} is a Python builtin type; "
                    f"pass a ctypes type (ctypes.c_int) or a C type name ({mtype.__name__!r})"
                )
            else:
                ctype = mtype
                name = ctype.__name__
            
            self._member_types.append(ctype)
            self._member_names.append(name)
        
        # 计算联合的大小（取最大成员类型的大小）
        self._size = max(ctypes.sizeof(t) for t in self._member_types)
        
        # 分配内存（使用ctypes直接分配）
        self._buffer = ctypes.create_string_buffer(self._size)
        
        # 当前活跃类型索引
        self._active_type_index = 0
    
    @property
    def size(self) -> int:
        """联合的大小（字节）"""
        return self._size
    
    @property
    def member_types(self) -> List[Type]:
        """联合成员类型列表"""
        return self._member_types
    
    @property
    def active_type(self) -> Type:
        """当前活跃的成员类型"""
        return self._member_types[self._active_type_index]
    
    @property
    def value(self) -> Any:
        """获取当前值"""
        ctype = self._member_types[self._active_type_index]
        return ctype.from_buffer(self._buffer).value
    
    @staticmethod
    def _store(ctype: Type, new_value: Any, buffer) -> bool:
        """把 new_value 写进 buffer，按 ctype 解释；放不下则返回 False
        
        ctypes 的整数类型对越界值是 **静默回绕**（c_ubyte(300).value == 44、
        c_byte(200).value == -56），不是抛异常，所以只 catch TypeError/ValueError
        会把截断当成成功。这里用"转换后读回"的方式校验：整数值必须能原样读回，
        否则认为这个成员装不下，交给下一个成员
        （例如 unsigned char 成员放不下 300 时改用 float 成员，读回 300.0）。
        """
        try:
            cval = ctype(new_value)
        except (TypeError, ValueError, OverflowError):
            return False
        
        stored = cval.value
        if isinstance(new_value, int) and not isinstance(new_value, bool):
            # 只对"整数写进成员"做回读校验：浮点成员本来就有精度损失，
            # 那是C的语义（cdef_union('int','float').value = 3.14 必须被接受）。
            if stored != new_value:
                return False
        
        try:
            ctype.from_buffer(buffer).value = stored
        except (TypeError, ValueError, OverflowError):
            return False
        return True
    
    @value.setter
    def value(self, new_value: Any):
        """设置值（自动推断类型）"""
        # 尝试找到合适的类型
        for i, ctype in enumerate(self._member_types):
            if self._store(ctype, new_value, self._buffer):
                self._active_type_index = i
                return
        
        raise UnionTypeError(f"Value {new_value} cannot be converted to any member type")
    
    def set_value(self, new_value: Any, type_index: int):
        """设置值并指定类型索引
        
        异常：
            UnionTypeError: 索引非法，或该成员放不下这个值
                （越界整数会被 ctypes 静默回绕，所以显式指定索引时必须拒绝，
                  而不是像 value setter 那样退到别的成员）
        """
        if type_index < 0 or type_index >= len(self._member_types):
            raise UnionTypeError(f"Invalid type index {type_index}")
        
        ctype = self._member_types[type_index]
        if not self._store(ctype, new_value, self._buffer):
            raise UnionTypeError(
                f"Value {new_value} does not fit member {type_index} "
                f"({getattr(ctype, '__name__', ctype)}); it would be truncated"
            )
        self._active_type_index = type_index
    
    def get_value_as(self, type_index: int) -> Any:
        """按指定类型获取值（类型转换）"""
        if type_index < 0 or type_index >= len(self._member_types):
            raise UnionTypeError(f"Invalid type index {type_index}")
        
        ctype = self._member_types[type_index]
        return ctype.from_buffer(self._buffer).value
    
    def __repr__(self):
        return f"CUnion({', '.join(self._member_names)})"


def cdef_union(*member_types: Type) -> CUnion:
    """声明联合类型（类似Cython的cdef union）
    
    示例：
        # 创建联合类型
        my_union = cdef_union("int", "float")
        
        # 设置值
        my_union.value = 42
        
        # 获取值
        print(my_union.value)  # 42
    """
    return CUnion(*member_types)


def union(*member_types: Type) -> CUnion:
    """声明联合类型（简化版）

    示例：
        my_union = union("int", "double")     # 或 union(ctypes.c_int, ctypes.c_double)
    """
    return CUnion(*member_types)


# 类型别名
CUnionType = CUnion


__all__ = [
    'CUnion',
    'CUnionType',
    'cdef_union',
    'union',
    'UnionTypeError',
]
