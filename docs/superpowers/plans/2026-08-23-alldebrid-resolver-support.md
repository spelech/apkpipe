# AllDebrid Link Resolver Support with Peer Fallthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement AllDebrid as a peer multihoster resolver alongside Real-Debrid, supporting seamless auth/error fallthrough across the download resolution chain, configuration persistence, MCP tools, and React Web UI controls.

**Architecture:** Create an `AllDebridResolver` class in `src/apkpipe/resolvers/all_debrid.py` adhering to `BaseResolver`. Register it in `ResolutionManager` with priority between Real-Debrid and JDownloader. Extend `Settings`, SQLite settings persistence, REST API routes, MCP server tools, and React SPA views (`Settings.tsx`, `Badge.tsx`, `ManualDownloadModal.tsx`).

**Tech Stack:** Python 3.12, httpx, FastAPI, Pydantic, React 18, TypeScript 5, TanStack Query, Tailwind CSS.

## Global Constraints

- Backend REST API endpoints under `/api/*`, `/health`, and `/mcp/*` must not introduce breaking schema changes.
- All existing 309 Python tests must continue to pass with total coverage $\ge 80\%$.
- Frontend TypeScript compiler checks (`npm run typecheck`) must pass with 0 errors.
- Unconfigured AllDebrid (or missing/invalid API key) must never block other resolvers or crash the download pipeline.

---

### Task 1: AllDebrid Resolver Module & Unit Tests

**Files:**
- Create: `src/apkpipe/resolvers/all_debrid.py`
- Modify: `src/apkpipe/resolvers/__init__.py`
- Test: `tests/test_resolvers_alldebrid.py`

**Interfaces:**
- Produces: `AllDebridResolver` class implementing `BaseResolver` with `can_resolve(link: str) -> bool` and `resolve(link: str, **kwargs) -> Optional[ResolvedDownload]`.

- [ ] **Step 1: Write unit tests for AllDebrid resolver**

Create `tests/test_resolvers_alldebrid.py`:
```python
"""Unit tests for AllDebrid link resolver."""

import pytest
import respx
import httpx
from apkpipe.resolvers.all_debrid import AllDebridResolver, KNOWN_AD_HOSTERS
from apkpipe.resolvers.base import (
    AuthenticationError,
    LinkDeadError,
    RateLimitError,
    ResolvedDownload,
    UnsupportedHosterError,
)

@pytest.mark.asyncio
async def test_alldebrid_unconfigured():
    resolver = AllDebridResolver(api_key=None)
    assert not resolver.is_configured
    assert not await resolver.can_resolve("https://rapidgator.net/file/123/sample.rar")
    result = await resolver.resolve("https://rapidgator.net/file/123/sample.rar")
    assert result is None

@pytest.mark.asyncio
async def test_alldebrid_can_resolve_configured():
    resolver = AllDebridResolver(api_key="valid_test_key")
    assert resolver.is_configured
    assert await resolver.can_resolve("https://rapidgator.net/file/123/sample.rar")
    assert await resolver.can_resolve("https://1fichier.com/?abcdef")
    assert not await resolver.can_resolve("not_a_url")
    assert not await resolver.can_resolve("ftp://random.com/file")

@pytest.mark.asyncio
@respx.mock
async def test_alldebrid_successful_resolve():
    resolver = AllDebridResolver(api_key="valid_test_key")
    link = "https://rapidgator.net/file/123/sample.rar"
    respx.get("https://api.alldebrid.com/v4/link/unlock").respond(
        status_code=200,
        json={
            "status": "success",
            "data": {
                "link": "https://debrid.alldebrid.com/dl/sample.rar",
                "filename": "sample.apk",
                "filesize": 52428800,
                "host": "rapidgator",
            },
        },
    )
    result = await resolver.resolve(link)
    assert isinstance(result, ResolvedDownload)
    assert result.download_url == "https://debrid.alldebrid.com/dl/sample.rar"
    assert result.filename == "sample.apk"
    assert result.filesize == 52428800
    assert result.hoster == "rapidgator"
    assert result.tier == "alldebrid"

@pytest.mark.asyncio
@respx.mock
async def test_alldebrid_auth_error():
    resolver = AllDebridResolver(api_key="invalid_key")
    link = "https://rapidgator.net/file/123/sample.rar"
    respx.get("https://api.alldebrid.com/v4/link/unlock").respond(
        status_code=200,
        json={"status": "error", "error": {"code": "AUTH_BAD_APIKEY", "message": "Invalid API key"}},
    )
    with pytest.raises(AuthenticationError):
        await resolver.resolve(link)

@pytest.mark.asyncio
@respx.mock
async def test_alldebrid_link_dead():
    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123/sample.rar"
    respx.get("https://api.alldebrid.com/v4/link/unlock").respond(
        status_code=200,
        json={"status": "error", "error": {"code": "LINK_DEAD", "message": "File not found"}},
    )
    with pytest.raises(LinkDeadError):
        await resolver.resolve(link)

@pytest.mark.asyncio
@respx.mock
async def test_alldebrid_host_not_supported():
    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://unknownhost.com/file/123"
    respx.get("https://api.alldebrid.com/v4/link/unlock").respond(
        status_code=200,
        json={"status": "error", "error": {"code": "LINK_HOST_NOT_SUPPORTED", "message": "Host not supported"}},
    )
    with pytest.raises(UnsupportedHosterError):
        await resolver.resolve(link)

@pytest.mark.asyncio
@respx.mock
async def test_alldebrid_rate_limited():
    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    respx.get("https://api.alldebrid.com/v4/link/unlock").respond(
        status_code=200,
        json={"status": "error", "error": {"code": "RATE_LIMITED", "message": "Too many requests"}},
    )
    with pytest.raises(RateLimitError):
        await resolver.resolve(link)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_resolvers_alldebrid.py`  
