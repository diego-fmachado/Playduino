from .settings import ServerSettings
from .compiler import MPYCompiler
from .ip import LOCAL_IP
from httpx import AsyncClient
from httpx import HTTPError
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram.ext import Application
from telegram.ext import ExtBot
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler
from telegram.ext import ContextTypes
from telegram.ext import filters
from telegram.ext import Updater
from telegram.error import NetworkError
from telegram.constants import MessageLimit
from traceback import format_exc
from asyncio import AbstractEventLoop
from asyncio import get_running_loop
from tempfile import mkdtemp
from os.path import basename
from itertools import batched
from functools import partial
from tools import SubprocessError
from logging import getLogger
from typing import Callable
import uvicorn
import aiofiles
import aiofiles.os




WELCOME_MESSAGE = "👋 Bem vindo ao Playduino, {}!\n\n{}"
WELCOME_TEACHER_MESSAGE = "🧑‍🏫 Como professor, você pode usar `/autorizar <ID>` para executar o código que o aluno submeteu ao sistema."
WELCOME_STUDENT_MESSSAGE = "🧑‍🎓 Como aluno, você pode enviar o arquivo **.py** do seu projeto (como anexo) para submissão."
PROJECT_EXTENSION_ERROR = "❌ Por favor, envie apenas arquivos Python (.py)."
PROJECT_STATUS_MESSAGE = "⏳ Baixando e processando arquivo..."
UNEXPECTED_ERROR_MESSAGE = "❌ Um Erro interno aconteceu, tente novamente:\n{}"
STATUS_SUCCESS_MESSAGE = "✅ Sucesso!"
PROJECT_REGISTER_SUCCESS = """✅ **Código recebido com sucesso!**
🔖 ID do seu projeto no sistema: `{}`
🧑‍🏫 Mande esse ID ao professor para que ele autorize a execução"""
PROJECT_ERROR_REPORT = """🚨 **Ocorreu um erro durante a execução do seu projeto** 🚨
🔖 ID do projeto: `{}`
📜 **Traceback do erro:**
{}
"""
MISSING_COMMAND_ARGUMENT = "⚠️ Esse comando requer os seguintes argumentos: {}"
PROJECT_COMPILE_ERROR = "❌ Ocorreu um erro ao pre compilar seu projeto:\n{} "
PROJECT_FILE_MISSING = "❌ Não foi encontrado esse projeto na base de dados, peça ao aluno para refazer o registro"
MCC_CONNECT_ERROR = "❌ Erro ao tentar se comunicar com o microcontrolador: {}"
MCC_UNAVAILABLE_ERROR = "⚠️ O dispositivo não está disponível do momento, tente novamente mais tarde"
OPEN_GAMEPAD_MESSAGE = "🎮 Utilize o botão abaixo para acessar o controle"

LOGGER = getLogger(__name__)
PORT = 8000
MCC_URL: str | None = None
SETTINGS: ServerSettings = None



CODES_DEST = "codes"
LOOP: AbstractEventLoop = None
MESSAGE_MAX_LENGTH = MessageLimit.MAX_TEXT_LENGTH - 3

async def run_in_executor[**P, R](
    func: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs
):
    return await LOOP.run_in_executor(None, partial(func, *args, **kwargs))
    

class CommandArgumentParser(BaseModel):
    @classmethod
    def parse(cls, args: list[str]):
        return cls(**(dict(zip(cls.model_fields, args, strict=True))))

class HandlerManager[PT: CommandArgumentParser | None]():
    def __init__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        parsed: PT
    ):
        self._update = update
        self._context = context
        self._parsed = parsed


    async def send_message(self, text: str, **kwargs):
        return await send_message(
            self._update.effective_chat.id,
            text,
            **kwargs
        )

    # async def edit_message(source: Message, text: str):
    #     return await _send_message(source.edit_text, text)

    @property
    def update(self):
        return self._update
    
    @property
    def context(self):
        return self._context
    
    @property
    def parsed(self):
        return self._parsed

    @classmethod
    def manage(cls, *, parse_args: type[CommandArgumentParser] | None=None):
        def wrapped(handler: Callable):
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
                try:
                    parsed = (
                        parse_args and
                        parse_args.parse(context.args) or
                        None
                    )
                except ValueError:
                    args = ", ".join(parse_args.model_fields)
                    text = MISSING_COMMAND_ARGUMENT.format(args)
                    return await send_message(update.effective_chat.id, text)
                self = cls(update, context, parsed)
                try:
                    return await handler(self)
                except:
                    trace_text = UNEXPECTED_ERROR_MESSAGE.format(format_exc())
                    await self.send_message(trace_text)

            return wrapper
        
        return wrapped


@HandlerManager.manage()
async def start(handler: HandlerManager):
    def get_welcome_message():
        if user.id == SETTINGS.teacher_user_id:
            return WELCOME_TEACHER_MESSAGE
        return WELCOME_STUDENT_MESSSAGE

    user = handler.update.effective_user
    message = WELCOME_MESSAGE.format(user.first_name, get_welcome_message())
    await handler.send_message(message, parse_mode="Markdown")

@HandlerManager.manage()
async def play(handler: HandlerManager):
    if not MCC_URL:
        return await handler.send_message(MCC_UNAVAILABLE_ERROR)
    gamepad_url = f"http://{LOCAL_IP}:{PORT}/gamepad?mccHost={MCC_URL}"
    await handler.send_message(
        OPEN_GAMEPAD_MESSAGE,
        reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🎮 Jogar",
                gamepad_url
            )
        ]])
    )

