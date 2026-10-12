"""CF-Server-Monitor discovery plus a persistent heartbeat subscription."""

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests


@dataclass(frozen=True)
class ProbeNode:
    id: str
    name: str
    report_age_seconds: float
    report_at_ms: int
    report_interval_seconds: int


def parse_probe_payload(payload: dict, now_ms: int | None = None) -> dict[str, ProbeNode]:
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    servers = {
        str(server.get("id", "")): server
        for server in payload.get("servers", [])
        if server.get("id")
    }
    updates = {
        str(update.get("serverId", "")): update
        for update in payload.get("latestReportUpdates", [])
        if update.get("serverId")
    }
    nodes: dict[str, ProbeNode] = {}
    for node_id, server in servers.items():
        update = updates.get(node_id, {})
        report_at_ms = int(update.get("reportTs") or server.get("last_updated") or 0)
        raw_age = update.get("reportAgeMs")
        age_ms = int(raw_age) if raw_age is not None else max(0, now_ms - report_at_ms)
        nodes[node_id] = ProbeNode(
            id=node_id,
            name=str(server.get("name") or node_id).strip(),
            report_age_seconds=max(0, age_ms) / 1000,
            report_at_ms=report_at_ms,
            report_interval_seconds=max(1, int(server.get("report_interval") or 60)),
        )
    return nodes


def fetch_probe_nodes(api_url: str, timeout_seconds: int = 20) -> dict[str, ProbeNode]:
    response = requests.get(
        api_url,
        headers={"Accept": "application/json", "User-Agent": "ACLClouds-Online-Keeper"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Probe API returned an invalid JSON document.")
    return parse_probe_payload(payload)

def websocket_url(api_url: str, node_ids: list[str] | tuple[str, ...]) -> str:
    parsed = urlsplit(api_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    scope = node_ids[0] if len(node_ids) == 1 else "all"
    return urlunsplit((scheme, parsed.netloc, "/api/ws", urlencode({"subscribe": scope}), ""))


class HeartbeatMonitor:
    """Maintain the same public WebSocket subscription used by the probe frontend."""

    def __init__(self, api_url: str):
        self.api_url = api_url
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._node_ids: tuple[str, ...] = ()
        self._heartbeats: dict[str, datetime] = {}
        self._subscribed_since: dict[str, datetime] = {}
        self._connected = False
        self._last_message_at: datetime | None = None
        self._last_error = ""
        self._ws = None
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="probe-heartbeat", daemon=True
        )
        self._thread.start()

    def update_ids(self, node_ids):
        cleaned = tuple(sorted({str(item).strip() for item in node_ids if str(item).strip()}))
        now = datetime.now(timezone.utc)
        with self._lock:
            if cleaned == self._node_ids:
                return
            old = set(self._node_ids)
            self._node_ids = cleaned
            for node_id in cleaned:
                if node_id not in old:
                    self._subscribed_since[node_id] = now
            for node_id in set(self._subscribed_since) - set(cleaned):
                self._subscribed_since.pop(node_id, None)
                self._heartbeats.pop(node_id, None)
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        self._wake.set()

    def ingest_message(self, raw_message: str):
        try:
            payload = json.loads(raw_message)
        except (TypeError, ValueError):
            return
        if payload.get("type") != "batchUpdate" or not isinstance(payload.get("updates"), list):
            return
        now = datetime.now(timezone.utc)
        seen = []
        for update in payload["updates"]:
            if not isinstance(update, dict) or not isinstance(update.get("samples"), list):
                continue
            node_id = str(update.get("serverId") or "").strip()
            if node_id and update["samples"]:
                seen.append(node_id)
        if not seen:
            return
        with self._lock:
            self._last_message_at = now
            for node_id in seen:
                if node_id in self._node_ids:
                    self._heartbeats[node_id] = now

    def snapshot(self):
        with self._lock:
            return {
                "node_ids": self._node_ids,
                "heartbeats": dict(self._heartbeats),
                "subscribed_since": dict(self._subscribed_since),
                "connected": self._connected,
                "last_message_at": self._last_message_at,
                "last_error": self._last_error,
            }

    def _on_open(self, ws):
        with self._lock:
            self._connected = True
            self._last_error = ""
            node_ids = list(self._node_ids)
        scope = node_ids[0] if len(node_ids) == 1 else "all"
        ws.send(json.dumps({"type": "subscribe", "scope": scope, "ids": node_ids}))

    def _on_close(self, _ws, _code, reason):
        with self._lock:
            self._connected = False
            if reason:
                self._last_error = str(reason)

    def _on_error(self, _ws, error):
        with self._lock:
            self._connected = False
            self._last_error = str(error)

    def _run(self):
        import websocket

        backoff = 1
        while True:
            with self._lock:
                node_ids = self._node_ids
            if not node_ids:
                self._wake.wait(5)
                self._wake.clear()
                continue
            app = websocket.WebSocketApp(
                websocket_url(self.api_url, node_ids),
                on_open=self._on_open,
                on_message=lambda _ws, message: self.ingest_message(message),
                on_error=self._on_error,
                on_close=self._on_close,
            )
            with self._lock:
                self._ws = app
            try:
                app.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as exc:
                self._on_error(app, exc)
            finally:
                with self._lock:
                    if self._ws is app:
                        self._ws = None
                    self._connected = False
            self._wake.wait(backoff)
            self._wake.clear()
            backoff = min(30, backoff * 2)
