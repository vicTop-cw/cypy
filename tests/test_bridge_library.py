"""
Cypy Bridge Library Test Suite

验证桥接库的核心功能是否正常工作。
"""

import unittest
import ctypes
import tempfile
import os
import sys


class TestBridgeCore(unittest.TestCase):
    """测试核心模块"""
    
    def test_get_platform(self):
        """测试平台检测"""
        from cypy_bridge.core import get_platform
        platform = get_platform()
        self.assertIn(platform, ['windows', 'linux', 'macos'])
    
    def test_get_c_stdlib(self):
        """测试C标准库绑定"""
        from cypy_bridge.core import get_c_stdlib
        c_stdlib = get_c_stdlib()
        self.assertIsNotNone(c_stdlib)
    
    def test_ctype_conversion(self):
        """测试类型转换"""
        from cypy_bridge.core import ctype_to_python, python_to_ctype
        
        # 测试 ctype_to_python
        c_int = ctypes.c_int(42)
        self.assertEqual(ctype_to_python(c_int), 42)
        
        # 测试 python_to_ctype
        result = python_to_ctype(42, ctypes.c_int)
        self.assertIsInstance(result, ctypes.c_int)
        self.assertEqual(result.value, 42)
    
    def test_size_of(self):
        """测试类型大小获取"""
        from cypy_bridge.core import size_of
        self.assertEqual(size_of(ctypes.c_int), ctypes.sizeof(ctypes.c_int))
        self.assertEqual(size_of(ctypes.c_double), ctypes.sizeof(ctypes.c_double))
    
    def test_align_of(self):
        """测试对齐要求获取"""
        from cypy_bridge.core import align_of
        self.assertEqual(align_of(ctypes.c_int), ctypes.alignment(ctypes.c_int))
    
    def test_offset_of(self):
        """测试字段偏移量获取"""
        from cypy_bridge.core import offset_of
        
        class Point(ctypes.Structure):
            _fields_ = [('x', ctypes.c_int), ('y', ctypes.c_int)]
        
        self.assertEqual(offset_of(Point, 'x'), 0)


class TestBridgeTypes(unittest.TestCase):
    """测试类型系统"""
    
    def test_type_mapper(self):
        """测试类型映射器"""
        from cypy_bridge.types import TypeMapper
        
        mapper = TypeMapper()
        self.assertEqual(mapper.to_ctypes('int'), ctypes.c_int)
        self.assertEqual(mapper.to_ctypes('double'), ctypes.c_double)
        self.assertTrue(mapper.is_builtin('int'))
        self.assertFalse(mapper.is_builtin('custom_type'))
    
    def test_cdef(self):
        """测试cdef类型声明"""
        from cypy_bridge.types import cdef
        
        int_type = cdef('int')
        self.assertIsNotNone(int_type)
        self.assertEqual(int_type.ctype, ctypes.c_int)
    
    def test_cdef_array(self):
        """测试cdef数组类型"""
        from cypy_bridge.types import cdef
        
        int_array = cdef('int')[10]
        self.assertIsNotNone(int_array)
    
    def test_declare(self):
        """测试变量声明"""
        from cypy_bridge.types import declare
        
        x = declare('int', 'x', 42)
        self.assertEqual(x.value, 42)
        
        y = declare('double', 'y')
        self.assertEqual(y.value, 0.0)
    
    def test_cpdef_decorator(self):
        """测试cpdef装饰器"""
        from cypy_bridge.types import cpdef
        
        @cpdef
        def add(a, b):
            return a + b
        
        self.assertEqual(add(3, 5), 8)
    
    def test_cpdef_with_types(self):
        """测试带类型声明的cpdef装饰器"""
        from cypy_bridge.types import cpdef
        
        @cpdef(arg_types=(ctypes.c_int, ctypes.c_int), return_type=ctypes.c_int)
        def add_fast(a, b):
            return a + b
        
        self.assertEqual(add_fast(3, 5), 8)
    
    def test_infer_type(self):
        """测试类型推断"""
        from cypy_bridge.types import infer_type
        
        self.assertEqual(infer_type(42), ctypes.c_int)
        self.assertEqual(infer_type(3.14), ctypes.c_double)
        # ctypes.c_bool在某些Python版本中可能不存在，接受c_int作为替代
        bool_type = infer_type(True)
        self.assertIn(bool_type, [ctypes.c_bool, ctypes.c_int])
        self.assertEqual(infer_type(b"hello"), ctypes.c_char_p)
    
    def test_cast(self):
        """测试类型转换"""
        from cypy_bridge.types import cast
        
        # float -> int
        self.assertEqual(cast("int", 3.14), 3)
        # int -> float
        self.assertEqual(cast("float", 42), 42.0)
        # int -> double
        self.assertEqual(cast("double", 42), 42.0)
    
    def test_cast_with_ctypes(self):
        """测试使用ctypes类型进行转换"""
        from cypy_bridge.types import cast
        
        self.assertEqual(cast(ctypes.c_int, 3.14), 3)
        self.assertEqual(cast(ctypes.c_double, 42), 42.0)
    
    def test_ccast(self):
        """测试C风格类型转换"""
        from cypy_bridge.types import ccast
        
        self.assertEqual(ccast(3.14, "int"), 3)
        self.assertEqual(ccast(42, "float"), 42.0)
    
    def test_type_aliases(self):
        """测试类型别名"""
        from cypy_bridge.types import int_, float32_, double_, bool_, str_, void, size_t
        
        self.assertEqual(int_, ctypes.c_int)
        self.assertEqual(float32_, ctypes.c_float)
        self.assertEqual(double_, ctypes.c_double)
        self.assertEqual(bool_, ctypes.c_bool)
        self.assertEqual(size_t, ctypes.c_size_t)


