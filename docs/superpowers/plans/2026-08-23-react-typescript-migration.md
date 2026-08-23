# React & TypeScript SPA Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the APKPipe Web UI from server-rendered Jinja2/Alpine.js templates to a modern, fully-typed React 18 + TypeScript + Vite Single Page Application (SPA) with TanStack Query for 5s real-time queue polling, Zustand for client state, and a custom Toast notification system, served directly by FastAPI.

**Architecture:** A standalone `frontend/` Vite workspace builds static assets into `frontend/dist/`. FastAPI serves the compiled SPA with HTML5 History fallback routing for client-side paths (`/`, `/watchlist`, `/feeds`, `/history`, `/settings`), while preserving existing `/api/*` REST endpoints and `/mcp/*` tools. In development, Vite reverse-proxies API requests to `:8000`.

**Tech Stack:** React 18/19, TypeScript 5.x, Vite 6.x, Tailwind CSS, Lucide React, TanStack Query (`@tanstack/react-query`), Zustand, FastAPI `StaticFiles`.

## Global Constraints

- Backend REST API endpoints under `/api/*`, `/health`, and `/mcp/*` must not have breaking changes.
- All 305 existing Python test suite cases must continue to pass with ≥ 80% coverage.
- TypeScript compiler checks (`tsc --noEmit`) must complete with 0 errors.
- Production container must remain a single Docker container serving both the API and the compiled SPA.

---

### Task 1: Frontend Workspace Initialization & Build Tooling

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/index.css`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

**Interfaces:**
- Produces: Working Vite build producing `frontend/dist/index.html` and assets.
- Scripts: `npm run build`, `npm run dev`, `npm run typecheck`.

- [ ] **Step 1: Create frontend workspace configuration files**

Create `frontend/package.json`:
```json
{
  "name": "apkpipe-frontend",
  "private": true,
  "version": "0.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.28.0",
    "clsx": "^2.1.0",
    "lucide-react": "^0.359.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "tailwind-merge": "^2.2.2",
    "zustand": "^4.5.2"
  },
  "devDependencies": {
    "@types/react": "^18.2.66",
    "@types/react-dom": "^18.2.22",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.4.2",
    "vite": "^5.1.6"
  }
}
```

Create `frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": false,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

Create `frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/mcp': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

Create `frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          950: '#0b0f19',
        },
      },
    },
  },
  plugins: [],
}
```

Create `frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

Create `frontend/index.html`:
```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%236366f1'><path d='M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'/></svg>" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>APKPipe - Automated Release Pipeline</title>
  </head>
  <body class="bg-slate-950 text-slate-100 antialiased min-h-screen">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer utilities {
  .glass-panel {
    background: rgba(15, 23, 42, 0.7);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
  }
}
```

Create `frontend/src/App.tsx`:
```tsx
export default function App() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-white">APKPipe React SPA</h1>
    </div>
  );
}
```

Create `frontend/src/main.tsx`:
```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.tsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 2: Install dependencies and build bundle**

Run in `frontend/`:
```bash
npm install
npm run build
```
Verify `frontend/dist/index.html` exists and `npm run typecheck` exits with 0.

- [ ] **Step 3: Commit initial frontend workspace**

```bash
git add frontend/
git commit -m "feat(frontend): initialize Vite + React + TypeScript workspace"
```

---

### Task 2: TypeScript Interfaces, API Client & TanStack Query Hooks

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/useWatchlist.ts`
- Create: `frontend/src/api/useFeeds.ts`
- Create: `frontend/src/api/useDownloads.ts`
- Create: `frontend/src/api/useSettings.ts`

