from re import compile
from re import MULTILINE
from strip_hints import strip_file_to_string
from functools import reduce
from tools import init_class
from tools import handle_process
from subprocess import PIPE
import mpy_cross

@init_class
class MPYCompiler():
    _EXTRA_STRIP = (
        # Empty lines
        r"^\s*\n",
        # Python's 3.12 Generics syntax
        r"((?:class|def|type)\s+\w+\s*)\[[^\]]+\]",
        # Class Generics definition
        r"(class\s+[A-Za-z_]+\s*\(\s*[A-Za-z_]+\s*)"
        r"\[\s*[A-Za-z_, |[\]]+\s*\](\s*\)\s*:)",
        # Typing library imports
        r"^\s*from\s+typing.+?\n",
        # Custom types definitions
        r"^\s*type\s+[A-Za-z_0-9]+\s*=.*?\n",
        # Set's type annotations
        r"(^\s*[A-Za-z_0-9.]+\s*=\s*set)\s*\[.+?\]\s*(\(.*?\)\s*\n)"
    )

    @classmethod
    def __init_class__(cls):
        cls._extra_patterns = [
            compile(pattern, MULTILINE)
            for pattern in cls._EXTRA_STRIP
        ]

    @classmethod
    def strip_code(cls, src: str, dest: str):
        stripped = reduce(
            lambda s, p: p.sub(lambda m: "".join(m.groups()), s),
            cls._extra_patterns,
            strip_file_to_string(src, True)
        )
        with open(dest, "w", newline="") as f:
            f.write(stripped)

    @classmethod
    def compile_code(cls, src: str, dest: str):
        handle_process(
            mpy_cross.run(
                "-o",
                dest,
                src,
                stderr=PIPE,
                stdout=PIPE
            )
        )