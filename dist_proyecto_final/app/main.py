from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.midi_mapper import MidiMapper
from core.text_analysis import TextAnalyzer
from monitor.orchestrator import MonitorOrchestrator
from network.relay_server import RelayServer

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
CORPUS_DIR = BASE_DIR / "corpus"
APP_NAME = "Director de Sonorización Literaria"


class Assignment(BaseModel):
    processor: str
    file_name: str
    bpm: int = 120


class ConfigurePayload(BaseModel):
    assignments: list[Assignment]


class PreviewPayload(BaseModel):
    file_name: str
    bpm: int = 120
    limit: Optional[int] = None


class ControlPayload(BaseModel):
    processor: str
    command: str


orchestrator = MonitorOrchestrator(host="127.0.0.1", port=5050, corpus_dir=CORPUS_DIR)
orchestrator.store.push_system("Aplicación iniciada. Levanta el relay y conecta los clientes para empezar.")
relay_server_instance: RelayServer | None = None
relay_thread: threading.Thread | None = None
analyzer = TextAnalyzer()
mapper = MidiMapper()


@asynccontextmanager
async def lifespan(app: FastAPI):
    orchestrator.ensure_connected()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def _available_files() -> list[str]:
    return sorted([path.name for path in CORPUS_DIR.glob("*.txt")])


def _is_relay_port_open(host: str = "127.0.0.1", port: int = 5050) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def _start_local_relay() -> bool:
    global relay_server_instance, relay_thread
    if _is_relay_port_open():
        return False
    relay_server_instance = RelayServer(host="127.0.0.1", port=5050)
    relay_thread = threading.Thread(target=relay_server_instance.serve_forever, daemon=True)
    relay_thread.start()
    return True


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "files": _available_files(),
        },
    )


@app.get("/api/state")
async def api_state():
    orchestrator.ensure_connected()
    data = orchestrator.store.snapshot()
    data["connected"] = orchestrator.connected
    data["relay_port_open"] = _is_relay_port_open()
    data["available_files"] = _available_files()
    data["connected_clients"] = [name for name in data.get("processors", {}).keys() if name != "director"]
    return JSONResponse(data)


@app.post("/api/relay/start")
async def api_relay_start():
    created = _start_local_relay()
    orchestrator.store.push_system("Solicitud de arranque del relay local recibida")
    orchestrator.ensure_connected()
    return {
        "ok": True,
        "created": created,
        "message": "Relay local iniciado." if created else "Ya había un relay escuchando.",
    }


@app.post("/api/configure")
async def api_configure(payload: ConfigurePayload):
    if not orchestrator.ensure_connected():
        raise HTTPException(status_code=503, detail="El director no está conectado al relay server.")
    orchestrator.configure_run([item.model_dump() for item in payload.assignments])
    return {"ok": True, "message": "Configuración enviada a los procesadores."}


@app.post("/api/start")
async def api_start():
    if not orchestrator.ensure_connected():
        raise HTTPException(status_code=503, detail="El director no está conectado al relay server.")
    orchestrator.start_run()
    return {"ok": True, "message": "Ejecución distribuida iniciada."}


@app.post("/api/processor/control")
async def api_processor_control(payload: ControlPayload):
    if not orchestrator.ensure_connected():
        raise HTTPException(status_code=503, detail="El director no está conectado al relay server.")
    try:
        orchestrator.control_processor(payload.processor, payload.command)
        return {"ok": True, "message": f"Comando {payload.command} enviado a {payload.processor}."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/preview")
async def api_preview(payload: PreviewPayload):
    if not orchestrator.ensure_connected():
        raise HTTPException(status_code=503, detail="Primero conecta el director al relay server.")
    file_path = (CORPUS_DIR / payload.file_name).resolve()
    if not file_path.exists() or file_path.parent != CORPUS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    content = file_path.read_text(encoding="utf-8")
    structure = analyzer.analyze_structure(content)
    events_all = analyzer.build_events(content, payload.bpm)
    limit = payload.limit
    if limit is None or limit <= 0:
        events = events_all
    else:
        events = events_all[: limit]
    rendered = []
    for index, event in enumerate(events, start=1):
        midi = mapper.to_midi(event)
        rendered.append(
            {
                "index": index,
                "token": event.token,
                "metric": event.metric,
                "midi_value": event.midi_value,
                "note": midi.note,
                "velocity": midi.velocity,
                "duration_ms": midi.duration_ms,
                "category": event.category,
                "work_type": event.work_type,
                "cadence_strength": event.cadence_strength,
                "sentence_index": event.sentence_index,
            }
        )
    orchestrator.store.push_system(
        f"Preview preparado: {payload.file_name}",
        file=payload.file_name,
        total_events=len(events_all),
        shown_events=len(rendered),
        mode="preview",
    )
    return {
        "ok": True,
        "file": payload.file_name,
        "events": rendered,
        "analysis": structure,
    }
