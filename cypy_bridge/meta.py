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
        """初始化类对象
        
        注意：当被创建的类本身就是一个 Cypy 元类（cls 是 CypyMetaClass 的子类，
        例如 meta(SingletonMeta) 这种"把元类再实例化一次"的自应用场景）时，
        零参数 super() 会走"类属性查找"，把 type.__init__ 取成**未绑定**的描述符，
        于是第一个位置参数 name（一个 str）被当成 self，报
        "descriptor '__init__' requires a 'type' object but received a 'str'"。
        这种情况下解释器已经用 type.__new__ 把类型建好，跳过这次空初始化即可。
        """
        if issubclass(cls, CypyMetaClass):
            return
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


# 从 vars(类) 复制命名空间时必须丢掉的描述符：它们是解释器为被装饰类自己生成的
# __dict__/__weakref__ 槽位描述符，塞进新类会得到
# "TypeError: __dict__ slot disallowed: we already got one"。
_SLOT_DESCRIPTORS = ('__dict__', '__weakref__')


def _class_namespace(target: Type) -> Dict[str, Any]:
    """复制一个类的命名空间（丢掉实例槽位描述符）"""
    return {k: v for k, v in vars(target).items() if k not in _SLOT_DESCRIPTORS}


def _build_metaclass(body: Type, base: Type) -> Type:
    """形式1：把 `body` 当作元类的"定义体"，造出一个真正的元类
    
    结果类继承自 `base`（默认 CypyMetaClass，是 type 的子类），所以
    `issubclass(结果, type)` 为 True，可以直接写 `class C(metaclass=结果)`；
    body 里自定义的 __new__/__init__/__call__ 也会被带走。
    """
    return type(body.__name__, (base,), _class_namespace(body))


def _apply_metaclass(target: Type, metaclass: Type) -> Type:
    """形式2：给 `target` 指定元类，保持类名/基类/属性不变
    
    结果仍然是一个"普通类"（不是元类），可以正常实例化。
    """
    return metaclass(target.__name__, target.__bases__, _class_namespace(target))


def _is_metaclass(candidate: Any) -> bool:
    """candidate 本身是否已经是一个元类（type 的子类）"""
    return isinstance(candidate, type) and issubclass(candidate, type)


def meta(cls: Type = None, *, base: Type = CypyMetaClass) -> Callable:
    """meta装饰器（类似Cython的meta关键字）
    
    三种形式（与文档一致，靠"目标是不是元类"来分派，而不是靠 cls is None）：
    
        # 形式1：定义元类（被装饰的是一个普通类，把它当成元类定义体）
        @meta
        class MyMeta:
            def __new__(cls, name, bases, attrs):
                attrs['custom'] = True
                return type(name, bases, attrs)
        # issubclass(MyMeta, type) 为 True，可用于 class C(metaclass=MyMeta)
        
        # 形式2：为类指定元类（显式给出 base=）
        @meta(base=SingletonMeta)
        class MyClass:
            pass
        # type(MyClass) is SingletonMeta，MyClass 仍可正常实例化
        
        # 形式3：位置参数直接调用
        meta(SingletonMeta)   # 传进来的已经是元类 -> 把它作为元类应用
        meta(SomeClass)       # 传进来的是普通类 -> 按形式1造元类
    """
    if cls is None:
        # 形式2：@meta / @meta(base=X) —— 返回装饰器，把 base 装成目标类的元类
        def decorator(target: Type) -> Type:
            return _apply_metaclass(target, base if _is_metaclass(base) else CypyMetaClass)
        return decorator
    
    if _is_metaclass(cls):
        # 形式3的"传进来的已经是元类"：它自己就是要安装的元类，
        # 再把它当元类定义体去包装就等于丢掉调用方给的元类
        return _apply_metaclass(cls, cls)
    
    # 形式1：@meta class M / meta(SomeClass) —— 把目标当作元类定义体
    return _build_metaclass(cls, base if _is_metaclass(base) else CypyMetaClass)


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
