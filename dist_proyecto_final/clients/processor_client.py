from __future__ import annotations

import argparse
import socket
import threading
import time
import uuid
from pathlib import Path

from core.midi_mapper import MidiMapper
from core.text_analysis import TextAnalyzer
from network.protocol import decode_message, encode_message


class ProcessorClient:
    def __init__(self, name: str, host: str, port: int, monitor_name: str = "monitor") -> None:
        self.name = name
        self.host = host
        self.port = port
        self.monitor_name = monitor_name
        self.socket: socket.socket | None = None
        self.analyzer = TextAnalyzer()
        self.mapper = MidiMapper()
        self.current_config: dict = {}
        self.ack_events: dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused by default
        self._stop_event = threading.Event()

    def log(self, message: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] [{self.name}] {message}")

    def connect(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        self.socket.sendall(encode_message({"type": "REGISTER", "client_name": self.name}))
        self.log(f"Conectado a {self.host}:{self.port}")

    def _send_private(self, payload: dict, wait_ack: bool = False) -> None:
        assert self.socket is not None
        message_id = str(payload.get("message_id") or uuid.uuid4().hex)
        payload["message_id"] = message_id
        ack_event = threading.Event()
        self.ack_events[message_id] = ack_event
        self.socket.sendall(encode_message({"type": "PRIVATE", "to": self.monitor_name, "payload": payload}))
        if wait_ack:
            ack_event.wait(timeout=2.0)
        self.ack_events.pop(message_id, None)

    def _run_job(self) -> None:
        file_path = Path(self.current_config["file_path"])
        bpm = int(self.current_config.get("bpm", 120))
        content = file_path.read_text(encoding="utf-8")
        structure = self.analyzer.analyze_structure(content)
        events = self.analyzer.build_events(content, bpm)
        self.log(f"Procesando {file_path.name}: {len(events)} eventos, tipo={structure['work_type']}, cadencia={structure['cadence']}")
        self._send_private(
            {
                "command": "JOB_STARTED",
                "processor": self.name,
                "file": file_path.name,
                "total_events": len(events),
                "work_type": structure["work_type"],
                "lexical_density": structure["lexical_density"],
                "lexical_diversity": structure["lexical_diversity"],
                "cadence": structure["cadence"],
            },
            wait_ack=True,
        )
        for index, event in enumerate(events, start=1):
            if self._stop_event.is_set():
                self.log("Trabajo detenido por STOP")
                break
            
            self._pause_event.wait()
            
            midi = self.mapper.to_midi(event)
            self._send_private(
                {
                    "command": "EVENT_SONADO",
                    "processor": self.name,
                    "index": index,
                    "token": event.token,
                    "metric": event.metric,
                    "midi_value": event.midi_value,
                    "note": midi.note,
                    "velocity": midi.velocity,
                    "duration_ms": midi.duration_ms,
                    "category": event.category,
                    "work_type": event.work_type,
                    "lexical_density": event.lexical_density,
                    "cadence_strength": event.cadence_strength,
                    "sentence_index": event.sentence_index,
                },
                wait_ack=(index <= 3 or index == len(events)),
            )
            time.sleep(midi.duration_ms / 1000)
        self._send_private(
            {
                "command": "JOB_FINISHED",
                "processor": self.name,
                "file": file_path.name,
                "total_events": len(events),
                "work_type": structure["work_type"],
            },
            wait_ack=True,
        )
        self.log(f"Trabajo finalizado: {file_path.name}")

    def listen(self) -> None:
        assert self.socket is not None
        buffer = b""
        while True:
            chunk = self.socket.recv(4096)
            if not chunk:
                self.log("Conexión cerrada")
                break
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if not raw.strip():
                    continue
                message = decode_message(raw)
                msg_type = message.get("type")
                if msg_type == "ACK":
                    message_id = str(message.get("message_id"))
                    ack_event = self.ack_events.get(message_id)
                    if ack_event:
                        ack_event.set()
                    continue
                if msg_type != "DELIVERED":
                    continue
                payload = message.get("payload", {})
                command = payload.get("command")
                if command == "CONFIGURE":
                    self.current_config = payload
                    file_name = Path(payload["file_path"]).name
                    self.log(f"CONFIGURE recibido: {file_name} @ {payload.get('bpm', 120)} BPM")
                    self._send_private(
                        {
                            "command": "CONFIG_ACK",
                            "processor": self.name,
                            "file": file_name,
                            "bpm": payload.get("bpm", 120),
                        },
                        wait_ack=True,
                    )
                elif command == "START" and self.current_config:
                    self.log("START recibido")
                    self._stop_event.clear()
                    self._pause_event.set()
                    threading.Thread(target=self._run_job, daemon=True).start()
                elif command == "PAUSE":
                    self.log("PAUSE recibido")
                    self._pause_event.clear()
                elif command == "RESUME":
                    self.log("RESUME recibido")
                    self._pause_event.set()
                elif command == "STOP":
                    self.log("STOP recibido")
                    self._stop_event.set()
                    self._pause_event.set()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()

    client = ProcessorClient(name=args.name, host=args.host, port=args.port)
    client.connect()
    client.listen()


if __name__ == "__main__":
    main()
