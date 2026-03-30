import threading

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from models import AppContext
from utils import authorized_tokens


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
        self.thread = threading.Thread(
            target=self.mcp.run, daemon=True, args=["http", False], kwargs={"log_level": "CRITICAL"}
        )
        self.thread.start()

    def _register_tools(self):
        self.mcp.add_tool(self.quit)

    async def quit(self):
        self.ctx.quit()
        return "closed app"
