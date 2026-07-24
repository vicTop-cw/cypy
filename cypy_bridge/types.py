"""
Cypy Bridge Type System

提供类型映射、类型声明和类型推断功能，与Cython的cdef/cpdef语法等价。
"""

import ctypes
from typing import Any, Type, Dict, Optional, Callable, Tuple
from .core import BridgeError, TypeConversionError


class TypeMapper:
    """类型映射器：负责Cypy类型到ctypes/C类型的映射"""
    
    def __init__(self):
        self.cypy_to_ctypes: Dict[str, Type] = {
            # 有符号整数类型
            "int": ctypes.c_int,
            "long": ctypes.c_long,
            "long long": ctypes.c_longlong,
            "short": ctypes.c_short,
            "char": ctypes.c_char,
            "signed char": ctypes.c_char,
            "signed int": ctypes.c_int,
            "signed long": ctypes.c_long,
            "signed long long": ctypes.c_longlong,
            "signed short": ctypes.c_short,
            
            # 无符号整数类型
            "unsigned": ctypes.c_uint,
            "unsigned char": ctypes.c_ubyte,
            "unsigned int": ctypes.c_uint,
            "unsigned long": ctypes.c_ulong,
            "unsigned long long": ctypes.c_ulonglong,
            "unsigned short": ctypes.c_ushort,
            "uint": ctypes.c_uint,
            "uint32": ctypes.c_uint32,
            "uint64": ctypes.c_uint64,
            "int32": ctypes.c_int32,
            "int64": ctypes.c_int64,
            
            # 浮点类型
            "float": ctypes.c_float,
            "double": ctypes.c_double,
            "long double": ctypes.c_longdouble,
            
            # 布尔类型
            "bool": ctypes.c_bool,
            "_Bool": ctypes.c_bool,
            
            # 指针类型
            "void *": ctypes.c_void_p,
            "pointer": ctypes.c_void_p,
            
            # 尺寸类型
            "size_t": ctypes.c_size_t,
            "ssize_t": ctypes.c_ssize_t,
            "ptrdiff_t": getattr(ctypes, 'c_ptrdiff_t', ctypes.c_long),
            
            # 其他类型
            "void": type(None),
            "PyObject*": ctypes.py_object,
        }
        
        self.cypy_to_c: Dict[str, str] = {
            # 有符号整数类型
            "int": "int",
            "long": "long",
            "long long": "long long",
            "short": "short",
            "char": "char",
            "signed char": "signed char",
            "signed int": "signed int",
            "signed long": "signed long",
            "signed long long": "signed long long",
            "signed short": "signed short",
            
            # 无符号整数类型
            "unsigned": "unsigned",
            "unsigned char": "unsigned char",
            "unsigned int": "unsigned int",
            "unsigned long": "unsigned long",
            "unsigned long long": "unsigned long long",
            "unsigned short": "unsigned short",
            "uint": "unsigned int",
            "uint32": "uint32_t",
            "uint64": "uint64_t",
            "int32": "int32_t",
            "int64": "int64_t",
            
            # 浮点类型
            "float": "float",
            "double": "double",
            "long double": "long double",
            
            # 布尔类型
            "bool": "bool",
            "_Bool": "_Bool",
            
            # 指针类型
            "void *": "void*",
            "pointer": "void*",
            
            # 尺寸类型
            "size_t": "size_t",
            "ssize_t": "ssize_t",
            "ptrdiff_t": "ptrdiff_t",
            
            # 其他类型
            "void": "void",
            "PyObject*": "PyObject*",
        }
    
    def to_ctypes(self, cypy_type: str) -> Type:
        """将Cypy类型转换为ctypes类型"""
        return self.cypy_to_ctypes.get(cypy_type, ctypes.py_object)
    
    def to_c(self, cypy_type: str) -> str:
        """将Cypy类型转换为C类型字符串"""
        return self.cypy_to_c.get(cypy_type, cypy_type)
    
    def is_builtin(self, type_name: str) -> bool:
        """检查类型是否是内置类型"""
        return type_name in self.cypy_to_ctypes
    
    def add_custom_type(self, name: str, ctypes_type: Type, c_type: str) -> None:
        """添加自定义类型映射"""
        self.cypy_to_ctypes[name] = ctypes_type
        self.cypy_to_c[name] = c_type
    
    def list_types(self) -> list:
        """列出所有支持的类型"""
        return list(self.cypy_to_ctypes.keys())


