"""Bright Data MCP client for scraping and search."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _load_token() -> str:
    token = os.environ.get("BRIGHTDATA_API_TOKEN") or os.environ.get("API_TOKEN")
    if token:
        return token
    mcp_path = Path(__file__).resolve().parent / ".cursor" / "mcp.json"
    if mcp_path.exists():
        config = json.loads(mcp_path.read_text())
        url = config.get("mcpServers", {}).get("brightdata", {}).get("url", "")
        match = re.search(r"token=([^&]+)", url)
        if match:
            return match.group(1)
    raise RuntimeError(
        "Bright Data API token not found. Set BRIGHTDATA_API_TOKEN or configure .cursor/mcp.json"
    )


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in re.split(r"\n\n+", text.strip()):
        data = None
        for line in block.split("\n"):
            if line.startswith("data: "):
                data = line[6:]
        if data:
            events.append(json.loads(data))
    return events


class BrightDataClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or _load_token()
        self.base_url = f"https://mcp.brightdata.com/mcp?token={self.token}"
        self.session_id: str | None = None
        self._rpc_id = 0

    def _rpc(self, method: str, params: dict[str, Any] | None = None, *, _retried: bool = False) -> list[dict[str, Any]]:
        self._rpc_id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": self._rpc_id, "method": method}
        if params is not None:
            body["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(body).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                if not self.session_id:
                    self.session_id = response.headers.get("Mcp-Session-Id")
                return _parse_sse(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410) and method != "initialize" and not _retried:
                self.reconnect()
                return self._rpc(method, params, _retried=True)
            raise

    def connect(self) -> None:
        self.session_id = None
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "price-tracker", "version": "1.0"},
            },
        )
        self._rpc("notifications/initialized", {})

    def reconnect(self) -> None:
        self.connect()

    def _tool_text(self, name: str, arguments: dict[str, Any]) -> str:
        events = self._rpc("tools/call", {"name": name, "arguments": arguments})
        for event in events:
            if "error" in event:
                raise RuntimeError(event["error"].get("message", str(event["error"])))
            result = event.get("result", {})
            content = result.get("content", [])
            if content:
                return content[0].get("text", "")
        return ""

    def scrape(self, url: str) -> str:
        return self._tool_text("scrape_as_markdown", {"url": url})

    def scrape_batch(self, urls: list[str]) -> dict[str, str]:
        if not urls:
            return {}
        events = self._rpc(
            "tools/call",
            {"name": "scrape_batch", "arguments": {"urls": urls}},
        )
        text = ""
        for event in events:
            result = event.get("result", {})
            content = result.get("content", [])
            if content:
                text = content[0].get("text", "")
        if not text:
            return {}
        # Response may be wrapped in security markers as JSON array string
        text = strip_security_markers(text)
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            return {urls[0]: text} if len(urls) == 1 else {}
        return {item.get("url", ""): item.get("content", "") for item in items}

    def search(self, query: str, geo_location: str = "us") -> list[dict[str, str]]:
        text = self._tool_text(
            "search_engine",
            {"query": query, "engine": "google", "geo_location": geo_location},
        )
        text = strip_security_markers(text)
        try:
            data = json.loads(text)
            return data.get("organic", [])
        except json.JSONDecodeError:
            return []

    def search_batch(self, queries: list[str], geo_location: str = "us") -> dict[str, list[dict[str, str]]]:
        events = self._rpc(
            "tools/call",
            {
                "name": "search_engine_batch",
                "arguments": {
                    "queries": [{"query": q, "engine": "google", "geo_location": geo_location} for q in queries]
                },
            },
        )
        text = ""
        for event in events:
            result = event.get("result", {})
            content = result.get("content", [])
            if content:
                text = content[0].get("text", "")
        text = strip_security_markers(text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {q: [] for q in queries}
        if isinstance(data, list):
            out: dict[str, list[dict[str, str]]] = {}
            for i, q in enumerate(queries):
                item = data[i] if i < len(data) else {}
                if isinstance(item, dict) and "organic" in item:
                    out[q] = item["organic"]
                elif isinstance(item, list):
                    out[q] = item
                else:
                    out[q] = []
            return out
        if isinstance(data, dict) and "organic" in data and len(queries) == 1:
            return {queries[0]: data["organic"]}
        return {q: data.get(q, []) if isinstance(data.get(q), list) else [] for q in queries}


def strip_security_markers(text: str) -> str:
    if not text:
        return ""
    text = re.sub(
        r"SECURITY NOTICE:.*?=====UNTRUSTED_[a-f0-9]+_BEGIN=====\n?",
        "",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"=====UNTRUSTED_[a-f0-9]+_BEGIN=====\n?", "", text)
    text = re.sub(r"\n?=====UNTRUSTED_[a-f0-9]+_END=====", "", text)
    return text.strip()
