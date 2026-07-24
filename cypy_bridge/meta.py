"""
Cypy Bridge Meta Class Support
实现类似Cython的元类（metaclass）支持，允许在编译时控制类的创建过程。

在Cypy中，meta关键字用于定义元类，类似于Python的metaclass机制。
这允许在类创建时进行额外的处理，如类型检查、属性注入、代码生成等。
"""

import ctypes
from typing import Any, Type, Dict, List, Callable, Tuple
from .core import BridgeError


class MetaError(BridgeError):
    """元类相关错误"""
    pass


class CypyMetaClass(type):
    """Cypy元类基类
    
    这是一个自定义元类，用于在类创建时进行额外的处理。
    可以作为其他元类的基类使用。
    
    示例：
        class MyMeta(CypyMetaClass):
            def __new__(cls, name, bases, attrs):
                # 在类创建前修改属性
                attrs['generated'] = True
                return super().__new__(cls, name, bases, attrs)
        
        class MyClass(metaclass=MyMeta):
            pass
        
        print(MyClass.generated)  # True
    """
    
    def __new__(cls, name: str, bases: Tuple[Type, ...], attrs: Dict[str, Any]) -> Type:
        """创建类对象
        
        参数：
            name: 类名称
            bases: 基类元组
            attrs: 类属性字典
        
        返回：
            新创建的类对象
        """
        # 添加一些默认属性
        attrs.setdefault('__cypy_class__', True)
        attrs.setdefault('__created_at__', __import__('datetime').datetime.now())
        
        return super().__new__(cls, name, bases, attrs)
    
    def __init__(cls, name: str, bases: Tuple[Type, ...], attrs: Dict[str, Any]) -> None:
        """初始化类对象"""
        super().__init__(name, bases, attrs)
    
    def __call__(cls, *args, **kwargs) -> Any:
        """创建实例（可以在这里进行实例创建前的处理）"""
        return super().__call__(*args, **kwargs)


class TypeCheckedMeta(CypyMetaClass):
    """类型检查元类
    
    在类创建时自动添加类型检查功能。
    
    示例：
        class Person(metaclass=TypeCheckedMeta):
            name: str
            age: int
            
            def __init__(self, name: str, age: int):
                self.name = name
                self.age = age
        
        p = Person("Alice", 30)  # OK
        p = Person(30, "Alice")  # TypeError
    """
    
    def __new__(cls, name: str, bases: Tuple[Type, ...], attrs: Dict[str, Any]) -> Type:
        # 检查类型注解
        annotations = attrs.get('__annotations__', {})
        
        # 如果有类型注解，添加类型检查初始化器
        if annotations:
            original_init = attrs.get('__init__')
            
            def type_checked_init(self, *args, **kwargs):
                # 调用原始__init__
                if original_init:
                    original_init(self, *args, **kwargs)
                
                # 检查属性类型
                for attr_name, expected_type in annotations.items():
                    if hasattr(self, attr_name):
                        value = getattr(self, attr_name)
                        if not isinstance(value, expected_type):
                            raise TypeError(
                                f"Attribute '{attr_name}' must be {expected_type.__name__}, "
                                f"got {type(value).__name__}"
                            )
            
            attrs['__init__'] = type_checked_init
        
        return super().__new__(cls, name, bases, attrs)


class AutoSlotsMeta(CypyMetaClass):
    """自动__slots__元类
    
    根据类型注解自动生成__slots__，减少内存开销。
    
    示例：
        class Point(metaclass=AutoSlotsMeta):
            x: int
            y: int
            
            def __init__(self, x: int, y: int):
                self.x = x
                self.y = y
        
        # 自动生成 __slots__ = ('x', 'y')
    """
    
    def __new__(cls, name: str, bases: Tuple[Type, ...], attrs: Dict[str, Any]) -> Type:
        # 如果没有显式定义__slots__，根据类型注解生成
        if '__slots__' not in attrs:
            annotations = attrs.get('__annotations__', {})
            if annotations:
                attrs['__slots__'] = tuple(annotations.keys())
        
        return super().__new__(cls, name, bases, attrs)


class SingletonMeta(CypyMetaClass):
    """单例元类
    
    确保类只有一个实例。
    
    示例：
        class Config(metaclass=SingletonMeta):
            pass
        
        c1 = Config()
        c2 = Config()
        assert c1 is c2  # True
    """
    
    _instances: Dict[Type, Any] = {}
    
    def __call__(cls, *args, **kwargs) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
    
    @classmethod
    def reset(cls, target_class: Type = None) -> None:
        """重置单例实例"""
        if target_class:
            cls._instances.pop(target_class, None)
        else:
            cls._instances.clear()


def meta(cls: Type = None, *, base: Type = CypyMetaClass) -> Callable:
    """meta装饰器（类似Cython的meta关键字）
    
    用于定义元类或为类指定元类。
    
    示例：
        # 方式1：定义元类
        @meta
        class MyMeta:
            def __new__(cls, name, bases, attrs):
                attrs['custom'] = True
                return type(name, bases, attrs)
        
        # 方式2：为类指定元类
        @meta(base=SingletonMeta)
        class MyClass:
            pass
    """
    def decorator(target: Type) -> Type:
        if cls is None:
            # 定义元类：创建一个继承自base的元类
            class NewMeta(base):
                pass
            
            # 复制目标类的方法到元类
            for attr_name, attr_value in vars(target).items():
                if not attr_name.startswith('__') or attr_name in ('__new__', '__init__', '__call__'):
                    setattr(NewMeta, attr_name, attr_value)
            
            return NewMeta
        else:
            # 为类指定元类
            return base(target.__name__, target.__bases__, dict(vars(target)))
    
    if cls is None:
        return decorator
    return decorator(cls)


def cdef_meta(name: str, bases: Tuple[Type, ...] = (), **attrs) -> Type:
    """声明元类（类似Cython的cdef meta语法）
    
    示例：
        MyMeta = cdef_meta('MyMeta', generated=True)
        
        class MyClass(metaclass=MyMeta):
            pass
        
        print(MyClass.generated)  # True
    """
    class NewMeta(CypyMetaClass):
        pass
    
    # 添加属性
    for attr_name, attr_value in attrs.items():
        setattr(NewMeta, attr_name, attr_value)
    
    return NewMeta


__all__ = [
    'CypyMetaClass',
    'TypeCheckedMeta',
    'AutoSlotsMeta',
    'SingletonMeta',
    'meta',
    'cdef_meta',
    'MetaError',
]
