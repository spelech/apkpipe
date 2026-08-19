"""Unit and integration tests for MCP server protocol, JSON-RPC 2.0, tools, and transports."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from apkpipe.database.db import close_db, get_db, init_db
from apkpipe.database.models import (
    AppSetting,
    DownloadHistory,
    DownloadTask,
    FeedSource,
    WatchlistItem,
)
from apkpipe.mcp.server import McpServer
from apkpipe.mcp.tools import (
    ALL_TOOLS,
    TOOL_REGISTRY,
    add_to_watchlist_tool,
    download_url_tool,
    execute_tool,
    get_history_tool,
    get_system_status_tool,
    list_watchlist_tool,
    remove_from_watchlist_tool,
    search_feed_tool,
    trigger_poll_tool,
)


@pytest.fixture(autouse=True)
async def setup_test_database():
    """Setup and teardown in-memory test database for each test."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    engine = await init_db(test_db_url)
    yield engine
    await close_db()


@pytest.mark.asyncio
async def test_tool_registry_and_schemas():
    """Verify all 8 standard tools are defined with valid schemas and registered."""
    expected_tools = {
        "apkpipe__list_watchlist",
        "apkpipe__add_to_watchlist",
        "apkpipe__remove_from_watchlist",
        "apkpipe__search_feed",
        "apkpipe__trigger_poll",
        "apkpipe__download_url",
        "apkpipe__get_history",
        "apkpipe__get_system_status",
    }
    assert set(TOOL_REGISTRY.keys()) == expected_tools

    tool_names = {t["name"] for t in ALL_TOOLS}
    assert tool_names == expected_tools

    for tool in ALL_TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