# 全局类型映射器
_type_mapper = TypeMapper()


# 类型别名
int_ = ctypes.c_int
float_ = ctypes.c_float
double_ = ctypes.c_double
bool_ = ctypes.c_bool
str_ = ctypes.c_char_p
void = type(None)
size_t = ctypes.c_size_t

# 扩展类型别名（使用getattr处理兼容性）
long_ = ctypes.c_long
longlong_ = ctypes.c_longlong
short_ = ctypes.c_short
char_ = ctypes.c_char
byte_ = ctypes.c_byte
ubyte_ = ctypes.c_ubyte
uint_ = ctypes.c_uint
ulong_ = ctypes.c_ulong
ulonglong_ = ctypes.c_ulonglong
ushort_ = ctypes.c_ushort
int32_ = ctypes.c_int32
int64_ = ctypes.c_int64
uint32_ = ctypes.c_uint32
uint64_ = ctypes.c_uint64
ssize_t = ctypes.c_ssize_t
ptrdiff_t = getattr(ctypes, 'c_ptrdiff_t', ctypes.c_long)
longdouble_ = getattr(ctypes, 'c_longdouble', ctypes.c_double)
void_p = ctypes.c_void_p


class CDefType:
    """C类型声明包装器"""
    
    def __init__(self, ctype: Type):
        self.ctype = ctype
    
    def __getitem__(self, key):
        """支持数组类型"""
        if isinstance(key, int):
            # 在Python 3.13中，ArrayType不再直接暴露，使用类型乘法创建数组
            return type(self.ctype * key)
        return self.ctype
    
    def __repr__(self):
        return f"CDefType({self.ctype.__name__})"


class CDefVariable:
    """C类型变量包装器"""
    
    def __init__(self, ctype: Type, value: Any = None):
        self.ctype = ctype
        self._value = ctype() if value is None else ctype(value)
    
    @property
    def value(self):
        return self._value.value
    
    @value.setter
    def value(self, new_value):
        self._value.value = new_value
    
    def __int__(self):
        return int(self.value)
    
    def __float__(self):
        return float(self.value)
    
    def __bool__(self):
        return bool(self.value)
    
    def __repr__(self):
        return f"CDefVariable({self.ctype.__name__}, {self.value})"


def cdef(type_name: str) -> CDefType:
    """声明C类型（类似Cython的cdef）
    
    用法：
        int_type = cdef("int")
        x = int_type()  # 创建C int类型变量
    """
    ctype = _type_mapper.to_ctypes(type_name)
    return CDefType(ctype)


class CPDefFunction:
    """cpdef函数包装器：同时具有C和Python接口"""
    
    def __init__(self, func: Callable, arg_types: Tuple[Type, ...] = None, 
                 return_type: Type = ctypes.py_object):
        self.func = func
        self.arg_types = arg_types
        self.return_type = return_type
        self._compiled = False
    
    def __call__(self, *args, **kwargs):
        """调用函数"""
        # 如果有类型声明，进行类型转换
        converted_args = []
        if self.arg_types:
            for i in range(min(len(args), len(self.arg_types))):
                arg = args[i]
                # 如果已经是ctypes对象，提取value
                if hasattr(arg, 'value'):
                    converted_args.append(arg.value)
                else:
                    converted_args.append(self.arg_types[i](arg).value)
            args = tuple(converted_args)
        
        result = self.func(*args, **kwargs)
        
        # 如果有返回类型声明，进行类型转换
        if self.return_type and self.return_type != ctypes.py_object:
            if hasattr(result, 'value'):
                return result.value
            return self.return_type(result).value
        
        return result
    
    def compile(self):
        """编译函数（优化调用性能）"""
        self._compiled = True
        return self
    
    def __repr__(self):
        return f"CPDefFunction({self.func.__name__})"