class TestBridgeMemory(unittest.TestCase):
    """测试内存管理"""
    
    def test_malloc_free(self):
        """测试malloc和free"""
        from cypy_bridge.memory import malloc, free
        
        ptr = malloc(100)
        self.assertIsNotNone(ptr)
        free(ptr)
    
    def test_malloc_invalid_size(self):
        """测试malloc无效大小"""
        from cypy_bridge.memory import malloc, MemoryError
        
        with self.assertRaises(MemoryError):
            malloc(0)
        
        with self.assertRaises(MemoryError):
            malloc(-1)
    
    def test_sizeof(self):
        """测试sizeof"""
        from cypy_bridge.memory import sizeof
        
        self.assertEqual(sizeof(ctypes.c_int), ctypes.sizeof(ctypes.c_int))
        
        obj = ctypes.c_int(42)
        self.assertEqual(sizeof(obj), ctypes.sizeof(ctypes.c_int))
    
    def test_calloc(self):
        """测试calloc"""
        from cypy_bridge.memory import calloc, free, memset
        
        ptr = calloc(10, 4)  # 10个int，每个4字节
        self.assertIsNotNone(ptr)
        free(ptr)
    
    def test_realloc(self):
        """测试realloc"""
        from cypy_bridge.memory import malloc, realloc, free
        
        ptr = malloc(100)
        self.assertIsNotNone(ptr)
        
        new_ptr = realloc(ptr, 200)
        self.assertIsNotNone(new_ptr)
        free(new_ptr)
    
    def test_realloc_zero_size(self):
        """测试realloc大小为0"""
        from cypy_bridge.memory import malloc, realloc, free
        
        ptr = malloc(100)
        self.assertIsNotNone(ptr)
        
        result = realloc(ptr, 0)
        self.assertIsNone(result)
    
    def test_memset(self):
        """测试memset"""
        from cypy_bridge.memory import malloc, memset, free
        
        ptr = malloc(10)
        memset(ptr, 0, 10)
        free(ptr)
    
    def test_memcpy(self):
        """测试memcpy"""
        from cypy_bridge.memory import malloc, memcpy, free
        
        src = malloc(10)
        dst = malloc(10)
        memcpy(dst, src, 10)
        free(src)
        free(dst)
    
    def test_memmove(self):
        """测试memmove"""
        from cypy_bridge.memory import malloc, memmove, free
        
        ptr = malloc(20)
        memmove(ptr + 10, ptr, 10)
        free(ptr)
    
    def test_aligned_alloc(self):
        """测试aligned_alloc"""
        from cypy_bridge.memory import aligned_alloc, free
        
        ptr = aligned_alloc(16, 100)
        self.assertIsNotNone(ptr)
        free(ptr)


class TestBridgePointer(unittest.TestCase):
    """测试指针操作"""
    
    def test_pointer_class(self):
        """测试Pointer类"""
        from cypy_bridge.pointer import Pointer
        
        # 创建一个ctypes变量
        val = ctypes.c_int(42)
        ptr = Pointer(ctypes.byref(val), ctypes.c_int)
        
        self.assertIsNotNone(ptr)
        self.assertEqual(ptr.base_type, ctypes.c_int)
    
    def test_pointer_deref(self):
        """测试指针解引用"""
        from cypy_bridge.pointer import Pointer, deref
        
        val = ctypes.c_int(42)
        ptr = Pointer(ctypes.byref(val), ctypes.c_int)
        
        self.assertEqual(deref(ptr), 42)
        self.assertEqual(ptr.deref(), 42)
    
    def test_pointer_assign(self):
        """测试指针赋值"""
        from cypy_bridge.pointer import Pointer
        
        val = ctypes.c_int(42)
        ptr = Pointer(ctypes.byref(val), ctypes.c_int)
        
        ptr.assign(100)
        self.assertEqual(val.value, 100)
    
    def test_pointer_offset(self):
        """测试指针偏移"""
        from cypy_bridge.pointer import Pointer
        
        arr = (ctypes.c_int * 5)(1, 2, 3, 4, 5)
        # 使用POINTER而不是byref来支持地址运算
        ptr = Pointer(ctypes.cast(ctypes.byref(arr), ctypes.POINTER(ctypes.c_int)), ctypes.c_int)
        
        ptr2 = ptr.offset(2)
        self.assertEqual(ptr2.deref(), 3)
    
    def test_pointer_arithmetic(self):
        """测试指针算术"""
        from cypy_bridge.pointer import Pointer
        
        arr = (ctypes.c_int * 5)(1, 2, 3, 4, 5)
        # 使用POINTER而不是byref来支持地址运算
        ptr = Pointer(ctypes.cast(ctypes.byref(arr), ctypes.POINTER(ctypes.c_int)), ctypes.c_int)
        
        self.assertEqual((ptr + 2).deref(), 3)
        self.assertEqual((ptr + 4).deref(), 5)
    
    def test_ptr_function(self):
        """测试ptr函数"""
        from cypy_bridge.pointer import ptr
        
        val = ctypes.c_int(42)
        pointer = ptr(val)
        
        self.assertIsNotNone(pointer)
    
    def test_addr_function(self):
        """测试addr函数"""
        from cypy_bridge.pointer import addr
        
        val = ctypes.c_int(42)
        address = addr(val)
        
        self.assertIsInstance(address, int)
    
    def test_cast_ptr(self):
        """测试指针类型转换"""
        from cypy_bridge.pointer import Pointer, cast_ptr
        
        val = ctypes.c_int(42)
        ptr = Pointer(ctypes.byref(val), ctypes.c_int)
        
        new_ptr = cast_ptr(ptr, ctypes.c_void_p)
        self.assertEqual(new_ptr.base_type, ctypes.c_void_p)
    
    def test_null_ptr(self):
        """测试空指针"""
        from cypy_bridge.pointer import null_ptr, is_null
        
        ptr = null_ptr()
        self.assertTrue(is_null(ptr))
    
    def test_null_ptr_deref(self):
        """测试空指针解引用抛出异常"""
        from cypy_bridge.pointer import null_ptr, PointerError
        
        ptr = null_ptr()
        
        with self.assertRaises(PointerError):
            ptr.deref()


