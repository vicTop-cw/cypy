# SIMD向量

## 向量类型

### 基本语法

Cypy 支持 SIMD 向量类型，使用 `vec[T; N]` 语法声明：

```python
# 向量类型声明
let v: vec[int; 4] = vec![1, 2, 3, 4]
let vf: vec[float; 4] = vec![1.0, 2.0, 3.0, 4.0]
```

### 向量字面量

```python
# 显式元素列表
let v1: vec[int; 4] = vec![1, 2, 3, 4]

# 重复值形式
let zeros: vec[int; 4] = vec![0; 4]  # [0, 0, 0, 0]
let ones: vec[float; 8] = vec![1.0; 8]  # 8个1.0
```

### 映射到 Cython

向量类型在 Cython 中映射为 Python `list`：

```python
# Cypy 源码
let v: vec[int; 4] = vec![1, 2, 3, 4]

# 生成的 Cython 代码
let v: list = [1, 2, 3, 4]
```

## 向量运算

### 基本运算

```python
# 向量加法
let a: Vec3[float] = Vec3(1.0, 2.0, 3.0)
let b: Vec3[float] = Vec3(4.0, 5.0, 6.0)
let c: Vec3[float] = a + b  # (5.0, 7.0, 9.0)

# 向量减法
let d: Vec3[float] = a - b  # (-3.0, -3.0, -3.0)

# 向量乘法（逐元素）
let e: Vec3[float] = a * b  # (4.0, 10.0, 18.0)

# 向量除法（逐元素）
let f: Vec3[float] = b / a  # (4.0, 2.5, 2.0)
```

### 标量运算

```python
# 标量乘法
let v: Vec3[float] = Vec3(1.0, 2.0, 3.0)
let scaled: Vec3[float] = v * 2.0  # (2.0, 4.0, 6.0)

# 标量除法
let divided: Vec3[float] = v / 2.0  # (0.5, 1.0, 1.5)
```

### 向量函数

```python
# 点积
let dot_product: float = a.dot(b)  # 1*4 + 2*5 + 3*6 = 32

# 叉积（仅3D）
let cross_product: Vec3[float] = a.cross(b)

# 长度
let length: float = a.length()  # sqrt(1+4+9) = sqrt(14)

# 归一化
let normalized: Vec3[float] = a.normalize()
```

## 向量变换

### 矩阵乘法

```python
# 向量与矩阵相乘
let v: Vec4[float] = Vec4(1.0, 2.0, 3.0, 1.0)
let m: Mat4[float] = Mat4.identity()
let result: Vec4[float] = m * v
```

### 旋转

```python
# 绕X轴旋转
let rotated: Vec3[float] = v3.rotate_x(45.0)

# 绕Y轴旋转
let rotated: Vec3[float] = v3.rotate_y(45.0)

# 绕Z轴旋转
let rotated: Vec3[float] = v3.rotate_z(45.0)
```

## 向量实现说明

当前版本的向量类型使用普通的 Python 列表操作实现，**未使用 SIMD 指令优化**。向量运算（加法、减法、乘法等）都是逐元素执行的，与 Python 列表操作类似。

SIMD 指令优化是未来的规划特性，目前的实现提供了向量类型的语法和基本运算能力，为后续的性能优化奠定基础。

## 向量特性

| 特性 | 说明 |
|------|------|
| **向量类型** | `Vec2`, `Vec3`, `Vec4` 支持多种数值类型 |
| **基本运算** | `+`, `-`, `*`, `/` 逐元素运算 |
| **标量运算** | 向量与标量的运算 |
| **向量函数** | `dot`, `cross`, `length`, `normalize` |
| **矩阵乘法** | 支持 `Mat4 * Vec4`（当前未实现） |
| **旋转变换** | 支持绕X/Y/Z轴旋转（当前未实现） |
| **SIMD优化** | 规划中，当前未实现 |
| **内存对齐** | 规划中，当前未实现 |