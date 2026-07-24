"""
Cypy Bridge Generics Support
实现Cython风格的泛型和融合类型（fused types）支持。

融合类型是Cython的一种编译时多态机制，允许函数根据参数类型自动选择
最合适的实现，类似于C++的模板特化。
"""

import ctypes
from typing import Any, Type, Callable, Tuple, List, Dict, Union
from .core import BridgeError


class GenericError(BridgeError):
    """泛型相关错误"""
    pass


class FusedType:
    """融合类型（Fused Type）封装类
    
    融合类型是一种类型变量，可以在编译时根据实际参数类型自动选择
    对应的实现。这类似于C++的模板机制。
    
    示例：
        # 创建融合类型
        Numeric = FusedType("int", "float", "double")
        
        # 使用融合类型
        @fused(Numeric)
        def add(a, b):
            return a + b
    """
    
    def __init__(self, *types: Union[str, Type]):
        """
        创建融合类型
        
        参数：
            types: 融合类型的候选类型列表（可以是类型名称或ctypes类型）
        """
        if not types:
            raise GenericError("Fused type must have at least one type")
        
        self._types = []
        self._type_names = []
        
        for t in types:
            if isinstance(t, str):
                from .types import _type_mapper
                ctype = _type_mapper.to_ctypes(t)
                name = t
            else:
                ctype = t
                name = ctype.__name__
            
            self._types.append(ctype)
            self._type_names.append(name)
    
    @property
    def types(self) -> List[Type]:
        """候选类型列表"""
        return self._types
    
    @property
    def type_names(self) -> List[str]:
        """候选类型名称列表"""
        return self._type_names
    
    def resolve(self, value: Any) -> Type:
        """根据值解析具体类型
        
        参数：
            value: 用于推断类型的值
        
        返回：
            匹配的ctypes类型
        """
        from .types import infer_type
        
        inferred = infer_type(value)
        
        # 优先精确匹配
        if inferred in self._types:
            return inferred
        
        # 尝试兼容匹配（例如int可以匹配long）
        for ctype in self._types:
            if isinstance(value, (int, float)):
                try:
                    ctype(value)
                    return ctype
                except (TypeError, ValueError):
                    continue
        
        raise GenericError(f"Cannot resolve type for value {value} in fused type {self}")
    
    def __repr__(self):
        return f"FusedType({', '.join(self._type_names)})"


class FusedFunction:
    """融合函数封装类
    
    融合函数是一个特殊的函数，它可以根据参数类型自动选择最合适的
    实现版本。
    """
    
    def __init__(self, func: Callable, fused_types: Tuple[FusedType, ...] = None):
        """
        创建融合函数
        
        参数：
            func: 原始函数
            fused_types: 融合类型元组
        """
        self._func = func
        self._fused_types = fused_types or ()
        self._specializations: Dict[Tuple[Type, ...], Callable] = {}
    
    def specialize(self, *types: Type) -> Callable:
        """为特定类型组合创建特化版本
        
        参数：
            types: 特化类型列表
        
        返回：
            特化后的函数
        """
        def specialized_func(*args, **kwargs):
            # 类型转换
            converted_args = []
            for i, (arg, ctype) in enumerate(zip(args, types)):
                if hasattr(arg, 'value'):
                    converted_args.append(ctype(arg.value))
                else:
                    converted_args.append(ctype(arg))
            
            result = self._func(*converted_args, **kwargs)
            
            # 结果类型转换
            if hasattr(result, 'value'):
                return result.value
            return result
        
        self._specializations[types] = specialized_func
        return specialized_func
    
    def __call__(self, *args, **kwargs):
        """调用融合函数（自动选择特化版本）"""
        # 推断参数类型
        arg_types = []
        for i, arg in enumerate(args):
            if i < len(self._fused_types):
                fused_type = self._fused_types[i]
                arg_types.append(fused_type.resolve(arg))
            else:
                from .types import infer_type
                arg_types.append(infer_type(arg))
        
        type_key = tuple(arg_types)
        
        # 检查是否有已缓存的特化版本
        if type_key in self._specializations:
            return self._specializations[type_key](*args, **kwargs)
        
        # 创建新的特化版本
        return self.specialize(*type_key)(*args, **kwargs)
    
    def __repr__(self):
        return f"FusedFunction({self._func.__name__})"


def fused(*fused_types: FusedType) -> Callable:
    """融合类型装饰器（类似Cython的fused类型）
    
    示例：
        # 创建融合类型
        Numeric = FusedType("int", "float", "double")
        
        # 使用融合类型
        @fused(Numeric)
        def add(a, b):
            return a + b
        
        # 调用时自动选择类型
        result = add(3, 5)    # 使用int版本
        result = add(3.14, 2.71)  # 使用float版本
    """
    def decorator(func: Callable) -> FusedFunction:
        return FusedFunction(func, fused_types=fused_types)
    
    return decorator


def generic(*param_types: Union[FusedType, Type]) -> Callable:
    """泛型装饰器（简化版）
    
    示例：
        @generic(ctypes.c_int, ctypes.c_int)
        def add(a, b):
            return a + b
    """
    def decorator(func: Callable) -> FusedFunction:
        fused_types = []
        for pt in param_types:
            if isinstance(pt, FusedType):
                fused_types.append(pt)
            else:
                # 将单个类型包装为FusedType
                fused_types.append(FusedType(pt))
        return FusedFunction(func, fused_types=tuple(fused_types))
    
    return decorator


# 常用融合类型预设
Numeric = FusedType("int", "float", "double", "long", "long long")
Integer = FusedType("int", "long", "long long", "short")
Floating = FusedType("float", "double", "long double")
AnyType = FusedType(
    "int", "long", "long long", "short",
    "float", "double", "long double",
    "char", "bool"
)


__all__ = [
    'FusedType',
    'FusedFunction',
    'fused',
    'generic',
    'GenericError',
    # 预设融合类型
    'Numeric',
    'Integer',
    'Floating',
    'AnyType',
]