class TestBridgeStruct(unittest.TestCase):
    """测试结构体定义"""
    
    def test_struct_creation(self):
        """测试结构体创建"""
        from cypy_bridge.struct import struct
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        
        self.assertIsNotNone(Point)
        self.assertEqual(Point.name, "Point")
    
    def test_struct_create_instance(self):
        """测试创建结构体实例"""
        from cypy_bridge.struct import struct
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        p = Point.create(x=10, y=20)
        
        self.assertEqual(p.x, 10)
        self.assertEqual(p.y, 20)
    
    def test_struct_size(self):
        """测试结构体大小"""
        from cypy_bridge.struct import struct
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        expected_size = ctypes.sizeof(ctypes.c_int) * 2
        
        self.assertEqual(Point.size, expected_size)
    
    def test_struct_field_offset(self):
        """测试字段偏移量"""
        from cypy_bridge.struct import struct
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        
        self.assertEqual(Point.get_field_offset('x'), 0)
    
    def test_struct_field_type(self):
        """测试字段类型"""
        from cypy_bridge.struct import struct
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        
        self.assertEqual(Point.get_field_type('x'), ctypes.c_int)
    
    def test_sizeof_struct(self):
        """测试sizeof_struct函数"""
        from cypy_bridge.struct import struct, sizeof_struct
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        
        self.assertEqual(sizeof_struct(Point), Point.size)
    
    def test_offset_of_field(self):
        """测试offset_of_field函数"""
        from cypy_bridge.struct import struct, offset_of_field
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        
        self.assertEqual(offset_of_field(Point, 'x'), 0)
    
    def test_pack_unpack_struct(self):
        """测试结构体打包和解包"""
        from cypy_bridge.struct import struct, pack_struct, unpack_struct
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        
        # 创建实例并打包
        p = Point.create(x=100, y=200)
        data = unpack_struct(p)
        
        # 解包回结构体
        p2 = pack_struct(Point, data)
        
        self.assertEqual(p2.x, 100)
        self.assertEqual(p2.y, 200)
    
    def test_struct_invalid_field(self):
        """测试访问不存在的字段"""
        from cypy_bridge.struct import struct, StructError
        
        Point = struct("Point", x=ctypes.c_int, y=ctypes.c_int)
        
        with self.assertRaises(StructError):
            Point.create(z=30)


class TestBridgeDefer(unittest.TestCase):
    """测试Defer资源管理"""
    
    def test_defer_scope(self):
        """测试defer_scope上下文管理器"""
        from cypy_bridge.defer import defer, defer_scope
        
        results = []
        
        with defer_scope():
            defer(results.append, 1)
            defer(results.append, 2)
            defer(results.append, 3)
        
        # 验证LIFO顺序
        self.assertEqual(results, [3, 2, 1])
    
    def test_defer_multiple(self):
        """测试多个defer"""
        from cypy_bridge.defer import defer, defer_scope
        
        count = [0]
        
        def increment():
            count[0] += 1
        
        with defer_scope():
            defer(increment)
            defer(increment)
        
        self.assertEqual(count[0], 2)
    
    def test_defer_exception(self):
        """测试异常情况下defer仍然执行"""
        from cypy_bridge.defer import defer, defer_scope
        
        results = []
        
        try:
            with defer_scope():
                defer(results.append, 1)
                raise ValueError("test exception")
        except ValueError:
            pass
        
        self.assertEqual(results, [1])
    
    def test_defer_guard(self):
        """测试DeferGuard"""
        from cypy_bridge.defer import DeferGuard
        
        guard = DeferGuard()
        results = []
        
        guard.defer(results.append, 1)
        guard.defer(results.append, 2)
        guard.execute()
        
        self.assertEqual(results, [2, 1])
    
    def test_defer_context(self):
        """测试defer_context"""
        from cypy_bridge.defer import defer, defer_context
        
        results = []
        
        with defer_context():
            defer(results.append, 1)
        
        self.assertEqual(results, [1])


class TestBridgeEnum(unittest.TestCase):
    """测试枚举定义"""
    
    def test_cdef_enum(self):
        """测试cdef_enum函数"""
        from cypy_bridge.enum import cdef_enum
        
        Color = cdef_enum('Color', 'RED', 'GREEN', 'BLUE')
        
        self.assertEqual(Color.RED, 0)
        self.assertEqual(Color.GREEN, 1)
        self.assertEqual(Color.BLUE, 2)
    
    def test_cdef_enum_with_values(self):
        """测试带值的枚举定义"""
        from cypy_bridge.enum import cdef_enum
        
        Color = cdef_enum('Color', 'RED', 'GREEN', BLUE=5)
        
        self.assertEqual(Color.RED, 0)
        self.assertEqual(Color.GREEN, 1)
        self.assertEqual(Color.BLUE, 5)
    
    def test_enum_function(self):
        """测试enum函数"""
        from cypy_bridge.enum import enum
        
        Color = enum('Color', RED=0, GREEN=1, BLUE=2)
        
        self.assertEqual(Color.RED, 0)
        self.assertEqual(Color.GREEN, 1)
        self.assertEqual(Color.BLUE, 2)
    
    def test_enum_access(self):
        """测试枚举成员访问"""
        from cypy_bridge.enum import cdef_enum
        
        Color = cdef_enum('Color', 'RED', 'GREEN', 'BLUE')
        
        # 属性访问
        self.assertEqual(Color.RED, 0)
        # 索引访问
        self.assertEqual(Color['GREEN'], 1)
    
    def test_enum_name_of(self):
        """测试name_of方法"""
        from cypy_bridge.enum import cdef_enum
        
        Color = cdef_enum('Color', 'RED', 'GREEN', 'BLUE')
        
        self.assertEqual(Color.name_of(0), 'RED')
        self.assertEqual(Color.name_of(2), 'BLUE')
        self.assertIsNone(Color.name_of(10))
    
    def test_enum_contains(self):
        """测试in操作符"""
        from cypy_bridge.enum import cdef_enum
        
        Color = cdef_enum('Color', 'RED', 'GREEN', 'BLUE')
        
        self.assertTrue(0 in Color)
        self.assertTrue(2 in Color)
        self.assertFalse(10 in Color)
    
    def test_enum_value(self):
        """测试enum_value函数"""
        from cypy_bridge.enum import cdef_enum, enum_value, EnumError
        
        Color = cdef_enum('Color', 'RED', 'GREEN', 'BLUE')
        
        self.assertEqual(enum_value(Color, 0), 0)
        
        with self.assertRaises(EnumError):
            enum_value(Color, 10)
    
    def test_cenum_properties(self):
        """测试CEnum属性"""
        from cypy_bridge.enum import cdef_enum
        
        Color = cdef_enum('Color', 'RED', 'GREEN', 'BLUE')
        
        self.assertEqual(Color.name, 'Color')
        self.assertIsInstance(Color.variants, dict)
        self.assertEqual(Color.ctype, ctypes.c_int)