def cpdef(func: Callable = None, *, arg_types=None, return_type=None):
    """声明cpdef函数（类似Cython的cpdef）
    
    用法：
        @cpdef
        def add(a, b):
            return a + b
        
        @cpdef(arg_types=(ctypes.c_int, ctypes.c_int), return_type=ctypes.c_int)
        def add_fast(a, b):
            return a + b
    """
    def decorator(f):
        return CPDefFunction(f, arg_types=arg_types, return_type=return_type)
    
    if func is None:
        return decorator
    return decorator(func)


def infer_type(value: Any) -> Type:
    """类型推断：根据值推断ctypes类型"""
    if isinstance(value, int):
        return ctypes.c_int
    elif isinstance(value, float):
        return ctypes.c_double
    elif isinstance(value, bool):
        # ctypes.c_bool在某些Python版本中可能不存在，使用c_int替代
        try:
            return ctypes.c_bool
        except AttributeError:
            return ctypes.c_int
    elif isinstance(value, bytes):
        return ctypes.c_char_p
    elif isinstance(value, str):
        return ctypes.c_char_p
    elif value is None:
        return type(None)
    else:
        return ctypes.py_object


def declare(type_name: str, name: str, value: Any = None) -> CDefVariable:
    """声明变量并可选初始化
    
    用法：
        x = declare("int", "x", 42)
        y = declare("double", "y")
    """
    ctype = _type_mapper.to_ctypes(type_name)
    return CDefVariable(ctype, value)


def cast(type_name: str, value: Any):
    """类型转换（类似Cython的<type>value语法）
    
    参数：
        type_name: 目标类型名称（如"int", "float", "double"）或ctypes类型
        value: 要转换的值
    
    返回：
        转换后的值（Python类型）
    
    示例：
        >>> cast("int", 3.14)
        3
        >>> cast("double", 42)
        42.0
        >>> cast(ctypes.c_int, 3.14)
        3
    """
    if isinstance(type_name, str):
        ctype = _type_mapper.to_ctypes(type_name)
    else:
        ctype = type_name
    
    if ctype == ctypes.py_object:
        return value
    
    # 如果已经是ctypes对象，提取value
    if hasattr(value, 'value'):
        value = value.value
    
    # 执行类型转换
    try:
        # 对于整数类型，先使用Python的int()转换
        if ctype in (ctypes.c_int, ctypes.c_long, ctypes.c_short, 
                     ctypes.c_char, ctypes.c_byte, ctypes.c_ubyte,
                     ctypes.c_uint, ctypes.c_ulong, ctypes.c_ushort):
            value = int(value)
        # 对于浮点类型，先使用Python的float()转换
        elif ctype in (ctypes.c_float, ctypes.c_double):
            value = float(value)
        
        return ctype(value).value
    except (TypeError, ValueError) as e:
        raise TypeConversionError(f"Failed to cast {value} to {type_name}: {e}")


def ccast(value: Any, type_name: str):
    """C风格类型转换（与cast相同，参数顺序相反）
    
    参数：
        value: 要转换的值
        type_name: 目标类型名称
    
    返回：
        转换后的值
    
    示例：
        >>> ccast(3.14, "int")
        3
    """
    return cast(type_name, value)


__all__ = [
    'TypeMapper',
    'cdef',
    'cpdef',
    'int_',
    'float_',
    'double_',
    'bool_',
    'str_',
    'void',
    'size_t',
    # 扩展类型别名
    'long_',
    'longlong_',
    'short_',
    'char_',
    'byte_',
    'ubyte_',
    'uint_',
    'ulong_',
    'ulonglong_',
    'ushort_',
    'int32_',
    'int64_',
    'uint32_',
    'uint64_',
    'ssize_t',
    'ptrdiff_t',
    'longdouble_',
    'void_p',
    'CDefType',
    'CDefVariable',
    'CPDefFunction',
    'infer_type',
    'declare',
    'cast',
    'ccast',
]
