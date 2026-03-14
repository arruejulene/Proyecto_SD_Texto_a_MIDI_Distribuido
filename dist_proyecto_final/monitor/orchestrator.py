# monitor/orchestrator.py
from __future__ import annotations

import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable

from network.protocol import decode_message, encode_message
from .store import MonitorStore


class MonitorOrchestrator:
    def __init__(self, host: str, port: int, corpus_dir: Path) -> None:
        self.host = host
        self.port = port
        self.corpus_dir = corpus_dir
        self.store = MonitorStore()
        self.socket: socket.socket | None = None
        self.listener_thread: threading.Thread | None = None
        self.connected = False
        self._lock = threading.Lock()
        self._acks: dict[str, dict] = {}

    def connect(self) -> bool:
        with self._lock:
            if self.connected and self.socket:
                return True
            self.close()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            try:
                sock.connect((self.host, self.port))
                sock.settimeout(None)
                sock.sendall(encode_message({"type": "REGISTER", "client_name": "monitor"}))
            except OSError:
                try:
                    sock.close()
                except OSError:
                    pass
                self.connected = False
                self.socket = None
                return False
            self.socket = sock
            self.connected = True
            self.listener_thread = threading.Thread(target=self._listen, daemon=True)
            self.listener_thread.start()
            self.store.push_system("Director conectado al relay server", host=self.host, port=self.port)
            return True

    def ensure_connected(self) -> bool:
        return self.connect()

    def close(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None
        self.connected = False

    def _send_private(self, client_name: str, payload: dict) -> str:
        if not self.ensure_connected() or not self.socket:
            raise RuntimeError("Monitor no conectado")
        message_id = str(payload.get("message_id") or uuid.uuid4().hex)
        payload["message_id"] = message_id
        self.socket.sendall(encode_message({"type": "PRIVATE", "to": client_name, "payload": payload}))
        self.store.push_system(
            f"Enviado {payload.get('command', 'payload')} a {client_name}",
            target=client_name,
            message_id=message_id,
        )
        return message_id

    def _send_broadcast(self, payload: dict) -> str:
        if not self.ensure_connected() or not self.socket:
            raise RuntimeError("Monitor no conectado")
        message_id = str(payload.get("message_id") or uuid.uuid4().hex)
        payload["message_id"] = message_id
        self.socket.sendall(encode_message({"type": "BROADCAST", "payload": payload}))
        self.store.push_system(f"Broadcast {payload.get('command', 'payload')} emitido", message_id=message_id)
        return message_id

    def _listen(self) -> None:
        sock = self.socket
        if sock is None:
            return
        buffer = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except OSError:
                self.connected = False
                self.store.push_system("Director desconectado del relay server")
                break
            if not chunk:
                self.connected = False
                self.store.push_system("Relay server no disponible")
                break
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if not raw.strip():
                    continue
                message = decode_message(raw)
                msg_type = message.get("type")
                if msg_type == "SYSTEM":
                    self.store.push_system(str(message.get("message") or "Evento del sistema"))
                    continue
                if msg_type == "ACK":
                    self._acks[str(message.get("message_id"))] = message
                    self.store.push_system(
                        f"ACK recibido para {message.get('message_id')}",
                        ack_target=message.get("target"),
                        message_id=message.get("message_id"),
                    )
                    continue
                if msg_type == "ERROR":
                    self.store.push_system(str(message.get("message") or "Error del relay"), message_id=message.get("message_id"))
                    continue
                if msg_type != "DELIVERED":
                    continue
                payload = message.get("payload", {})
                payload.setdefault("from", message.get("from"))
                self.store.add_event(payload)

    def configure_run(self, assignments: Iterable[dict]) -> None:
        sent = 0
        for item in assignments:
            file_name = item["file_name"]
            target = item["processor"]
            bpm = int(item.get("bpm", 120))
            path = (self.corpus_dir / file_name).resolve()
            if not path.exists():
                raise FileNotFoundError(f"No existe {file_name}")
            self._send_private(
                target,
                {
                    "command": "CONFIGURE",
                    "file_path": str(path),
                    "bpm": bpm,
                    "sent_at": time.time(),
                },
            )
            sent += 1
        self.store.push_system(f"Director envió {sent} configuración(es)")

    def start_run(self) -> None:
        self._send_broadcast({"command": "START", "sent_at": time.time()})
        self.store.push_system("Director lanzó START a todos los clientes")
