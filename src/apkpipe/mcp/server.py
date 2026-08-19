"""MCP 2026-07-28 Server Protocol (RC), JSON-RPC 2.0 Handler, and SSE/HTTP Transports."""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apkpipe.mcp.tools import ALL_TOOLS, execute_tool

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2026-07-28"
SERVER_NAME = "apkpipe"
SERVER_VERSION = "0.1.0"


class McpServer:
    """Model Context Protocol (MCP 2026-07-28 RC) Server supporting JSON-RPC 2.0, SSE, and HTTP transports."""

    def __init__(self) -> None:
        """Initialize McpServer instance with active session registry."""
        self.sessions: Dict[str, asyncio.Queue] = {}

    async def _handle_single_request(
        self,
        req: Dict[str, Any],
        session: Optional[AsyncSession] = None,
    ) -> Optional[Dict[str, Any]]:
        """Process a single JSON-RPC 2.0 request or notification dictionary."""
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or "method" not in req:
            req_id = req.get("id") if isinstance(req, dict) else None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: expected valid JSON-RPC 2.0 object with method",
                },
            }

        method = req["method"]
        msg_id = req.get("id")
        params = req.get("params", {}) or {}

        # Handle notifications (no response expected)
        if method.startswith("notifications/") or msg_id is None:
            logger.debug("Received MCP notification: %s", method)
            return None

        # 1. initialize / server/discover
        if method in ("initialize", "server/discover", "discover"):
            client_proto = params.get("protocolVersion") or MCP_PROTOCOL_VERSION
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": client_proto if client_proto in ("2026-07-28", "2024-11-05") else MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        },
                        "prompts": {
                            "listChanged": False,
                        },
                        "resources": {
                            "subscribe": False,
                            "listChanged": False,
                        },
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            }

        # 2. ping
        if method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {},
            }

        # 3. tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": ALL_TOOLS,
                },
            }

        # 4. tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params: 'name' is required for tools/call",
                    },
                }

            result = await execute_tool(tool_name, tool_args, session=session)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": result,
            }

        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    async def handle_jsonrpc(
        self,
        request_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        session: Optional[AsyncSession] = None,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """Handle incoming JSON-RPC 2.0 payload (single or batch)."""
        if isinstance(request_data, list):
            responses = []
            for item in request_data:
                resp = await self._handle_single_request(item, session=session)
                if resp is not None:
                    responses.append(resp)
            return responses

        if isinstance(request_data, dict):
            return await self._handle_single_request(request_data, session=session)

        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32600,
                "message": "Invalid Request: payload must be a JSON object or array",
            },
        }

    def get_router(self) -> APIRouter:
        """Create and configure FastAPI APIRouter with MCP endpoints."""
        router = APIRouter(tags=["MCP"])

        @router.post("/mcp")
        async def direct_mcp_post(request: Request) -> Response:
            """Direct HTTP POST endpoint for standard MCP JSON-RPC 2.0 messages."""
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error: Invalid JSON"},
                    },
                    status_code=400,
                )

            resp = await self.handle_jsonrpc(body)
            if resp is None:
                return Response(status_code=204)
            return JSONResponse(content=resp)

        @router.get("/mcp/sse")
        async def mcp_sse_connect(request: Request) -> StreamingResponse:
            """Server-Sent Events connection endpoint for streaming MCP clients."""
            session_id = uuid.uuid4().hex
            queue: asyncio.Queue = asyncio.Queue()
            self.sessions[session_id] = queue

            async def event_generator() -> AsyncGenerator[str, None]:
                try:
                    # Announce message endpoint with session ID
                    yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"

                    while True:
                        try:
                            # Wait for next event in queue or timeout for keep-alive ping
                            msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                            yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                        except asyncio.TimeoutError:
                            # Keep-alive comment
                            yield ": ping\n\n"
                except (asyncio.CancelledError, GeneratorExit):
                    pass
                except Exception as exc:
                    logger.debug("SSE stream error: %s", exc)
                finally:
                    self.sessions.pop(session_id, None)
                    logger.debug("Cleaned up SSE session: %s", session_id)

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        @router.post("/mcp/messages")
        async def mcp_post_message(
            request: Request,
            session_id: Optional[str] = Query(None),
        ) -> Response:
            """Post message to an active SSE session."""
            if not session_id or session_id not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found or expired")

            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            resp = await self.handle_jsonrpc(body)
            queue = self.sessions.get(session_id)

            if resp is not None and queue is not None:
                queue.put_nowait(resp)
                return JSONResponse(content=resp, status_code=200)

            return Response(status_code=202)

        return router
