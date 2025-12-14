from aiohttp import ClientSession
from sys import print_exception
from io import StringIO
from asyncio import create_task
from asyncio import Task

class ErrorReporter():
    def __init__(self, http: ClientSession, project_id: str):
        self._http = http
        self._project_id = project_id
        self._report_task: Task | None = None

    def report_error(self, exc: Exception):
        try:
            raise exc
        except Exception as e:
            with StringIO() as f:
                print_exception(e, f)
                self._do_request(f.getvalue())

    async def _request(self, trace: str):
        async with self._http.post(
            f"/project/report/{self._project_id}",
            json={"error_trace": trace}
        ) as resp:
            await resp.text()

    def _do_request(self, trace: str):
        self._report_task = create_task(self._request(trace))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        if self._report_task:
            await self._report_task