class TestBridgeUnion(unittest.TestCase):
    """测试联合类型"""
    
    def test_cdef_union_creation(self):
        """测试创建联合类型"""
        from cypy_bridge.union import cdef_union
        
        u = cdef_union("int", "float")
        self.assertIsInstance(u, type(u))
        self.assertEqual(len(u.member_types), 2)
    
    def test_union_creation(self):
        """测试union函数"""
        from cypy_bridge.union import union
        
        u = union(ctypes.c_int, ctypes.c_float)
        self.assertIsInstance(u, type(u))
    
    def test_union_size(self):
        """测试联合大小（取最大成员）"""
        from cypy_bridge.union import cdef_union
        
        u = cdef_union("int", "double")
        # double比int大，所以联合大小应该等于double的大小
        self.assertEqual(u.size, ctypes.sizeof(ctypes.c_double))
    
    def test_union_set_get_value(self):
        """测试设置和获取值"""
        from cypy_bridge.union import cdef_union
        
        u = cdef_union("int", "float")
        
        # 设置int值
        u.value = 42
        self.assertEqual(u.value, 42)
        
        # 设置float值（c_float是单精度，会有精度损失）
        u.value = 3.14
        # 使用近似比较，因为c_float是单精度浮点数
        self.assertAlmostEqual(u.value, 3.14, places=5)
    
    def test_union_set_value_with_type(self):
        """测试指定类型设置值"""
        from cypy_bridge.union import cdef_union
        
        u = cdef_union("int", "float")
        
        # 指定类型索引0（int）
        u.set_value(100, 0)
        self.assertEqual(u.get_value_as(0), 100)
        
        # 指定类型索引1（float）
        u.set_value(2.5, 1)
        self.assertEqual(u.get_value_as(1), 2.5)
    
    def test_union_invalid_type_index(self):
        """测试无效类型索引"""
        from cypy_bridge.union import cdef_union, UnionTypeError
        
        u = cdef_union("int", "float")
        
        with self.assertRaises(UnionTypeError):
            u.set_value(42, 5)
        
        with self.assertRaises(UnionTypeError):
            u.get_value_as(-1)
    
    def test_union_invalid_value(self):
        """测试无效值"""
        from cypy_bridge.union import cdef_union, UnionTypeError
        
        u = cdef_union("int", "float")
        
        with self.assertRaises(UnionTypeError):
            u.value = "not a number"
    
    def test_union_active_type(self):
        """测试活跃类型"""
        from cypy_bridge.union import cdef_union
        
        u = cdef_union("int", "float")
        
        u.value = 42
        self.assertEqual(u.active_type, ctypes.c_int)
        
        u.value = 3.14
        self.assertEqual(u.active_type, ctypes.c_float)


class TestBridgeGenerics(unittest.TestCase):
    """测试泛型/融合类型"""
    
    def test_fused_type_creation(self):
        """测试创建融合类型"""
        from cypy_bridge.generics import FusedType
        
        ft = FusedType("int", "float", "double")
        self.assertEqual(len(ft.types), 3)
        self.assertEqual(len(ft.type_names), 3)
    
    def test_fused_type_resolve(self):
        """测试融合类型解析"""
        from cypy_bridge.generics import FusedType
        
        ft = FusedType("int", "float", "double")
        
        # 解析int值
        self.assertEqual(ft.resolve(42), ctypes.c_int)
        
        # 解析float值
        self.assertEqual(ft.resolve(3.14), ctypes.c_double)
    
    def test_fused_function(self):
        """测试融合函数"""
        from cypy_bridge.generics import FusedType, fused
        
        Numeric = FusedType("int", "float", "double")
        
        @fused(Numeric)
        def add(a, b):
            return a.value + b.value
        
        result = add(3, 5)
        self.assertIsInstance(result, int)
    
    def test_generic_decorator(self):
        """测试泛型装饰器"""
        from cypy_bridge.generics import generic
        
        @generic(ctypes.c_int, ctypes.c_int)
        def add(a, b):
            return a.value + b.value
        
        result = add(3, 5)
        self.assertIsInstance(result, int)
    
    def test_preset_fused_types(self):
        """测试预设融合类型"""
        from cypy_bridge.generics import Numeric, Integer, Floating, AnyType
        
        self.assertIsNotNone(Numeric)
        self.assertIsNotNone(Integer)
        self.assertIsNotNone(Floating)
        self.assertIsNotNone(AnyType)


