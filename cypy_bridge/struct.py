"""
Cypy Bridge Struct Definitions

提供与Cython等价的结构体定义功能，支持cdef struct风格。
"""

import ctypes
from typing import Any, Type, Dict, List
from .core import BridgeError, StructError, size_of, offset_of, align_of


class StructField:
    """结构体字段定义"""
    
    def __init__(self, name: str, ctype: Type, offset: int = 0):
        self.name = name
        self.ctype = ctype
        self.offset = offset
    
    def __repr__(self):
        return f"StructField({self.name}, {self.ctype.__name__}, offset={self.offset})"


class Struct:
    """结构体类：封装ctypes Structure"""
    
    def __init__(self, name: str, fields: List[StructField]):
        self.name = name
        self.fields = fields
        
        # 构建ctypes Structure类
        self._fields_ = [(f.name, f.ctype) for f in fields]
        self._struct_class = type(
            name,
            (ctypes.Structure,),
            {'_fields_': self._fields_}
        )
        
        # 计算字段偏移量
        for i, field in enumerate(fields):
            field.offset = getattr(self._struct_class, field.name).offset
    
    @property
    def struct_class(self):
        """返回底层ctypes Structure类"""
        return self._struct_class
    
    @property
    def size(self):
        """返回结构体大小"""
        return size_of(self._struct_class)
    
    @property
    def alignment(self):
        """返回结构体对齐要求"""
        return align_of(self._struct_class)
    
    def create(self, **kwargs):
        """创建结构体实例
        
        参数：
            **kwargs: 字段名和值
        
        返回：
            ctypes Structure实例
        """
        instance = self._struct_class()
        for name, value in kwargs.items():
            if hasattr(instance, name):
                setattr(instance, name, value)
            else:
                raise StructError(f"Field '{name}' not found in struct '{self.name}'")
        return instance
    
    def get_field_offset(self, field_name: str) -> int:
        """获取字段偏移量
        
        参数：
            field_name: 字段名称
        
        返回：
            字段偏移量
        """
        try:
            return offset_of(self._struct_class, field_name)
        except Exception as e:
            raise StructError(f"Failed to get offset for field '{field_name}': {e}")
    
    def get_field_type(self, field_name: str) -> Type:
        """获取字段类型
        
        参数：
            field_name: 字段名称
        
        返回：
            字段类型
        """
        for field in self.fields:
            if field.name == field_name:
                return field.ctype
        raise StructError(f"Field '{field_name}' not found in struct '{self.name}'")
    
    def __repr__(self):
        fields_str = ", ".join(f"{f.name}: {f.ctype.__name__}" for f in self.fields)
        return f"Struct({self.name}, [{fields_str}])"


def struct(name: str, **fields: Type) -> Struct:
    """定义结构体（类似Cython的cdef struct）
    
    用法：
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        p = Point.create(x=10, y=20)
    
    参数：
        name: 结构体名称
        **fields: 字段名称和类型
    
    返回：
        Struct对象
    """
    struct_fields = []
    for field_name, ctype in fields.items():
        struct_fields.append(StructField(field_name, ctype))
    
    return Struct(name, struct_fields)


def sizeof_struct(struct_obj: Struct) -> int:
    """获取结构体大小
    
    参数：
        struct_obj: Struct对象
    
    返回：
        结构体大小（字节）
    """
    return struct_obj.size


def offset_of_field(struct_obj: Struct, field_name: str) -> int:
    """获取结构体字段偏移量
    
    参数：
        struct_obj: Struct对象
        field_name: 字段名称
    
    返回：
        字段偏移量
    """
    return struct_obj.get_field_offset(field_name)


def pack_struct(struct_obj: Struct, data: bytes) -> Any:
    """将字节数据解包为结构体实例
    
    参数：
        struct_obj: Struct对象
        data: 字节数据
    
    返回：
        结构体实例
    """
    if len(data) < struct_obj.size:
        raise StructError(f"Data too short for struct '{struct_obj.name}'")
    
    instance = struct_obj._struct_class()
    ctypes.memmove(ctypes.byref(instance), data, struct_obj.size)
    return instance


def unpack_struct(instance) -> bytes:
    """将结构体实例打包为字节数据
    
    参数：
        instance: ctypes Structure实例
    
    返回：
        字节数据
    """
    size = ctypes.sizeof(type(instance))
    buf = ctypes.create_string_buffer(size)
    ctypes.memmove(buf, ctypes.byref(instance), size)
    return bytes(buf)


__all__ = [
    'Struct',
    'StructField',
    'struct',
    'sizeof_struct',
    'offset_of_field',
    'pack_struct',
    'unpack_struct',
]