@pytest.mark.asyncio
async def test_mcp_initialize():
    """Verify MCP initialize returns 2024-11-05 protocol version and capabilities."""
    server = McpServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    resp = await server.handle_jsonrpc(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in resp["result"]["capabilities"]
    assert resp["result"]["serverInfo"]["name"] == "apkpipe"


@pytest.mark.asyncio
async def test_mcp_ping_and_notifications():
    """Verify ping and initialized notification handling."""
    server = McpServer()

    # Ping
    ping_req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    ping_resp = await server.handle_jsonrpc(ping_req)
    assert ping_resp["jsonrpc"] == "2.0"
    assert ping_resp["id"] == 2
    assert ping_resp["result"] == {}

    # Initialized notification (no id)
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    notif_resp = await server.handle_jsonrpc(notif)
    assert notif_resp is None


@pytest.mark.asyncio
async def test_mcp_tools_list():
    """Verify tools/list returns full list of available tools."""
    server = McpServer()
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    resp = await server.handle_jsonrpc(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 3
    tools = resp["result"]["tools"]
    assert len(tools) == 8
    tool_names = [t["name"] for t in tools]
    assert "apkpipe__list_watchlist" in tool_names
    assert "apkpipe__get_system_status" in tool_names


@pytest.mark.asyncio
async def test_mcp_invalid_and_unknown_methods():
    """Verify JSON-RPC error codes for invalid requests and unknown methods."""
    server = McpServer()

    # Unknown method
    unknown_req = {"jsonrpc": "2.0", "id": 4, "method": "non_existent_method"}
    resp = await server.handle_jsonrpc(unknown_req)
    assert resp["error"]["code"] == -32601
    assert "Method not found" in resp["error"]["message"]

    # Invalid JSON-RPC request structure
    invalid_req = {"not_jsonrpc": True}
    resp = await server.handle_jsonrpc(invalid_req)
    assert resp["error"]["code"] == -32600

    # Batch request
    batch_req = [
        {"jsonrpc": "2.0", "id": 10, "method": "ping"},
        {"jsonrpc": "2.0", "id": 11, "method": "ping"},
    ]
    batch_resp = await server.handle_jsonrpc(batch_req)
    assert isinstance(batch_resp, list)
    assert len(batch_resp) == 2
    assert batch_resp[0]["id"] == 10
    assert batch_resp[1]["id"] == 11


@pytest.mark.asyncio
async def test_tool_add_and_list_watchlist():
    """Test adding apps to watchlist and listing with various filters."""
    # 1. Add app
    add_args = {
        "app_name": "Nova Launcher",
        "package_name": "com.teslacoilsw.launcher",
        "title_regex": r"^Nova Launcher Prime.*",
        "min_version": "8.0.0",
        "releaser_whitelist": ["Balatan", "derrin"],
        "category": "Personalization",
        "enabled": True,
    }
    result = await execute_tool("apkpipe__add_to_watchlist", add_args)
    assert result.get("isError", False) is False
    assert len(result["content"]) > 0
    data = json.loads(result["content"][0]["text"])
    assert data["app_name"] == "Nova Launcher"
    assert data["min_version"] == "8.0.0"
    item_id = data["id"]

    # 2. Add second app
    await execute_tool(
        "apkpipe__add_to_watchlist",
        {
            "app_name": "VLC for Android",
            "package_name": "org.videolan.vlc",
            "category": "Media",
            "enabled": False,
        },
    )

    # 3. List all
    list_res = await execute_tool("apkpipe__list_watchlist", {})
    assert list_res.get("isError", False) is False
    all_items = json.loads(list_res["content"][0]["text"])
    assert len(all_items) == 2

    # 4. List enabled only
    enabled_res = await execute_tool("apkpipe__list_watchlist", {"enabled_only": True})
    enabled_items = json.loads(enabled_res["content"][0]["text"])
    assert len(enabled_items) == 1
    assert enabled_items[0]["app_name"] == "Nova Launcher"

    # 5. Filter by category
    media_res = await execute_tool("apkpipe__list_watchlist", {"category": "Media"})
    media_items = json.loads(media_res["content"][0]["text"])
    assert len(media_items) == 1
    assert media_items[0]["app_name"] == "VLC for Android"

    # 6. Filter by query
    query_res = await execute_tool("apkpipe__list_watchlist", {"query": "teslacoil"})
    query_items = json.loads(query_res["content"][0]["text"])
    assert len(query_items) == 1
    assert query_items[0]["id"] == item_id


@pytest.mark.asyncio
async def test_tool_add_watchlist_invalid_regex_and_validation():
    """Test validation errors when adding watchlist items."""
    # Missing required app_name
    res_empty = await execute_tool("apkpipe__add_to_watchlist", {"app_name": ""})
    assert res_empty["isError"] is True
    assert "app_name is required" in res_empty["content"][0]["text"]

    # Invalid regex
    res_regex = await execute_tool(
        "apkpipe__add_to_watchlist",
        {"app_name": "Broken App", "title_regex": "[invalid regex("},
    )
    assert res_regex["isError"] is True
    assert "Invalid regex" in res_regex["content"][0]["text"]


@pytest.mark.asyncio
async def test_tool_remove_from_watchlist():
    """Test disabling and deleting watchlist items."""
    add_res = await execute_tool(
        "apkpipe__add_to_watchlist",
        {"app_name": "SD Maid Pro", "category": "Tools", "enabled": True},
    )
    item_id = json.loads(add_res["content"][0]["text"])["id"]

    # Disable (delete=False)
    disable_res = await execute_tool(
        "apkpipe__remove_from_watchlist",
        {"watchlist_id": item_id, "delete": False},
    )
    assert disable_res.get("isError", False) is False
    assert "disabled" in disable_res["content"][0]["text"].lower()

    # Verify enabled is False
    list_res = await execute_tool("apkpipe__list_watchlist", {"enabled_only": True})
    assert len(json.loads(list_res["content"][0]["text"])) == 0

    # Delete permanently by app_name
    del_res = await execute_tool(
        "apkpipe__remove_from_watchlist",
        {"app_name": "SD Maid Pro", "delete": True},
    )
    assert del_res.get("isError", False) is False
    assert "deleted" in del_res["content"][0]["text"].lower()

    # Remove non-existent
    not_found_res = await execute_tool(
        "apkpipe__remove_from_watchlist",
        {"watchlist_id": 99999},
    )
    assert not_found_res["isError"] is True


@pytest.mark.asyncio
async def test_tool_search_feed():
    """Test searching RSS feeds with keyword and regex patterns."""
    sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Mobilism Android Releases</title>
        <item>
          <title>Nova Launcher Prime v8.0.18 [Mod] [Balatan]</title>
          <link>https://forum.mobilism.org/viewtopic.php?t=1001</link>
          <description>Nova Launcher Prime full version</description>
        </item>
        <item>
          <title>Spotify Music and Podcasts v8.9.12 [Premium] [derrin]</title>
          <link>https://forum.mobilism.org/viewtopic.php?t=1002</link>
          <description>Spotify modded release</description>
        </item>
      </channel>
    </rss>
    """

    # Keyword search
    kw_res = await execute_tool(
        "apkpipe__search_feed",
        {"query": "Spotify", "feed_url": sample_rss},
    )
    assert kw_res.get("isError", False) is False
    kw_data = json.loads(kw_res["content"][0]["text"])
    assert len(kw_data) == 1
    assert "Spotify" in kw_data[0]["title"]
    assert kw_data[0]["version"] == "8.9.12"
    assert kw_data[0]["releaser"] == "derrin"

    # Regex search
    regex_res = await execute_tool(
        "apkpipe__search_feed",
        {"query": r"Nova.*8\.0\.\d+", "is_regex": True, "feed_url": sample_rss},
    )
    assert regex_res.get("isError", False) is False
    regex_data = json.loads(regex_res["content"][0]["text"])
    assert len(regex_data) == 1
    assert "Nova Launcher" in regex_data[0]["title"]

    # Search against database feed sources
    async for session in get_db():
        feed = FeedSource(
            name="Sample Feed",
            url=sample_rss,
            feed_type="mobilism_rss",
            enabled=True,
        )
        session.add(feed)
        await session.commit()

    db_search_res = await execute_tool("apkpipe__search_feed", {"query": "Nova"})
    assert db_search_res.get("isError", False) is False
    db_items = json.loads(db_search_res["content"][0]["text"])
    assert len(db_items) >= 1


@pytest.mark.asyncio
async def test_tool_trigger_poll():
    """Test triggering feed polling and automatic download task generation."""
    sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Mobilism Android Releases</title>
        <item>
          <title>MX Player Pro v1.78.2 [Patched] [Balatan]</title>
          <link>https://forum.mobilism.org/viewtopic.php?t=2001</link>
          <description>MX Player release</description>
        </item>
      </channel>
    </rss>
    """

    # Add watchlist item
    await execute_tool(
        "apkpipe__add_to_watchlist",
        {
            "app_name": "MX Player Pro",
            "min_version": "1.70.0",
            "releaser_whitelist": ["Balatan"],
            "enabled": True,
        },
    )

    # Add feed source
    async for session in get_db():
        feed = FeedSource(
            name="Test Feed",
            url=sample_rss,
            feed_type="mobilism_rss",
            enabled=True,
        )
        session.add(feed)
        await session.commit()
        await session.refresh(feed)
        feed_id = feed.id

    # Trigger poll
    poll_res = await execute_tool("apkpipe__trigger_poll", {"feed_id": feed_id})
    assert poll_res.get("isError", False) is False
    poll_data = json.loads(poll_res["content"][0]["text"])
    assert poll_data["polled_feeds"] == 1
    assert poll_data["matches_found"] == 1
    assert poll_data["tasks_created"] == 1

    # Verify task was created in DB
    async for session in get_db():
        tasks = (await session.execute(select(DownloadTask))).scalars().all()
        assert len(tasks) == 1
        assert "MX Player" in tasks[0].feed_item_title
        assert tasks[0].matched_version == "1.78.2"


@pytest.mark.asyncio
async def test_tool_download_url_and_history(tmp_path):
    """Test manually initiating a download and querying history records."""
    target_file = tmp_path / "apps" / "TestApp v1.0.0 [test].apk"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(b"dummy apk content")

    mock_download = AsyncMock(return_value=target_file)
    mock_resolve = AsyncMock(
        return_value=MagicMock(
            download_url="https://real-debrid.com/d/xyz",
            filename="TestApp v1.0.0 [test].apk",
            tier="real_debrid",
        )
    )

    with patch("apkpipe.resolvers.manager.ResolverManager.resolve", mock_resolve), patch(
        "apkpipe.downloader.engine.DownloadEngine.download", mock_download
    ):
        dl_res = await execute_tool(
            "apkpipe__download_url",
            {
                "url": "https://rapidgator.net/file/12345/app.apk",
                "app_name": "TestApp",
                "version": "1.0.0",
                "releaser": "test",
                "auto_resolve": True,
                "trigger_ingest": False,
            },
        )
        assert dl_res.get("isError", False) is False
        dl_data = json.loads(dl_res["content"][0]["text"])
        assert dl_data["status"] == "completed"
        assert dl_data["app_name"] == "TestApp"

    # Query history
    hist_res = await execute_tool("apkpipe__get_history", {"limit": 10})
    assert hist_res.get("isError", False) is False
    hist_data = json.loads(hist_res["content"][0]["text"])
    assert len(hist_data) >= 1
    assert hist_data[0]["app_name"] == "TestApp"


@pytest.mark.asyncio
async def test_tool_get_system_status():
    """Test retrieving system health and configuration status."""
    res = await execute_tool("apkpipe__get_system_status", {})
    assert res.get("isError", False) is False
    data = json.loads(res["content"][0]["text"])
    assert data["status"] == "healthy"
    assert "database" in data
    assert "services" in data
    assert "storage" in data
    assert "watchlist_count" in data["database"]
    assert "real_debrid_configured" in data["services"]


@pytest.mark.asyncio
async def test_mcp_tools_call_dispatch():
    """Test McpServer tools/call dispatching."""
    server = McpServer()

    # Valid tool call
    call_req = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {
            "name": "apkpipe__get_system_status",
            "arguments": {},
        },
    }
    resp = await server.handle_jsonrpc(call_req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 100
    assert "content" in resp["result"]
    assert resp["result"]["isError"] is False

    # Unknown tool call
    unknown_call = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "tools/call",
        "params": {
            "name": "apkpipe__nonexistent",
            "arguments": {},
        },
    }
    resp_unknown = await server.handle_jsonrpc(unknown_call)
    assert resp_unknown["jsonrpc"] == "2.0"
    assert resp_unknown["id"] == 101
    assert resp_unknown["result"]["isError"] is True


@pytest.mark.asyncio
async def test_mcp_fastapi_http_and_sse_routes():
    """Test FastAPI router integration for direct POST /mcp and SSE endpoints."""
    server = McpServer()
    app = FastAPI()
    app.include_router(server.get_router())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Direct POST /mcp with ping
        post_resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert post_resp.status_code == 200
        assert post_resp.json()["result"] == {}

        # 2. Direct POST /mcp with notification (no response body / 204)
        notif_resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert notif_resp.status_code == 204

        # 3. Direct POST /mcp with invalid JSON syntax
        invalid_json_resp = await client.post(
            "/mcp",
            content=b"not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert invalid_json_resp.status_code == 400
        assert invalid_json_resp.json()["error"]["code"] == -32700

        # 4. SSE session message dispatching
        # Manually register a session in server
        test_session_id = "test-session-123"
        session_queue = asyncio.Queue()
        server.sessions[test_session_id] = session_queue

        # Post message to session
        msg_resp = await client.post(
            f"/mcp/messages?session_id={test_session_id}",
            json={"jsonrpc": "2.0", "id": 42, "method": "ping"},
        )
        assert msg_resp.status_code == 200
        assert msg_resp.json()["result"] == {}

        # Verify message was also pushed to session queue
        queued_msg = await session_queue.get()
        assert queued_msg["id"] == 42
        assert queued_msg["result"] == {}


@pytest.mark.asyncio
async def test_mcp_server_session_cleanup():
    """Test McpServer session cleanup, invalid session ID, and bad JSON."""
    server = McpServer()
    app = FastAPI()
    app.include_router(server.get_router())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Post to invalid / non-existent session
        resp = await client.post(
            "/mcp/messages?session_id=invalid-session-id",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

        # Post without session_id
        resp_no_id = await client.post(
            "/mcp/messages",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert resp_no_id.status_code == 404

        # Post with invalid JSON to messages
        session_id = "valid-session"
        server.sessions[session_id] = asyncio.Queue()
        bad_json_resp = await client.post(
            f"/mcp/messages?session_id={session_id}",
            content=b"{invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert bad_json_resp.status_code == 400

        # Post notification to messages (no JSON-RPC response -> 202)
        notif_msg_resp = await client.post(
            f"/mcp/messages?session_id={session_id}",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert notif_msg_resp.status_code == 202


@pytest.mark.asyncio
async def test_mcp_sse_event_generator_direct():
    """Test SSE event generator output and session lifecycle directly."""
    server = McpServer()
    router = server.get_router()

    sse_route = [r for r in router.routes if getattr(r, "path", None) == "/mcp/sse"][0]

    mock_request = MagicMock()
    response = await sse_route.endpoint(mock_request)
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"

    gen = response.body_iterator

    # First chunk: endpoint announcement
    chunk1 = await anext(gen)
    assert "event: endpoint" in chunk1
    session_id = chunk1.split("session_id=")[-1].strip()
    assert session_id in server.sessions

    # Put a message in queue
    queue = server.sessions[session_id]
    await queue.put({"jsonrpc": "2.0", "id": 99, "result": "ok"})

    chunk2 = await anext(gen)
    assert "event: message" in chunk2
    assert '"id": 99' in chunk2

    # Close generator and ensure cleanup
    await gen.aclose()
    assert session_id not in server.sessions


@pytest.mark.asyncio
async def test_mcp_protocol_edge_cases():
    """Test tools/call without name and invalid JSON-RPC payload formats."""
    server = McpServer()

    # tools/call missing 'name'
    no_name_call = {
        "jsonrpc": "2.0",
        "id": 201,
        "method": "tools/call",
        "params": {},
    }
    resp = await server.handle_jsonrpc(no_name_call)
    assert resp["error"]["code"] == -32602
    assert "Invalid params" in resp["error"]["message"]

    # Payload that is neither dict nor list (e.g. primitive number or string)
    invalid_type_resp = await server.handle_jsonrpc(12345)  # type: ignore[arg-type]
    assert invalid_type_resp["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_tool_edge_cases_and_error_handling(tmp_path):
    """Test tool error handling, validation, and auto_resolve=False."""
    # 1. remove_from_watchlist without id or app_name
    err_rem = await execute_tool("apkpipe__remove_from_watchlist", {})
    assert err_rem["isError"] is True
    assert "Either watchlist_id or app_name" in err_rem["content"][0]["text"]

    # 2. search_feed with invalid regex
    err_search_regex = await execute_tool(
        "apkpipe__search_feed",
        {"query": "[invalid(", "is_regex": True, "feed_url": "<rss></rss>"},
    )
    assert err_search_regex["isError"] is True
    assert "Invalid search regex" in err_search_regex["content"][0]["text"]

    # 3. search_feed with failing remote URL
    with patch("httpx.AsyncClient.get", side_effect=Exception("Network error")):
        err_search_http = await execute_tool(
            "apkpipe__search_feed",
            {"query": "Test", "feed_url": "https://example.com/bad-feed.xml"},
        )
        assert err_search_http["isError"] is True
        assert "Failed to fetch feed" in err_search_http["content"][0]["text"]

    # 4. download_url with empty URL
    err_dl_empty = await execute_tool("apkpipe__download_url", {"url": ""})
    assert err_dl_empty["isError"] is True
    assert "url is required" in err_dl_empty["content"][0]["text"]

    # 5. download_url with auto_resolve=False
    enqueue_res = await execute_tool(
        "apkpipe__download_url",
        {
            "url": "https://example.com/file.apk",
            "app_name": "QueuedApp",
            "auto_resolve": False,
        },
    )
    assert enqueue_res["isError"] is False
    enq_data = json.loads(enqueue_res["content"][0]["text"])
    assert enq_data["status"] == "pending"
    assert enq_data["auto_resolve"] is False

    # 6. download_url failure handling
    with patch(
        "apkpipe.resolvers.manager.ResolverManager.resolve",
        side_effect=Exception("Resolution server timeout"),
    ):
        fail_dl = await execute_tool(
            "apkpipe__download_url",
            {
                "url": "https://example.com/broken.apk",
                "app_name": "BrokenDownload",
                "auto_resolve": True,
            },
        )
        assert fail_dl["isError"] is True
        assert "Resolution server timeout" in fail_dl["content"][0]["text"]

    # 7. execute_tool with non-existent tool
    not_found_tool = await execute_tool("apkpipe__does_not_exist", {})
    assert not_found_tool["isError"] is True
    assert "not found in registry" in not_found_tool["content"][0]["text"]

    # 8. trigger_poll skipping duplicate tasks
    sample_feed = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>DupeApp v1.0.0 [Balatan]</title>
          <link>https://forum.mobilism.org/viewtopic.php?t=9999</link>
        </item>
      </channel>
    </rss>
    """
    await execute_tool(
        "apkpipe__add_to_watchlist",
        {"app_name": "DupeApp", "min_version": "1.0.0"},
    )
    async for session in get_db():
        feed = FeedSource(name="DupeFeed", url=sample_feed, enabled=True)
        session.add(feed)
        await session.commit()
        feed_id = feed.id

    # Poll first time -> task created
    poll1 = await execute_tool("apkpipe__trigger_poll", {"feed_id": feed_id})
    assert json.loads(poll1["content"][0]["text"])["tasks_created"] == 1

    # Poll second time -> duplicate skipped (tasks_created=0)
    poll2 = await execute_tool("apkpipe__trigger_poll", {"feed_id": feed_id})
    assert json.loads(poll2["content"][0]["text"])["tasks_created"] == 0
