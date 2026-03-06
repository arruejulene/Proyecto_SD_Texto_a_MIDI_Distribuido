from __future__ import annotations

import socket
import threading
import time
import uuid
from typing import Dict

from .protocol import decode_message, encode_message

HOST = "0.0.0.0"
PORT = 5050


class RelayServer:
    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self.host = host
        self.port = port
        self.server_socket: socket.socket | None = None
        self.clients: Dict[str, socket.socket] = {}
        self.lock = threading.Lock()
        self.running = False

    def _log(self, message: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] [relay] {message}")

    def _send(self, conn: socket.socket, payload: dict) -> None:
        conn.sendall(encode_message(payload))

    def _broadcast(self, payload: dict, exclude: str | None = None) -> None:
        dead: list[str] = []
        with self.lock:
            for name, conn in self.clients.items():
                if name == exclude:
                    continue
                try:
                    self._send(conn, payload)
                except OSError:
                    dead.append(name)
            for name in dead:
                self._log(f"Descartando cliente inactivo: {name}")
                self._drop_client(name)

    def _drop_client(self, name: str) -> None:
        conn = self.clients.pop(name, None)
        if conn:
            try:
                conn.close()
            except OSError:
                pass

    def _unique_name(self, requested_name: str) -> str:
        if requested_name not in self.clients:
            return requested_name
        suffix = 2
        while f"{requested_name}-{suffix}" in self.clients:
            suffix += 1
        return f"{requested_name}-{suffix}"

    def _handle_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        client_name: str | None = None
        buffer = b""
        try:
            while self.running:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    if not raw.strip():
                        continue
                    message = decode_message(raw)
                    msg_type = message.get("type")

                    if msg_type == "REGISTER":
                        requested_name = str(message.get("client_name") or f"client-{addr[1]}")
                        with self.lock:
                            final_name = self._unique_name(requested_name)
                            self.clients[final_name] = conn
                        client_name = final_name
                        self._send(conn, {"type": "REGISTERED", "client_name": final_name})
                        self._log(f"Cliente registrado: {final_name} desde {addr[0]}:{addr[1]}")
                        self._broadcast({"type": "SYSTEM", "message": f"{final_name} conectado"}, exclude=final_name)
                        continue

                    if msg_type == "PRIVATE":
                        target = str(message.get("to") or "")
                        payload = message.get("payload", {})
                        message_id = str(payload.get("message_id") or uuid.uuid4().hex)
                        payload["message_id"] = message_id
                        with self.lock:
                            target_conn = self.clients.get(target)
                        if target_conn:
                            try:
                                self._send(
                                    target_conn,
                                    {
                                        "type": "DELIVERED",
                                        "from": client_name,
                                        "payload": payload,
                                    },
                                )
                                self._send(conn, {"type": "ACK", "message_id": message_id, "target": target})
                                self._log(f"PRIVATE {client_name} -> {target} ({payload.get('command', 'payload')}) id={message_id}")
                            except OSError:
                                self._send(conn, {"type": "ERROR", "message": f"Entrega fallida a {target}", "message_id": message_id})
                        else:
                            self._send(conn, {"type": "ERROR", "message": f"Destino no disponible: {target}", "message_id": message_id})
                        continue

                    if msg_type == "BROADCAST":
                        payload = message.get("payload", {})
                        payload["message_id"] = str(payload.get("message_id") or uuid.uuid4().hex)
                        self._broadcast(
                            {
                                "type": "DELIVERED",
                                "from": client_name,
                                "payload": payload,
                            },
                            exclude=client_name,
                        )
                        self._send(conn, {"type": "ACK", "message_id": payload["message_id"], "target": "*"})
                        self._log(f"BROADCAST {client_name} ({payload.get('command', 'payload')}) id={payload['message_id']}")
                        continue
        finally:
            if client_name:
                with self.lock:
                    self._drop_client(client_name)
                self._broadcast({"type": "SYSTEM", "message": f"{client_name} desconectado"})
                self._log(f"Cliente desconectado: {client_name}")
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.running = True
        self._log(f"Relay server escuchando en {self.host}:{self.port}")
        try:
            while self.running:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        with self.lock:
            names = list(self.clients.keys())
            for name in names:
                self._drop_client(name)
        self._log("Relay detenido")


if __name__ == "__main__":
    RelayServer().serve_forever()
