from typing import Callable
from subprocess import Popen

def init_class[C: type](cls: C):
    init: Callable[[], None] | None = getattr(cls, "__init_class__", None)
    if init:
        assert isinstance(cls.__dict__[init.__name__], classmethod), \
            "__init_class__ has to be a classmethod"
        init()
    return cls

class SubprocessError(Exception):
    def __init__(self, process: Popen[bytes], err: str):
        super().__init__()
        self._process = process
        self._err = err

    @property
    def process(self):
        return self._process

    def __str__(self):
        return self._err

@staticmethod
def handle_process(process: Popen[bytes]):
    if process.wait():
        _, stderr = process.communicate()
        err = stderr.decode(errors="ignore")
        raise SubprocessError(process, err)
    