**Interfaces:**
- Produces: Typed functions & TanStack Query hooks:
  - `useWatchlistQuery()`, `useCreateWatchlistMutation()`, `useUpdateWatchlistMutation()`, `useDeleteWatchlistMutation()`, `useToggleWatchlistMutation()`
  - `useFeedsQuery()`, `useCreateFeedMutation()`, `useUpdateFeedMutation()`, `useDeleteFeedMutation()`, `usePollSingleFeedMutation()`, `usePollAllFeedsMutation()`
  - `useQueueQuery(pollingIntervalMs)`, `useHistoryQuery()`, `useManualDownloadMutation()`, `useRetryDownloadMutation()`, `useCancelDownloadMutation()`
  - `useSettingsQuery()`, `useUpdateSettingsMutation()`, `useSystemStatusQuery()`

- [ ] **Step 1: Write `frontend/src/api/types.ts`**

```typescript
export interface WatchlistItem {
  id: number;
  app_name: string;
  package_name?: string | null;
  title_regex?: string | null;
  min_version?: string | null;
  releaser_whitelist: string[];
  releaser_blacklist: string[];
  category: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItemCreate {
  app_name: string;
  package_name?: string | null;
  title_regex?: string | null;
  min_version?: string | null;
  releaser_whitelist?: string[];
  releaser_blacklist?: string[];
  category?: string;
  enabled?: boolean;
}

export interface FeedSource {
  id: number;
  name: string;
  url: string;
  feed_type: string;
  enabled: boolean;
  poll_interval_minutes: number;
  last_polled_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedSourceCreate {
  name: string;
  url: string;
  feed_type?: string;
  enabled?: boolean;
  poll_interval_minutes?: number;
}

export interface DownloadTask {
  id: number;
  watchlist_item_id?: number | null;
  feed_item_title: string;
  feed_item_url?: string | null;
  matched_version?: string | null;
  matched_releaser?: string | null;
  status: 'pending' | 'resolving' | 'downloading' | 'completed' | 'failed';
  download_tier?: 'real_debrid' | 'jdownloader' | 'direct' | null;
  resolved_url?: string | null;
  file_path?: string | null;
  file_size: number;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface DownloadHistory {
  id: number;
  task_id?: number | null;
  app_name: string;
  version?: string | null;
  releaser?: string | null;
  target_path: string;
  file_size: number;
  duration_seconds: number;
  download_tier?: string | null;
  status: string;
  downloaded_at: string;
}

export interface ManualDownloadRequest {
  url: string;
  app_name?: string;
  version?: string;
  releaser?: string;
  download_tier?: string;
}

export interface AppSettings {
  app_name: string;
  host: string;
  port: number;
  debug: boolean;
  database_url: string;
  download_dir: string;
  staging_dir: string;
  poll_interval_seconds: number;
  real_debrid_api_token: string;
  jdownloader_email: string;
  jdownloader_password?: string;
  jdownloader_device_name: string;
  jdownloader_watch_dir: string;
  scraper_url: string;
  nextcloud_url: string;
  nextcloud_token?: string;
  nextcloud_occ_command: string;
  apprise_url: string;
  ntfy_topic: string;
}

export interface HealthStatus {
  status: string;
  version: string;
  active_tasks: number;
}
```

- [ ] **Step 2: Write `frontend/src/api/client.ts`**

```typescript
export class ApiError extends Error {
  constructor(public status: number, message: string, public data?: any) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(endpoint, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let errorMsg = `Request failed with status ${res.status}`;
    let errorData;
    try {
      errorData = await res.json();
      if (errorData?.detail) errorMsg = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
      else if (errorData?.message) errorMsg = errorData.message;
    } catch {
      // ignore json parse error
    }
    throw new ApiError(res.status, errorMsg, errorData);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return res.json();
}
```

- [ ] **Step 3: Write Query and Mutation hooks (`useWatchlist.ts`, `useFeeds.ts`, `useDownloads.ts`, `useSettings.ts`)**

Write hooks utilizing `@tanstack/react-query` to interact with `/api/watchlist`, `/api/feeds`, `/api/downloads`, `/api/settings`, and `/health`.

- [ ] **Step 4: Verify typecheck**

Run in `frontend/`:
```bash
npm run typecheck
```

- [ ] **Step 5: Commit API layer**

```bash
git add frontend/src/api/
git commit -m "feat(frontend): add typed API client and TanStack Query hooks"
```