Expected: FAIL (`ModuleNotFoundError` or `ImportError`).

- [ ] **Step 3: Implement `AllDebridResolver` in `src/apkpipe/resolvers/all_debrid.py`**

Create `src/apkpipe/resolvers/all_debrid.py` and update `src/apkpipe/resolvers/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_resolvers_alldebrid.py`  
Expected: PASS (all 7 tests pass).

- [ ] **Step 5: Commit**

```bash
git add src/apkpipe/resolvers/all_debrid.py src/apkpipe/resolvers/__init__.py tests/test_resolvers_alldebrid.py
git commit -m "feat(resolvers): implement AllDebrid resolver with error mapping and tests"
```

---

### Task 2: ResolutionManager Fallthrough Integration

**Files:**
- Modify: `src/apkpipe/resolvers/manager.py`
- Modify: `tests/test_resolvers.py`

**Interfaces:**
- Consumes: `AllDebridResolver`
- Produces: `ResolutionManager` with peer fallthrough: Real-Debrid $\rightarrow$ AllDebrid $\rightarrow$ JDownloader $\rightarrow$ Direct.

- [ ] **Step 1: Write fallthrough unit & integration tests**

Add tests to `tests/test_resolvers.py`:
- Test Real-Debrid returning `AuthenticationError` automatically falling through to AllDebrid.
- Test Real-Debrid returning `UnsupportedHosterError` falling through to AllDebrid.
- Test AllDebrid `AuthenticationError` falling through to JDownloader/Direct.
- Test `preferred_tier="alldebrid"` executing AllDebrid before Real-Debrid.

- [ ] **Step 2: Run test to verify failure before manager update**

Run: `pytest tests/test_resolvers.py`

- [ ] **Step 3: Update `ResolutionManager` in `src/apkpipe/resolvers/manager.py`**

- Accept `ad_resolver: Optional[AllDebridResolver] = None` in `__init__`.
- Register `self.ad_resolver` in `_get_ordered_resolvers()`.
- Add `AuthenticationError` to caught exceptions in the resolution loop so missing/invalid credentials on one provider seamlessly try subsequent providers.

- [ ] **Step 4: Run tests to verify all resolver tests pass**

Run: `pytest tests/test_resolvers.py tests/test_resolvers_alldebrid.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apkpipe/resolvers/manager.py tests/test_resolvers.py
git commit -m "feat(resolvers): integrate AllDebrid into ResolutionManager with peer fallthrough"
```

---

### Task 3: Backend Settings, Configuration, Database & MCP Tool Updates

**Files:**
- Modify: `src/apkpipe/config.py`
- Modify: `src/apkpipe/api/routes_settings.py`
- Modify: `src/apkpipe/mcp/tools.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_api_routes.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `Settings.alldebrid_api_key`, `Settings.alldebrid_agent`, API endpoints accepting `alldebrid_api_key`, MCP tools supporting `alldebrid`.

- [ ] **Step 1: Write tests for AllDebrid configuration & settings endpoints**

- [ ] **Step 2: Update `config.py`, `routes_settings.py`, and `mcp/tools.py`**

- Add `alldebrid_api_key` and `alldebrid_agent` to `Settings`.
- Update `AppSettings` schema to include `alldebrid_api_key: Optional[str] = None`.
- Update MCP `trigger_manual_download` tool description and tier checks to recognize `alldebrid`.

- [ ] **Step 3: Run pytest on backend settings and MCP tests**

Run: `pytest tests/test_config.py tests/test_api_routes.py tests/test_mcp_server.py`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/apkpipe/config.py src/apkpipe/api/routes_settings.py src/apkpipe/mcp/tools.py tests/test_config.py tests/test_api_routes.py tests/test_mcp_server.py
git commit -m "feat(config): add AllDebrid settings and MCP tool tier support"
```

---

### Task 4: React SPA UI Updates & End-to-End Verification

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/common/Badge.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/components/modals/ManualDownloadModal.tsx`

**Interfaces:**
- Produces: React SPA Settings page with AllDebrid API key card, `alldebrid` tier badge styling, and manual download selector option.

- [ ] **Step 1: Update TypeScript types in `frontend/src/api/types.ts`**
  - Add `alldebrid_api_key?: string;` to `AppSettings`.
  - Add `'alldebrid'` to `ResolverTier` union type.

- [ ] **Step 2: Update `Badge.tsx`**
  - Add violet/purple badge styling and icon for `alldebrid` tier.

- [ ] **Step 3: Update `Settings.tsx`**
  - Add **AllDebrid Resolver (Tier 1b)** settings card with show/hide password toggle, description, and link to `https://alldebrid.com/apikeys/`.

- [ ] **Step 4: Update `ManualDownloadModal.tsx`**
  - Add `<option value="alldebrid">AllDebrid (Tier 1b)</option>` to the Tier Preference dropdown.

- [ ] **Step 5: Run frontend typecheck and build**

```bash
cd frontend && npm run typecheck && npm run build
```
Expected: 0 errors, clean production bundle in `frontend/dist/`.

- [ ] **Step 6: Run full backend test suite with coverage**

```bash
pytest --cov=src/apkpipe tests/
```
Expected: All tests pass with $\ge 80\%$ coverage.

- [ ] **Step 7: Commit UI updates**

```bash
git add frontend/
git commit -m "feat(frontend): add AllDebrid settings, badges, and manual download options"
```