class TestBridgeMeta(unittest.TestCase):
    """测试元类支持"""
    
    def test_cypy_meta_class(self):
        """测试CypyMetaClass"""
        from cypy_bridge.meta import CypyMetaClass
        
        class MyMeta(CypyMetaClass):
            def __new__(cls, name, bases, attrs):
                attrs['generated'] = True
                return super().__new__(cls, name, bases, attrs)
        
        class MyClass(metaclass=MyMeta):
            pass
        
        self.assertTrue(MyClass.generated)
        self.assertTrue(hasattr(MyClass, '__cypy_class__'))
    
    def test_type_checked_meta(self):
        """测试TypeCheckedMeta"""
        from cypy_bridge.meta import TypeCheckedMeta
        
        class Person(metaclass=TypeCheckedMeta):
            name: str
            age: int
            
            def __init__(self, name: str, age: int):
                self.name = name
                self.age = age
        
        # 正确类型
        p = Person("Alice", 30)
        self.assertEqual(p.name, "Alice")
        
        # 类型错误（需要在__init__后检查）
        with self.assertRaises(TypeError):
            class BadPerson(metaclass=TypeCheckedMeta):
                name: str
                
                def __init__(self):
                    self.name = 123  # 错误类型
            
            BadPerson()
    
    def test_auto_slots_meta(self):
        """测试AutoSlotsMeta"""
        from cypy_bridge.meta import AutoSlotsMeta
        
        class Point(metaclass=AutoSlotsMeta):
            x: int
            y: int
            
            def __init__(self, x: int, y: int):
                self.x = x
                self.y = y
        
        # 应该自动生成__slots__
        self.assertTrue(hasattr(Point, '__slots__'))
        self.assertEqual(Point.__slots__, ('x', 'y'))
    
    def test_singleton_meta(self):
        """测试SingletonMeta"""
        from cypy_bridge.meta import SingletonMeta
        
        class Config(metaclass=SingletonMeta):
            pass
        
        c1 = Config()
        c2 = Config()
        self.assertIs(c1, c2)
    
    def test_meta_decorator(self):
        """测试meta装饰器"""
        from cypy_bridge.meta import meta
        
        @meta
        class MyMeta:
            def __new__(cls, name, bases, attrs):
                attrs['custom'] = True
                return type(name, bases, attrs)
        
        class MyClass(metaclass=MyMeta):
            pass
        
        self.assertTrue(MyClass.custom)
    
    def test_cdef_meta(self):
        """测试cdef_meta函数"""
        from cypy_bridge.meta import cdef_meta
        
        MyMeta = cdef_meta('MyMeta', generated=True)
        
        class MyClass(metaclass=MyMeta):
            pass
        
        self.assertTrue(MyClass.generated)


class TestBridgeNoGil(unittest.TestCase):
    """测试nogil特性"""
    
    def test_gil_state(self):
        """测试GilState"""
        from cypy_bridge.nogil import GilState
        
        state = GilState()
        self.assertFalse(state.released)
        
        state.release()
        self.assertTrue(state.released)
        
        state.acquire()
        self.assertFalse(state.released)
    
    def test_nogil_context(self):
        """测试nogil上下文管理器"""
        from cypy_bridge.nogil import nogil
        
        with nogil:
            # 在nogil区域内执行
            result = 3 + 5
        
        self.assertEqual(result, 8)
    
    def test_nogil_decorator(self):
        """测试nogil装饰器"""
        from cypy_bridge.nogil import nogil
        
        @nogil
        def compute():
            return 3 + 5
        
        result = compute()
        self.assertEqual(result, 8)
    
    def test_nogil_exec(self):
        """测试nogil_exec函数"""
        from cypy_bridge.nogil import nogil_exec
        
        def compute():
            return 3 + 5
        
        result = nogil_exec(compute)
        self.assertEqual(result, 8)
    
    def test_nogil_pool(self):
        """测试nogil_pool线程池"""
        from cypy_bridge.nogil import nogil_pool
        
        def compute(x):
            return x * x
        
        with nogil_pool(max_workers=2) as pool:
            results = list(pool.map(compute, [1, 2, 3, 4]))
        
        self.assertEqual(results, [1, 4, 9, 16])
    
    def test_nogil_parallel(self):
        """测试nogil_parallel并行执行"""
        from cypy_bridge.nogil import nogil_parallel
        
        def compute(x):
            return x * x
        
        results = nogil_parallel(compute, [(1,), (2,), (3,), (4,)])
        self.assertEqual(results, [1, 4, 9, 16])


class TestBridgeCompiler(unittest.TestCase):
    """测试编译API"""
    
    def test_compile_result(self):
        """测试CompileResult"""
        from cypy_bridge.compiler import CompileResult
        
        result = CompileResult(success=True, output_path="/path/to/module.pyd")
        self.assertTrue(result)
        
        result2 = CompileResult(success=False, error="compile failed")
        self.assertFalse(result2)
    
    def test_bridge_compiler_init(self):
        """测试BridgeCompiler初始化"""
        from cypy_bridge.compiler import BridgeCompiler
        
        compiler = BridgeCompiler()
        self.assertIsNotNone(compiler)
    
    def test_compile_code(self):
        """测试compile_code函数"""
        from cypy_bridge.compiler import compile_code, CompileResult
        
        result = compile_code("def foo(): return 42")
        # 编译可能因缺少编译器而失败，但不应抛出异常
        self.assertIsInstance(result, CompileResult)
    
    def test_compile_module(self):
        """测试compile_module函数"""
        from cypy_bridge.compiler import compile_module
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cypy', delete=False) as f:
            f.write("def foo(): return 42")
            temp_file = f.name
        
        try:
            result = compile_module(temp_file)
            self.assertIsNotNone(result)
        finally:
            os.unlink(temp_file)


class TestBridgeImport(unittest.TestCase):
    """测试模块导入"""
    
    def test_import_all(self):
        """测试导入所有API"""
        from cypy_bridge import (
            TypeMapper, cdef, cpdef,
            int_, float32_, double_, bool_, str_, void, size_t,
            malloc, free, sizeof, aligned_alloc,
            Pointer, ptr, deref, addr,
            Struct, struct,
            defer, DeferManager,
            CEnum, enum, cdef_enum, enum_value,
            compile_module, compile_code, BridgeCompiler, CompileResult,
            __version__
        )
        
        self.assertEqual(__version__, '0.1.0')
    
    def test_import_submodules(self):
        """测试导入子模块"""
        import cypy_bridge.types
        import cypy_bridge.memory
        import cypy_bridge.pointer
        import cypy_bridge.struct
        import cypy_bridge.defer
        import cypy_bridge.enum
        import cypy_bridge.compiler
        import cypy_bridge.core
        
        self.assertIsNotNone(cypy_bridge.types)
        self.assertIsNotNone(cypy_bridge.memory)
        self.assertIsNotNone(cypy_bridge.pointer)
        self.assertIsNotNone(cypy_bridge.struct)
        self.assertIsNotNone(cypy_bridge.defer)
        self.assertIsNotNone(cypy_bridge.enum)
        self.assertIsNotNone(cypy_bridge.compiler)
        self.assertIsNotNone(cypy_bridge.core)