---

### Task 3: Zustand Stores & Toast Notification System

**Files:**
- Create: `frontend/src/stores/useToastStore.ts`
- Create: `frontend/src/stores/useUIStore.ts`
- Create: `frontend/src/components/common/ToastContainer.tsx`

**Interfaces:**
- Produces:
  - `useToastStore`: `addToast({ type, title, message, duration? })`, `removeToast(id)`
  - `useUIStore`: `isManualModalOpen`, `setManualModalOpen(open)`, `activeTab`, `setActiveTab(tab)`, persistent preferences in localStorage (`autoRefreshQueue`, `queueInterval`)
  - `ToastContainer`: Renders fixed top-right notification stack with smooth fade-in/out animations.

- [ ] **Step 1: Write `frontend/src/stores/useToastStore.ts`**

```typescript
import { create } from 'zustand';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message?: string;
  duration?: number;
}

interface ToastState {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => string;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9);
    const duration = toast.duration ?? 4000;
    
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }));

    if (duration > 0) {
      setTimeout(() => {
        set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
      }, duration);
    }
    return id;
  },
  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));
```

- [ ] **Step 2: Write `frontend/src/stores/useUIStore.ts`**

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UIState {
  manualModalOpen: boolean;
  setManualModalOpen: (open: boolean) => void;
  autoRefreshQueue: boolean;
  setAutoRefreshQueue: (enabled: boolean) => void;
  queuePollingInterval: number;
  setQueuePollingInterval: (interval: number) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      manualModalOpen: false,
      setManualModalOpen: (open) => set({ manualModalOpen: open }),
      autoRefreshQueue: true,
      setAutoRefreshQueue: (enabled) => set({ autoRefreshQueue: enabled }),
      queuePollingInterval: 5000,
      setQueuePollingInterval: (interval) => set({ queuePollingInterval: interval }),
    }),
    {
      name: 'apkpipe-ui-storage',
      partialize: (state) => ({
        autoRefreshQueue: state.autoRefreshQueue,
        queuePollingInterval: state.queuePollingInterval,
      }),
    }
  )
);
```

- [ ] **Step 3: Write `frontend/src/components/common/ToastContainer.tsx`**

Implement animated toast notification container with Lucide icons (CheckCircle, AlertCircle, Info, AlertTriangle, X).

- [ ] **Step 4: Verify typecheck**

Run: `npm run typecheck`

- [ ] **Step 5: Commit Toast & Zustand layer**

```bash
git add frontend/src/stores/ frontend/src/components/common/ToastContainer.tsx
git commit -m "feat(frontend): add Zustand UI store and Toast notification system"
```

---

### Task 4: Shared Design System & Navigation Layout

**Files:**
- Create: `frontend/src/components/common/Badge.tsx`
- Create: `frontend/src/components/common/Modal.tsx`
- Create: `frontend/src/components/common/StatCard.tsx`
- Create: `frontend/src/components/common/ConfirmDialog.tsx`
- Create: `frontend/src/components/layout/Navbar.tsx`
- Create: `frontend/src/components/layout/Layout.tsx`

**Interfaces:**
- Produces: Reusable navigation bar with active route highlighting, health pulse indicator, manual download trigger button, and responsive layout wrapper.

- [ ] **Step 1: Create reusable primitives**
  - Implement `Badge.tsx` with color variants for pipeline statuses (`pending`, `resolving`, `downloading`, `completed`, `failed`) and resolver tiers (`real_debrid`, `jdownloader`, `direct`).
  - Implement `Modal.tsx` with backdrop blur, exit transitions, and escape key listener.
  - Implement `StatCard.tsx` with icon slot, value, subtitle, and link.
  - Implement `ConfirmDialog.tsx` for deletion confirmations.

- [ ] **Step 2: Implement `Navbar.tsx` and `Layout.tsx`**
  - Navigation links to Dashboard (`/`), Watchlist (`/watchlist`), Feeds (`/feeds`), Queue & History (`/history`), and Settings (`/settings`).
  - Embed `ToastContainer.tsx` in `Layout.tsx`.

- [ ] **Step 3: Verify typecheck**

Run: `npm run typecheck`

- [ ] **Step 4: Commit UI components & Layout**

```bash
git add frontend/src/components/
git commit -m "feat(frontend): implement shared design system and navigation layout"
```

---

### Task 5: Dashboard & Watchlist Pages

**Files:**
- Create: `frontend/src/components/modals/ManualDownloadModal.tsx`
- Create: `frontend/src/components/modals/WatchlistModal.tsx`
- Create: `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/src/pages/Watchlist.tsx`

**Interfaces:**
- Produces:
  - `Dashboard.tsx`: Metric cards, Live activity table, recent ingests, manual download action.
  - `Watchlist.tsx`: Search/filter input, category selector, status toggle, application CRUD table with modal.

- [ ] **Step 1: Write `ManualDownloadModal.tsx`**
  - Supports URL input, optional App Name, Version, Releaser, and Tier preference selector.
  - Dispatches `POST /api/downloads/manual` and emits success toast.

- [ ] **Step 2: Write `Dashboard.tsx`**
  - Fetches watchlist, feeds, history, and system status via TanStack Query.
  - Renders quick metric cards, active tasks preview, and recent 5 ingests.

- [ ] **Step 3: Write `WatchlistModal.tsx` and `Watchlist.tsx`**
  - Add and Edit mode with field validation for regex, version threshold, comma-separated whitelists/blacklists.
  - Interactive search filtering and instant toggle switch mutations with toast feedback.

- [ ] **Step 4: Verify typecheck**

Run: `npm run typecheck`

- [ ] **Step 5: Commit Dashboard & Watchlist**

```bash
git add frontend/src/components/modals/ frontend/src/pages/Dashboard.tsx frontend/src/pages/Watchlist.tsx
git commit -m "feat(frontend): implement Dashboard and Watchlist pages with modals"
```

---

### Task 6: Feeds, Queue & History, Settings Pages & Router Setup

**Files:**
- Create: `frontend/src/components/modals/FeedModal.tsx`
- Create: `frontend/src/pages/Feeds.tsx`
- Create: `frontend/src/pages/History.tsx`
- Create: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces:
  - `Feeds.tsx`: Feed sources list, manual poll trigger buttons with spinner states, and Add/Edit Feed modal.
  - `History.tsx`: Dual-tab view for active queue (with 5s live polling) and audit history, retry button for failed downloads.
  - `Settings.tsx`: Form for Real-Debrid token, JDownloader, Scraper, Nextcloud OCC, and Apprise/Ntfy with instant save toasts.
  - `App.tsx`: React Router setup with QueryClientProvider wrapping all 5 routes.

- [ ] **Step 1: Write `FeedModal.tsx` and `Feeds.tsx`**
  - Feed name, URL, feed type selector (`mobilism_rss`, `generic_rss`, `atom`), poll interval in minutes.
  - "Poll Now" and "Poll All Feeds Now" mutation triggers with instant toast alerts.

- [ ] **Step 2: Write `History.tsx`**
  - Tabbed interface between "Active Queue" and "Completed History".
  - Live auto-refresh switch connected to `useUIStore`.
  - Display task IDs, resolver tier badges, file sizes, duration formatting, and retry action.

- [ ] **Step 3: Write `Settings.tsx`**
  - Structured into General, Real-Debrid, JDownloader, Nextcloud/Scraper, and Notifications sections.
  - Show/hide password toggles for tokens and API keys.

- [ ] **Step 4: Update `App.tsx` with Router**
  - Implement client-side routing matching current paths (`/`, `/watchlist`, `/feeds`, `/history`, `/settings`).

- [ ] **Step 5: Verify build & typecheck**

Run in `frontend/`:
```bash
npm run typecheck
npm run build
```
Verify `frontend/dist/` contains production assets.

- [ ] **Step 6: Commit all SPA pages & router**

```bash
git add frontend/src/
git commit -m "feat(frontend): implement Feeds, History, Settings pages and complete SPA router"
```

---

### Task 7: FastAPI Static SPA Serving & Fallback Routing

**Files:**
- Modify: `src/apkpipe/main.py`
- Modify: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: `frontend/dist/` bundle.
- Produces: FastAPI app that mounts `frontend/dist/` static files and returns `index.html` for all SPA routes while keeping `/api/*`, `/health`, and `/mcp/*` active.

- [ ] **Step 1: Write test for SPA static serving & fallback**

Update `tests/test_web_ui.py`:
```python
import pytest
import httpx
from apkpipe.main import create_app

@pytest.mark.asyncio
async def test_spa_routes_serve_index():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for path in ["/", "/watchlist", "/feeds", "/history", "/settings"]:
            resp = await client.get(path)
            assert resp.status_code == 200
            assert "text/html" in resp.headers["content-type"]
            assert "APKPipe" in resp.text
```

- [ ] **Step 2: Update `src/apkpipe/main.py`**

Mount `frontend/dist` static assets and HTML fallback handler for client routes:
```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, HTMLResponse

# In create_app():
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if not frontend_dist.exists():
    # Fallback to internal container path
    frontend_dist = Path("/app/frontend/dist")

if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API / docs routes
        if full_path.startswith(("api/", "health", "mcp", "docs", "openapi.json")):
            return HTMLResponse(status_code=404, content="Not found")
        file_target = frontend_dist / full_path
        if file_target.is_file():
            return FileResponse(file_target)
        return FileResponse(frontend_dist / "index.html")
```

- [ ] **Step 3: Run pytest test suite**

Run: `pytest tests/test_web_ui.py`
Run: `pytest --cov=src/apkpipe tests/`
Verify all 305+ tests pass with ≥ 80% coverage.

- [ ] **Step 4: Commit backend SPA serving integration**

```bash
git add src/apkpipe/main.py tests/test_web_ui.py
git commit -m "feat(backend): serve compiled React SPA with HTML5 fallback routing"
```

---

### Task 8: Production Multi-Stage Dockerfile & End-to-End Verification

**Files:**
- Modify: `Dockerfile`

**Interfaces:**
- Produces: Single Docker container image building React SPA in Stage 1, building Python packages in Stage 2, and running lightweight Python runtime serving API & SPA in Stage 3.

- [ ] **Step 1: Update `Dockerfile` with multi-stage Node + Python build**

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: Build React/TypeScript Frontend
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Python Dependencies
FROM python:3.12-slim AS python-builder
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

# Stage 3: Production Runtime
FROM python:3.12-slim AS runner
LABEL org.opencontainers.image.title="APKPipe" org.opencontainers.image.authors="Steve Pelech"
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" PYTHONPATH="/app/src" \
    APKPIPE_DOWNLOAD_DIR="/downloads" APKPIPE_STAGING_DIR="/data/staging" \
    APKPIPE_DATABASE_URL="sqlite+aiosqlite:////data/apkpipe.db" \
    APKPIPE_HOST="0.0.0.0" APKPIPE_PORT="8000"

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates p7zip-full unrar-free tini && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 1000 apkpipe && useradd -u 1000 -g apkpipe -d /data -s /bin/sh apkpipe

COPY --from=python-builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=apkpipe:apkpipe src/ /app/src/
COPY --chown=apkpipe:apkpipe --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY --chown=apkpipe:apkpipe pyproject.toml README.md /app/

RUN mkdir -p /data /data/staging /downloads && chown -R apkpipe:apkpipe /data /downloads /app
USER apkpipe
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "apkpipe.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Full System Verification**
  1. Frontend: `cd frontend && npm run typecheck && npm run build`
  2. Backend: `pytest --cov=src/apkpipe tests/`
  3. Git status: clean working tree.

- [ ] **Step 3: Commit Dockerfile update**

```bash
git add Dockerfile
git commit -m "feat(docker): add multi-stage build compiling React frontend into runtime image"
```
