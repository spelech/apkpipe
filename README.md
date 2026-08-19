# APKPipe

Automated APK & RSS media pipeline with Real-Debrid, JDownloader fallback, Nextcloud ingestion, Web UI, and MCP server.

## Features
- **RSS Feed Monitoring**: Automate APK and media discovery with flexible regex matching and version comparison.
- **Multi-Downloader Engine**: Seamless Real-Debrid unrestrictor with automatic JDownloader fallback.
- **Nextcloud Ingestion**: Direct WebDAV integration for uploading and structuring downloaded assets.
- **FastAPI Backend & Modern Web UI**: Responsive management dashboard and real-time event logs.
- **MCP Server**: Model Context Protocol integration for AI agent control.

## Installation & Development

```bash
# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
pip install -e .

# Run test suite
pytest
```
