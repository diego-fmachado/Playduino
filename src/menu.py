from .ip import LOCAL_IP
from .path import MCC_ROOT
from .path import MCC_COMPILED
from .path import MCC_STRIPPED
from .server import PORT
from .server import run_server
from .settings import Settings
from .settings import MCCSettings
from .settings import MissingSettings
from .compiler import MPYCompiler
from .logger import ColoredStreamHandler
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from itertools import chain
from subprocess import Popen
from logging import getLogger
from logging import DEBUG
from inspect import isclass
from contextlib import contextmanager
from contextlib import suppress
from os import scandir
from os import mkdir
from os.path import basename
from os.path import join
from os.path import splitext
from os.path import relpath
from os.path import dirname
from subprocess import PIPE
from shutil import rmtree
from tools import SubprocessError
from tools import handle_process
from shutil import copy
from tempfile import TemporaryDirectory


class ExecutionError(RuntimeError): ...

LOGGER = getLogger(__name__)
LOGGER.addHandler(ColoredStreamHandler())
LOGGER.setLevel(DEBUG)
    
class Menu():
    title: str = ""
    submenus: list[type['Menu']] = []
    _rendering = set[type['Menu']]()

    @classmethod
    def _set_title(cls):
        if not cls.title:
            cls.title = "".join(
                (" " if char.isupper() and i else "") + char
                for i, char in enumerate(cls.__name__)
            )

    @classmethod
    def _inner_submenus(cls):
        for attr in vars(cls).values():
            if (
                isclass(attr)
                and issubclass(attr, Menu)
                and not attr in cls._rendering
            ):
                yield attr

    @classmethod
    def _render(cls, parent: type['Menu'] | None=None):
        cls._rendering.add(cls)
        cls._set_title()
        cls._parent = parent
        cls._submenus: list[type[Menu]] = []
        cls.on_render()
        for submenu in chain(cls._inner_submenus(), cls.submenus):
            cls._submenus.append(submenu)
            submenu._render(cls)


    @classmethod
    def on_render(cls): ...
        
    @classmethod
    def _has_submenus(cls):
        return bool(cls._submenus)

    @classmethod
    def execute(cls):
        raise NotImplementedError
    
    @staticmethod
    @contextmanager
    def _print_ln():
        print("")
        try:
            yield
        finally:
            print("")
    
    @classmethod
    def run(cls):
        cls._render()
        current: type[Menu] = cls
        while True:
            selected: type[Menu] | None = inquirer.select(
                current.title,
                [
                    *(
                        Choice(value=submenu, name=submenu.title)
                        for submenu in current._submenus
                    ),
                    Choice(
                        value=None,
                        name=current._parent and "Voltar" or "Sair"
                    ),
                ]
            ).execute()
            if not selected:
                if not current._parent:
                    break
                current = current._parent
                continue
            if selected._has_submenus():
                current = selected
                continue
            with cls._print_ln():
                try:
                    selected.execute()
                    LOGGER.info("Success!")
                except SubprocessError as e:
                    args = (
                        basename(arg) if not i else arg
                        for i, arg in enumerate(
                            e.process.args.split()
                            if isinstance(e.process.args, str) else
                            e.process.args
                        )
                    )
                    LOGGER.error(f'Running {' '.join(args)} -> {e}')
                except ExecutionError as e:
                    LOGGER.error(str(e))
                except:
                    LOGGER.exception(
                        "An unexpected "
                        "exception happened"
                    )

from time import sleep