class ProjectMetadata(BaseModel):
    user_id: int

@HandlerManager.manage()
async def receive_project_file(handler: HandlerManager[None]):
    user = handler.update.effective_user
    document = handler.update.message.document
    if not document.file_name or not document.file_name.endswith(".py"):
        return await handler.send_message(PROJECT_EXTENSION_ERROR)
    file = await document.get_file()
    content = await file.download_as_bytearray()
    code_content = content.decode()
    metadata = ProjectMetadata(user_id=user.id)
    tmp_path = await run_in_executor(mkdtemp, prefix="", dir=CODES_DEST)
    code_path = f"{tmp_path}/game.py"
    async with aiofiles.open(code_path, "w", newline="") as f:
        await f.write(code_content)
    await run_in_executor(MPYCompiler.strip_code, code_path, code_path)
    try:
        await run_in_executor(
            MPYCompiler.compile_code,
            code_path,
            f"{tmp_path}/game.mpy"
        )
    except SubprocessError as e:
        text = PROJECT_COMPILE_ERROR.format(str(e))
        return await handler.send_message(text)
    await aiofiles.os.remove(code_path)
    async with aiofiles.open(f"{tmp_path}/metadata.json", "w") as f:
        await f.write(metadata.model_dump_json())
    await handler.send_message(
        PROJECT_REGISTER_SUCCESS.format(basename(tmp_path)),
        parse_mode="Markdown"
    )

class AuthorizeArgs(CommandArgumentParser):
    project_id: str

@HandlerManager.manage(parse_args=AuthorizeArgs)
async def authorize_execution(handler: HandlerManager[AuthorizeArgs]):
    if handler.update.effective_user.id != SETTINGS.teacher_user_id:
        return
    if not MCC_URL:
        reason = "O handshake não foi realizado pelo dispositivo"
        text = MCC_CONNECT_ERROR.format(reason)
        return await handler.send_message(text)
    project_id = handler.parsed.project_id
    compiled_path = f"{CODES_DEST}/{project_id}/game.mpy"
    try:
        async with aiofiles.open(compiled_path, "rb") as f:
            compiled_code = await f.read()
    except FileNotFoundError:
        return await handler.send_message(PROJECT_FILE_MISSING)
    try:
        async with AsyncClient() as client:
            response = await client.post(
                f"http://{MCC_URL}/project/upload/{project_id}",
                content=compiled_code,
                timeout=10
            )
            response.raise_for_status()
    except HTTPError as e:
        text = MCC_CONNECT_ERROR.format(e.__class__.__name__)
        return await handler.send_message(text)
    await handler.send_message(STATUS_SUCCESS_MESSAGE)

from contextlib import suppress

async def send_message(
    chat_id: int | str,
    text: str,
    **kwargs
):
    reply_to_id: int | None=None
    fragments = [
        "".join(batch)
        for batch in batched(
            text,
            MessageLimit.MAX_TEXT_LENGTH - 6
        )
    ]
    with suppress(NetworkError):
        for i, text_ in enumerate(fragments):
            if i > 0:
                text_ = "..." + text_
            if i < len(fragments) - 1:
                text_ += "..."
            message = await BOT_APP.bot.send_message(
                chat_id,
                text_,
                reply_to_message_id=reply_to_id,
                **kwargs
            )
            reply_to_id = message.id


BOT_APP: Application[ExtBot[None]] = None 

@asynccontextmanager
async def run_bot():
    await BOT_APP.initialize()
    await BOT_APP.updater.start_polling()
    await BOT_APP.start()
    try:
        yield
    finally:
        await BOT_APP.updater.stop()
        await BOT_APP.stop()
        await BOT_APP.shutdown()

@asynccontextmanager
async def lifespan(_):
    global LOOP
    LOOP = get_running_loop()
    async with run_bot():
        yield
    
app = FastAPI(lifespan=lifespan, title="Playduino")

class ErrorReport(BaseModel):
    error_trace: str

@app.post("/project/report/{project_id}")
async def report_error(project_id: str, report: ErrorReport):
    metadata_path = f"{CODES_DEST}/{project_id}/metadata.json"
    try:
        async with aiofiles.open(metadata_path) as f:
            data = await f.read()
            metadata = ProjectMetadata.model_validate_json(data)
    except FileNotFoundError:
        return LOGGER.debug(
            f"Project ID {project_id} not "
            "found, skipping report..."
        )
    await send_message(
        metadata.user_id,
        PROJECT_ERROR_REPORT.format(
            project_id,
            report.error_trace
        ), 
        parse_mode="Markdown"
    )

class HandshakeData(BaseModel):
    mcc_url: str

@app.post("/handshake")
async def report_error(data: HandshakeData):
    global MCC_URL
    MCC_URL = data.mcc_url

@app.get("/gamepad")
async def download_file():
    return FileResponse(
        path="static/gamepad.html",
        media_type="text/html"
    )

def run_server():
    global SETTINGS, BOT_APP

    SETTINGS = ServerSettings()
    BOT_APP = (
        Application.builder()
        .token(SETTINGS.bot_token)
        .build()
    )
    BOT_APP.add_handlers((
        CommandHandler("start", start),
        CommandHandler("autorizar", authorize_execution),
        CommandHandler("jogar", play),
        MessageHandler(filters.Document.TEXT, receive_project_file)
    ))
    uvicorn.run(
        "src.server:app",
        host="0.0.0.0",
        port=PORT
    )