class TestBridgeRegressionT0r61(unittest.TestCase):
    """OMEGA T0r61.3.2 永久回归用例
    
    对应 Find_BUG/audit_2026q3/repro_runtime_01..09.py 的 9 个运行时/桥接缺陷，
    每个用例都锁定"修复前的可观测错误行为"，防止回归。
    """
    
    # ---------- 缺陷 1：pointer.py Owned/ptr ----------
    def test_owned_accepts_non_weakrefable_values(self):
        """Owned 必须能吃下 int/float/str/tuple/list/dict/bool/None（旧实现抛 TypeError）"""
        from cypy_bridge.pointer import Owned
        
        for value in (5, 3.14, "text", (1, 2), [1], {1: 2}, True, None):
            owned = Owned(value)
            self.assertTrue(owned.is_valid, repr(value))
            self.assertEqual(owned.take(), value)
            self.assertFalse(owned.is_valid)
    
    def test_owned_accepts_temporary_ctypes_object(self):
        """Owned(ctypes.c_int(42)) 不能是静默的 NULL 句柄"""
        from cypy_bridge.pointer import Owned
        
        owned = Owned(ctypes.c_int(42))
        self.assertTrue(owned.is_valid, repr(owned))
        self.assertEqual(owned.take().value, 42)
    
    def test_owned_keeps_real_weakref_semantics(self):
        """可弱引用对象仍然走弱引用：原对象销毁后 Owned 失效"""
        import gc
        
        from cypy_bridge.pointer import Owned
        
        class Holder:
            def __init__(self, data):
                self.data = data
        
        obj = Holder(7)
        owned = Owned(obj)
        self.assertTrue(owned.is_valid)
        del obj
        gc.collect()
        self.assertFalse(owned.is_valid)
    
    def test_ptr_resolves_base_type_to_ctypes_type(self):
        """ptr() 的 base_type 必须是 ctypes 类型，而不是 _type_ 里的单字符字符串"""
        from cypy_bridge.pointer import ptr
        
        p = ptr(ctypes.c_int(42))
        self.assertIsNotNone(p)
        self.assertIsInstance(p.base_type, type)
        ctypes.sizeof(p.base_type)  # 不抛 "this type has no size"
        self.assertEqual(p.deref(), 42)
        self.assertEqual(p.offset(1).base_type, p.base_type)
    
    def test_ptr_on_plain_python_int(self):
        """ptr(5) 不能抛 PointerError，且能读回 5"""
        from cypy_bridge.pointer import ptr
        
        p = ptr(5)
        self.assertEqual(p.deref(), 5)
        p.assign(6)
        self.assertEqual(p.deref(), 6)
    
    def test_byref_based_pointer_supports_address_arithmetic(self):
        """byref() 构造的 Pointer 也必须能算自己的地址（offset/__eq__/__repr__）"""
        from cypy_bridge.pointer import Pointer
        
        arr = (ctypes.c_int * 4)(10, 20, 30, 40)
        p = Pointer(ctypes.byref(arr), ctypes.c_int)
        self.assertEqual(p.deref(), 10)
        self.assertEqual((p + 1).deref(), 20)
        self.assertIn("Pointer(", repr(p))
        self.assertEqual(p, Pointer(ctypes.byref(arr), ctypes.c_int))
    
    def test_pointer_is_hashable(self):
        """__eq__ 定义后必须仍有 __hash__，否则 Pointer 不能当 dict 键"""
        from cypy_bridge.pointer import Pointer
        
        self.assertIsNotNone(Pointer.__hash__)
        table = {Pointer(ctypes.c_void_p(1), ctypes.c_int): "x"}
        self.assertEqual(table[Pointer(ctypes.c_void_p(1), ctypes.c_int)], "x")
    
    # ---------- 缺陷 2：defer.py 共享栈 ----------
    def test_nested_defer_context_does_not_steal_outer_defers(self):
        """内层作用域只能执行自己登记的 defer"""
        from cypy_bridge.defer import DeferManager, defer, defer_context
        
        manager = DeferManager.get_instance()
        manager.clear()
        events = []
        try:
            with defer_context():
                defer(events.append, "OUTER")
                with defer_context():
                    defer(events.append, "INNER")
                self.assertEqual(events, ["INNER"])
                self.assertEqual(manager.count, 1)
            self.assertEqual(events, ["INNER", "OUTER"])
        finally:
            manager.clear()
    
    def test_nested_defer_context_keeps_resource_open(self):
        """外层打开的资源不能被内层的 defer 提前关掉（use-after-close）"""
        import io
        import os
        import tempfile
        
        from cypy_bridge.defer import DeferManager, defer, defer_context
        
        manager = DeferManager.get_instance()
        manager.clear()
        fd, path = tempfile.mkstemp(suffix=".defer")
        os.close(fd)
        try:
            with defer_context():
                fh = open(path, "w")
                defer(fh.close)
                with defer_context():
                    defer(lambda: None)
                fh.write("still-open\n")  # 修复前：ValueError: I/O operation on closed file
                self.assertIsInstance(fh, io.IOBase)
            self.assertTrue(fh.closed)
            with open(path) as check:
                self.assertEqual(check.read(), "still-open\n")
        finally:
            manager.clear()
            os.unlink(path)
    
    def test_nested_defer_scope_isolated(self):
        """defer_scope 同样按子栈执行"""
        from cypy_bridge.defer import DeferManager, defer, defer_scope
        
        manager = DeferManager.get_instance()
        manager.clear()
        seq = []
        try:
            with defer_scope():
                defer(seq.append, "outer")
                with defer_scope():
                    defer(seq.append, "inner")
                self.assertEqual(seq, ["inner"])
                seq.append("outer-body-done")
            self.assertEqual(seq, ["inner", "outer-body-done", "outer"])
        finally:
            manager.clear()
    
    def test_execute_defers_still_drains_everything(self):
        """execute_all()/execute_defers() 的整体排空语义不变"""
        from cypy_bridge.defer import DeferManager, defer, execute_defers
        
        manager = DeferManager.get_instance()
        manager.clear()
        got = []
        defer(got.append, 1)
        defer(got.append, 2)
        execute_defers()
        self.assertEqual(got, [2, 1])
        self.assertEqual(manager.count, 0)
    
    # ---------- 缺陷 3：nogil.py 单例状态被覆盖 ----------
    def test_nogil_is_reentrant(self):
        """嵌套 with nogil / @nogil / nogil_exec 都不再抛 NoGilError"""
        from cypy_bridge.nogil import NoGilContext, nogil, nogil_exec
        
        with nogil:
            with nogil:
                pass
            self.assertTrue(nogil._state.released)  # 外层仍然处于释放状态
        self.assertIsNone(nogil._state)
        
        @nogil
        def double(x):
            return x * 2
        
        with nogil:
            self.assertEqual(double(21), 42)
            self.assertEqual(nogil_exec(lambda: 7), 7)
        
        with nogil:
            with nogil:
                with nogil:
                    pass
        
        self.assertIsNone(NoGilContext()._state)
    
    def test_nogil_does_not_mask_user_exception(self):
        """nogil 区域内抛出的异常必须原样传播，不被 NoGilError 顶掉"""
        from cypy_bridge.nogil import nogil
        
        with self.assertRaises(ValueError):
            with nogil:
                with nogil:
                    raise ValueError("user error")
        self.assertIsNone(nogil._state)
    
    # ---------- 缺陷 6：meta.py 分派反了 ----------
    def test_meta_bare_form_defines_a_metaclass(self):
        """@meta class M 必须得到一个真正的元类（旧实现给的是普通类）"""
        from cypy_bridge.meta import meta
        
        @meta
        class MyMeta:
            def __new__(cls, name, bases, attrs):
                attrs['custom'] = True
                return type(name, bases, attrs)
        
        self.assertTrue(issubclass(MyMeta, type))
        
        class UsesMeta(metaclass=MyMeta):
            pass
        
        # 这条不变量在修复前"碰巧"成立，修复后必须仍然成立
        self.assertTrue(UsesMeta.custom)
    
    def test_meta_marker_form_usable_as_metaclass(self):
        """没有自定义 __new__ 的 @meta 定义体也能直接当 metaclass 用"""
        from cypy_bridge.meta import meta
        
        @meta
        class MarkerOnly:
            pass
        
        self.assertTrue(issubclass(MarkerOnly, type))
        
        class UsesMarker(metaclass=MarkerOnly):
            pass
        
        self.assertIs(type(UsesMarker), MarkerOnly)
    
    def test_meta_base_form_assigns_metaclass_and_keeps_identity(self):
        """@meta(base=X) class C 给 C 装上元类 X，而不是把 C 换成元类"""
        from cypy_bridge.meta import SingletonMeta, meta
        
        @meta(base=SingletonMeta)
        class Config:
            x = 1
        
        self.assertIs(type(Config), SingletonMeta)
        self.assertEqual(Config.__name__, "Config")
        self.assertEqual(Config.x, 1)
        self.assertFalse(issubclass(Config, type))
        self.assertIs(Config(), Config())
    
    def test_meta_positional_form_does_not_lose_base(self):
        """meta(SomeMeta) 不能再把调用方的元类换成默认 CypyMetaClass"""
        from cypy_bridge.meta import SingletonMeta, meta
        
        result = meta(SingletonMeta)
        self.assertTrue(type(result) is SingletonMeta
                        or issubclass(type(result), SingletonMeta))
        # 位置参数是普通类时等价于 @meta：得到元类
        class Body:
            pass
        
        self.assertTrue(issubclass(meta(Body), type))
    
    # ---------- 缺陷 7：memory.aligned_alloc ----------
    def test_aligned_alloc_rejects_zero_alignment(self):
        """alignment=0 通过 (0 & -1) 的检查并让 malloc(size-1) 少分配一字节"""
        from cypy_bridge.core import MemoryError as BridgeMemoryError
        from cypy_bridge.memory import aligned_alloc
        
        with self.assertRaises(BridgeMemoryError):
            aligned_alloc(0, 64)
        with self.assertRaises(BridgeMemoryError):
            aligned_alloc(0, 1)
    
    def test_aligned_alloc_actually_aligns_and_is_freeable(self):
        """返回地址必须真的按 alignment 对齐，并且能被 free() 正确释放"""
        from cypy_bridge.memory import aligned_alloc, free
        from cypy_bridge.memory import aligned_block_count
        
        before = aligned_block_count()
        for alignment in (16, 32, 64, 128, 256, 1024):
            pointers = [aligned_alloc(alignment, alignment * 2) for _ in range(8)]
            for p in pointers:
                self.assertEqual(p % alignment, 0, "alignment=%d addr=%r" % (alignment, p))
            for p in pointers:
                free(p)  # 内部换算回 malloc 的原始地址，不能把中间指针交给CRT
        self.assertEqual(aligned_block_count(), before)
    
    def test_aligned_alloc_rejects_negative_and_non_power_of_two(self):
        """负数与非2的幂对齐继续被拒绝（修复前后都该如此）"""
        from cypy_bridge.core import MemoryError as BridgeMemoryError
        from cypy_bridge.memory import aligned_alloc
        
        for bad in (-16, -1, 3, 12, 100):
            with self.assertRaises(BridgeMemoryError):
                aligned_alloc(bad, 64)
    
    # ---------- 缺陷 9：memory NULL 守卫 + 注解 ----------
    def test_memory_ops_reject_null(self):
        """memmove/memcpy/memset 收到 NULL 必须在调用C库之前报错（旧实现直接崩）"""
        from cypy_bridge.core import MemoryError as BridgeMemoryError
        from cypy_bridge.memory import memcpy, memmove, memset
        
        null = ctypes.c_void_p(None)
        with self.assertRaises(BridgeMemoryError):
            memmove(null, null, 8)
        with self.assertRaises(BridgeMemoryError):
            memcpy(null, null, 8)
        with self.assertRaises(BridgeMemoryError):
            memset(null, 0, 8)
        with self.assertRaises(BridgeMemoryError):
            memset(None, 0, 8)
        with self.assertRaises(BridgeMemoryError):
            memset(0, 0, 8)
    
    def test_mem_ops_accept_malloc_result_types(self):
        """指针归一化要同时接受 int / c_void_p / byref()，且数据真的被搬动"""
        from cypy_bridge.memory import free, malloc, memmove
        
        dst = malloc(16)
        payload = ctypes.create_string_buffer(b"01234567", 8)
        # 三种指针表示混用：int 地址、c_void_p、byref() 的 CArgObject
        memmove(ctypes.c_void_p(dst), ctypes.byref(payload), 8)
        self.assertEqual(ctypes.string_at(dst, 8), b"01234567")
        memmove(dst, ctypes.c_void_p(dst), 8)
        self.assertEqual(ctypes.string_at(dst, 8), b"01234567")
        free(dst)
    
    def test_memory_annotations_match_return_values(self):
        """malloc/calloc/aligned_alloc 的返回类型注解不能再撒谎"""
        import typing
        
        from cypy_bridge.memory import aligned_alloc, calloc, free, malloc
        
        cases = (
            (malloc, malloc(16)),
            (calloc, calloc(2, 8)),
            (aligned_alloc, aligned_alloc(16, 16)),
        )
        for func, returned in cases:
            self.assertIs(typing.get_type_hints(func).get("return"), type(returned),
                          "%s() annotation lies about %s" % (func.__name__, type(returned)))
            self.assertIsInstance(returned, int)
            free(returned)
    
    # ---------- 缺陷 8：union 越界静默回绕 ----------
    def test_union_widens_instead_of_wrapping(self):
        """装不下的整数要提升到能装的成员，而不是被 ctypes 截断"""
        from cypy_bridge.union import CUnion, cdef_union
        
        u = cdef_union("unsigned char", "float")
        for value in (300, -1, 256, 999999):
            u.value = value
            self.assertEqual(u.value, value, "value=%d -> %r" % (value, u.value))
        
        v = CUnion(ctypes.c_byte, ctypes.c_double)
        v.value = 200
        self.assertEqual(v.value, 200)
    
    def test_union_rejects_value_that_no_member_can_hold(self):
        """显式指定索引时不放宽：越界值直接 UnionTypeError"""
        from cypy_bridge.union import UnionTypeError, cdef_union
        
        u = cdef_union("unsigned char", "float")
        with self.assertRaises(UnionTypeError):
            u.set_value(777, 0)
        with self.assertRaises(UnionTypeError):
            u.value = "not a number"
    
    def test_union_valid_values_still_map(self):
        """合法用法保持不变：42->c_int、3.14->c_float（tests/test_bridge_library 既有钉）"""
        from cypy_bridge.union import cdef_union
        
        u = cdef_union("int", "float")
        u.value = 42
        self.assertEqual(u.value, 42)
        self.assertIs(u.active_type, ctypes.c_int)
        u.value = 3.14
        self.assertAlmostEqual(u.value, 3.14, places=5)
        self.assertIs(u.active_type, ctypes.c_float)
    
    # ---------- 缺陷 9：types.to_ctypes ----------
    def test_to_ctypes_rejects_unsupported_types(self):
        """未知类型不能静默降级成 py_object"""
        from cypy_bridge.core import TypeConversionError
        from cypy_bridge.types import cast, cdef, declare, _type_mapper
        
        for name in ("int128", "uint128", "float16", "wchar_t", "long long *",
                     "char[10]", "no_such_type"):
            self.assertFalse(_type_mapper.is_builtin(name), name)
            with self.assertRaises(TypeConversionError, msg=name):
                _type_mapper.to_ctypes(name)
            with self.assertRaises(TypeConversionError, msg=name):
                declare(name, "x", 5)
            with self.assertRaises(TypeConversionError, msg=name):
                cdef(name)
            with self.assertRaises(TypeConversionError, msg=name):
                cast(name, 9.7)
    
    def test_to_ctypes_aliases_still_map(self):
        """补齐的别名（无空格指针、ctypes 类型码）不能变成错误"""
        from cypy_bridge.types import _type_mapper
        
        self.assertIs(_type_mapper.to_ctypes("void*"), ctypes.c_void_p)
        self.assertIs(_type_mapper.to_ctypes("void *"), ctypes.c_void_p)
        self.assertIs(_type_mapper.to_ctypes("double"), ctypes.c_double)
        self.assertIs(_type_mapper.to_ctypes("l"), ctypes.c_long)
        self.assertIs(_type_mapper.to_ctypes("int"), ctypes.c_int)
        self.assertFalse(_type_mapper.is_builtin("int128"))
    
    def test_package_union_name_is_the_submodule(self):
        """cypy_bridge.union 必须是子模块，不能被同名函数遮蔽"""
        import types as pytypes
        
        import cypy_bridge
        
        self.assertIsInstance(cypy_bridge.union, pytypes.ModuleType)
        self.assertTrue(callable(cypy_bridge.union.union))
        self.assertTrue(callable(cypy_bridge.union.cdef_union))
    
    def test_ptr_type_name_and_base_type_resolve(self):
        """ptr(obj, type_name=...) 走 to_ctypes，未知类型要报错而不是 py_object"""
        from cypy_bridge.core import PointerError
        from cypy_bridge.pointer import ptr
        
        holder = ctypes.c_int(9)
        self.assertEqual(ptr(holder, "int").deref(), 9)
        with self.assertRaises(PointerError):
            ptr(holder, "int128")


if __name__ == '__main__':
    unittest.main()
