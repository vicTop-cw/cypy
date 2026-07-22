from typing import List, Dict


class SetupGenerator:
    def __init__(self):
        self.module_name = ""
        self.sources: List[str] = []
        self.include_dirs: List[str] = []
        self.libraries: List[str] = []
        self.library_dirs: List[str] = []
        self.extra_compile_args: List[str] = []
        self.extra_link_args: List[str] = []

    def set_module_name(self, name: str) -> None:
        self.module_name = name

    def add_source(self, source: str) -> None:
        self.sources.append(source)

    def add_include_dir(self, path: str) -> None:
        self.include_dirs.append(path)

    def add_library(self, lib: str) -> None:
        self.libraries.append(lib)

    def add_library_dir(self, path: str) -> None:
        self.library_dirs.append(path)

    def add_compile_arg(self, arg: str) -> None:
        self.extra_compile_args.append(arg)

    def add_link_arg(self, arg: str) -> None:
        self.extra_link_args.append(arg)

    def generate(self) -> str:
        parts = [
            "from setuptools import setup, Extension",
            "",
            "setup(",
            f"    name='{self.module_name}',",
            "    version='0.1.0',",
            "    ext_modules=[",
            "        Extension(",
            f"            '{self.module_name}',",
            f"            sources={self.sources},",
        ]

        if self.include_dirs:
            parts.append(f"            include_dirs={self.include_dirs},")
        if self.libraries:
            parts.append(f"            libraries={self.libraries},")
        if self.library_dirs:
            parts.append(f"            library_dirs={self.library_dirs},")
        if self.extra_compile_args:
            parts.append(f"            extra_compile_args={self.extra_compile_args},")
        if self.extra_link_args:
            parts.append(f"            extra_link_args={self.extra_link_args},")

        parts.extend([
            "        ),",
            "    ],",
            ")",
        ])

        return "\n".join(parts)
