"""A fake MCP server for trying Sensai's MCP support by hand.

Speaks the stateless `2026-07-28` protocol over plain JSON on HTTP and prints every
request it receives and every reply it sends. Run it, then point a
`[mcp.servers.<name>]` table at `http://127.0.0.1:8765/mcp/`:

    uv run python scripts/fake_mcp_server.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

PROTOCOL_VERSION = "2026-07-28"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "echo",
        "description": "Echo the given text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "add",
        "description": "Add two numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        # No annotations: Sensai assumes side effects and asks for confirmation.
        "name": "delete_everything",
        "description": "Pretend to delete everything (does nothing).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "fail",
        "description": "Always report an execution failure.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
]


def _text(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a fake tool and return its `tools/call` result."""
    match name:
        case "echo":
            return _text(f"echo: {arguments.get('text', '')}")
        case "add":
            return _text(str(arguments.get("a", 0) + arguments.get("b", 0)))
        case "delete_everything":
            return _text("Deleted everything (just kidding).")
        case "fail":
            return _text("this tool always fails", is_error=True)
    raise KeyError(name)


def _dispatch(request: dict[str, Any]) -> dict[str, Any]:
    """Build the JSON-RPC response for a request."""
    method = request.get("method")
    params = request.get("params", {})
    reply: dict[str, Any] = {"jsonrpc": "2.0", "id": request.get("id")}
    match method:
        case "server/discover":
            info = {"name": "fake-mcp", "version": "0.0.1"}
            reply["result"] = {"_meta": {"io.modelcontextprotocol/serverInfo": info}}
        case "tools/list":
            reply["result"] = {"tools": TOOLS}
        case "tools/call":
            try:
                reply["result"] = _call_tool(
                    params.get("name", ""), params.get("arguments", {})
                )
            except KeyError:
                reply["error"] = {
                    "code": -32602,
                    "message": f"unknown tool {params.get('name')!r}",
                }
        case _:
            reply["error"] = {"code": -32601, "message": f"unknown method {method!r}"}
    return reply


class Handler(BaseHTTPRequestHandler):
    """Answer JSON-RPC POSTs and print both directions."""

    def do_POST(self) -> None:
        """Handle one JSON-RPC request."""
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        print(f"\n--> POST {self.path}")
        for header in ("Authorization", "Mcp-Protocol-Version", "Mcp-Session-Id"):
            if header in self.headers:
                print(f"    {header}: {self.headers[header]}")
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            print(f"    invalid JSON: {raw!r}")
            self.send_error(400, "invalid JSON")
            return
        print(json.dumps(request, indent=2))

        reply = _dispatch(request)
        print("<-- reply")
        print(json.dumps(reply, indent=2))

        body = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Protocol-Version", PROTOCOL_VERSION)
        self.send_header("Mcp-Session-Id", "fake-session")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default access log; `do_POST` prints what matters."""


def main() -> None:
    """Parse the command line and serve until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)  # show requests live when piped
    server = HTTPServer((args.host, args.port), Handler)
    print(f"fake MCP server listening on http://{args.host}:{args.port}/mcp/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
