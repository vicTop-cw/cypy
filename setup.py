from setuptools import setup, find_packages

setup(
    name="cypyc",
    version="0.1.0",
    description="Cypy compiler - A Python-like language that compiles to Cython",
    long_description=open("README.md", encoding="utf-8").read() if __file__.endswith(".py") else "",
    author="Cypy Team",
    author_email="dev@cypy.dev",
    url="https://github.com/cypy-lang/cypyc",
    packages=find_packages(exclude=["tests", "examples"]),
    entry_points={
        "console_scripts": [
            "cypyc=cypyc.cli:main",
            "cypy-hook=cypy_hook.hook:main",
        ],
    },
    python_requires=">=3.9",
    install_requires=[
        "Cython>=3.0.0",
        "setuptools>=60.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "flake8>=6.0",
            "mypy>=1.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Compilers",
    ],
    keywords="compiler, cython, transpiler",
)
