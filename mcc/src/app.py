from microdot import Microdot
from microdot import Request
from microdot.cors import CORS
from microdot.websocket import with_websocket
from microdot.websocket import WebSocket
from microdot.websocket import WebSocketError
from aiohttp import ClientSession
from playduino import GameEngine
from playduino import GP_BUILDER
from asyncio import sleep_ms
from wifi import get_ip_address
from report import ErrorReporter

ENGINE: GameEngine = None
PORT = 5000

async def do_server_handshake(http: ClientSession):
    mcc_url = f"{get_ip_address()}:{PORT}"
    print("Entrando em contato com o servidor...")
    while True:
        try:
            async with http.post(
                "/handshake",
                json={"mcc_url": mcc_url}
            ) as resp:
                await resp.text()
                break
        except Exception as e:
            print(f"Erro ao tentar contactar o servidor: {e}")

def read_data(filename: str):
    with open(f"env/{filename}") as f:
        return f.read()
    
server = Microdot()
is_shutting_down: bool = False

CORS(server, allowed_origins="*")

class Gamepad():
    @staticmethod
    def _update_state(_): ...

def log_errors(*exc_type: type[Exception]):
    def wrapped(func):
        async def wrapper(*args):
            try:
                return await func(*args)
            except exc_type as e:
                print(f"{e.__class__.__name__}: {e}")
        return wrapper
    return wrapped

@server.route("/players")
def get_players(_):
    return GP_BUILDER._info
    
@server.route("/gamepad")
@with_websocket
@log_errors(WebSocketError)
async def connect_gamepad(_, ws: WebSocket):
    info = None
    try:
        id = await ws.receive()
        info = GP_BUILDER._info[id]
        if info["isConnected"]:
            return await ws.send(
                "Someone is already connected"
                f" as {info['label']}"
            )
        info["isConnected"] = True
        print(f"Conectado! ID type: {type(id)}")
        gamepad = GP_BUILDER._instances[id]
        while not is_shutting_down:
            state = await ws.receive()
            gamepad._update_state(int(state))
    except KeyError:
        await ws.send("Invalid player ID")
    except ValueError:
        await ws.send("Invalid state data")
    finally:
        await ws.close()
        if info:
            info["isConnected"] = False

@server.post("/project/upload/<project_id>")
async def upload_project(request: Request, project_id: str):
    global is_shutting_down

    with open("lib/game.mpy", "wb") as f:
        while True:
            chunk = await request.stream.read(1024)
            if not chunk:
                break
            f.write(chunk)
    with open("env/project_id", "w") as f:
        f.write(project_id)
    is_shutting_down = True
    server.shutdown()

def get_engine(reporter: ErrorReporter):
    try:
        import game
        return GameEngine._get_implementation(game)(reporter)
    except Exception as e:
        reporter.report_error(e)
        engine = GameEngine(reporter)
        engine._activate_error_animation()
        return engine
    
async def main():
    global ENGINE
    async with ClientSession(f"http://{read_data("server_url")}") as http, \
        ErrorReporter(http, read_data("project_id")) as reporter:
        await do_server_handshake(http)
        async with get_engine(reporter) as ENGINE:
            await server.start_server(port=PORT, debug=True)