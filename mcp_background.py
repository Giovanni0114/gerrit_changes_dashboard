import threading
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.resources import FileResource
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from models import AppContext
from utils import authorized_tokens

MCP_PATH = Path("./mcp")


class AuthMiddleware(Middleware):
    async def on_request(self, context: MiddlewareContext, call_next: CallNext):
        headers = get_http_headers()
        auth = headers.get("authorization", "")

        if not auth.startswith("Bearer "):
            raise AuthorizationError("Missing or invalid Authorization header")

        if auth.removeprefix("Bearer ").strip() not in authorized_tokens():
            raise AuthorizationError("Unauthorized token")

        return await call_next(context)


class BackgroundMCPServer:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.mcp = FastMCP("Gerrit Approvals MCP Server")

        self._register_tools()
        self._register_resources()

        self.thread = threading.Thread(
            target=self.mcp.run, daemon=True, args=["http", False], kwargs={"log_level": "CRITICAL"}
        )
        self.thread.start()

    def _register_tools(self):
        self.mcp.add_tool(self._quit)
        self.mcp.add_tool(self._get_changes)

    def _register_resources(self):
        self.mcp.add_resource(
            FileResource(
                uri=f"file://{(MCP_PATH / 'README.md').as_posix()}",
                path=(MCP_PATH / "README.md").resolve(),
                name="README File",
                description="The project's README.",
                mime_type="text/markdown",
                tags={"documentation"},
            )
        )

    async def _quit(self):
        self.ctx.quit()
        return {"message": "Server closed"}

    async def _get_changes(self):
        payload = []
        for ch in self.ctx.get_changes():
            if ch.deleted or ch.disabled:
                continue
            payload.append(
                {
                    "instance": ch.instance,
                    "hash": ch.current_revision,
                    "waiting": ch.waiting,
                    "disabled": ch.disabled,
                    "deleted": ch.deleted,
                    "submitted": ch.submitted,
                    "subject": ch.subject,
                    "number": ch.number,
                    "project": ch.project,
                    "url": ch.url,
                    "approvals": [{"type": a.label, "value": a.value, "by": a.by} for a in ch.approvals],
                }
            )
        return {"changes": payload}