class RunServer(Menu):
    title = "Iniciar servidor"

    @staticmethod
    def _update_mcc_settings():
        with TemporaryDirectory() as tmp:
            with open(f"{tmp}/env.json", "w") as f:
                env_json = MCCSettings().model_dump_json()
                f.write(env_json)
            with open(f"{tmp}/server_url", "w") as f:
                f.write(f"{LOCAL_IP}:{PORT}")
            
            cmd = f"mpremote cp -r {join(tmp, '.')} :env + reset"
            while True:
                try:
                    handle_process(Popen(cmd, stderr=PIPE))
                    break
                except SubprocessError as e:
                    LOGGER.debug(
                        "Error while updating "
                        f"microcontroller settings:\n{e}"
                    )
                    sleep(0.5)

    @classmethod
    def execute(cls):
        LOGGER.info(
            "Transferindo dados de conexão "
            "ao microcontrolador... (Ctrl + C para cancelar)"
        )
        try:
            try:
                cls._update_mcc_settings()
            except KeyboardInterrupt:
                LOGGER.warning(
                    "Operação cancelada, mas saiba que a "
                    "comunicação com o dispositivo pode falhar"
                )
            LOGGER.info("Iniciando servidor...")
            run_server()
        except MissingSettings as e:
            missing = "\n".join(
                name + (f": {description}" if description else "")
                for name, description in e.fields
            )
            raise ExecutionError(
                "As seguintes configurações obrigatórias "
                f"do {e.source.description} estão faltando:\n{missing}"
            )

class CompileInterface(Menu):
    title = "Compilar engine para o microcontrolador"

    @classmethod
    def _compile(
        cls,
        path: str,
        compiled_dest: str,
        stripped_dest: str,
        is_root: bool
    ):
        LOGGER.info(f"Compiling {path}...")
        filename = basename(path)
        stripped_path = join(stripped_dest, filename)
        MPYCompiler.strip_code(path, stripped_path)
        if not is_root or filename not in ("main.py", "boot.py"):
            compiled_path = join(compiled_dest, splitext(filename)[0] + ".mpy")
            MPYCompiler.compile_code(stripped_path, compiled_path)
        else:
            copy(stripped_path, join(compiled_dest, filename))

    @classmethod
    def execute(cls):
        def strip_and_compile(path: str, is_root: bool=True):
            for entry in scandir(path):
                rel_path = relpath(entry.path, start=MCC_ROOT)
                compiled_dest = join(MCC_COMPILED, dirname(rel_path))
                stripped_dest = join(MCC_STRIPPED, dirname(rel_path))
                if entry.is_dir():
                    mkdir(join(compiled_dest, entry.name))
                    mkdir(join(stripped_dest, entry.name))
                    strip_and_compile(entry.path, False)
                elif entry.name.endswith(".py"):
                    cls._compile(
                        entry.path,
                        compiled_dest,
                        stripped_dest,
                        is_root
                    )
                else:
                    copy(entry.path, join(compiled_dest, entry.name))

            
        @contextmanager
        def compile_dir():
            def remove_comp_dirs():
                for dest in (MCC_COMPILED, MCC_STRIPPED):
                    with suppress(FileNotFoundError):
                        rmtree(dest)
            
            remove_comp_dirs()
            mkdir(MCC_COMPILED)
            mkdir(MCC_STRIPPED)
            yield
            remove_comp_dirs()

        with compile_dir():
            strip_and_compile(MCC_ROOT)
            for msg, cmd in (
                ("Erasing memory...", "rm -rv"),
                ("Copying files...", "cp -r " + join(MCC_COMPILED, '.'))
            ):
                LOGGER.info(msg)
                handle_process(Popen(f"mpremote {cmd} :", stderr=PIPE))

class ChangeSettings(Menu):
    title = "Configurações"

    @classmethod
    def on_render(cls):
        def yield_options(settings: type[Settings]):
            def new_option(key: str, description: str):
                class Option(Menu):
                    title = f"Configurar {description}"

                    @classmethod
                    def execute(cls):
                        new_value = input("Entre com o novo valor: ")
                        settings.update({key: new_value})

                return Option
            
            for name, field in settings.model_fields.items():
                yield new_option(name, field.description or name)

        def yield_submenus():
            def new_submenu(settings: type[Settings]):
                class Submenu(Menu):
                    title = f"Configurar {settings.description}"
                    submenus = list(yield_options(settings))

                return Submenu
            
            for cls in Settings.__subclasses__():
                yield new_submenu(cls)

        cls.submenus = list(yield_submenus())

class MainMenu(Menu):
    submenus = [RunServer, CompileInterface, ChangeSettings]