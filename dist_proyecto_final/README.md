# Proyecto SD: Sonorización de Texto a MIDI Distribuido

Este proyecto es un sistema distribuido diseñado para analizar textos literarios (como el _Mio Cid_ o _Don Quijote_) y transformarlos en eventos musicales (MIDI) en tiempo real. Utiliza una arquitectura cliente-servidor con un nodo central (Relay) y múltiples nodos trabajadores (Procesadores) guiados por un Orquestador (Director) a través de una interfaz web basada en FastAPI.

## Características Principales
- **Análisis Lingüístico:** Extrae métricas como densidad léxica, diversidad léxica y cadencia para diferenciar entre prosa y verso.
- **Mapeo Multivariable a MIDI:** Convierte las métricas del texto en características musicales (nota, velocidad, duración).
- **Arquitectura Distribuida TCP:** Emplea sockets TCP no bloqueantes para la comunicación entre los nodos de procesamiento y el director central.
- **Reproducción Comparativa (Dual):** Permite cargar y escuchar dos obras literarias simultáneamente en el frontend web con espacialización estéreo (Paneo L y R) y controles independientes.
- **Control de Red en Vivo:** Permite arrancar, pausar, reanudar y detener el análisis de todos los nodos distribuidos de forma centralizada.
- **Archivos Dinámicos:** Soporta carga dinámica de archivos `.txt` directamente desde el navegador al sistema.

---

## 🚀 Arranque Rápido

Asegúrate de tener un entorno de Python compatible (ej. Python 3.11). Ve a la carpeta `dist_proyecto_final`:

```bash
# Opcional (Dependiendo de tu instalación de Python)
py -3.11 -m pip install -r requirements.txt
```

Para iniciar el flujo completo de la red, necesitas **abrir 3 terminales distintas**.

### Terminal 1: Iniciar el Servidor Web (Director)
Inicia la Interfaz Gráfica y la API Central:
```bash
py -3.11 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
> 👉 Una vez iniciado, abre [http://127.0.0.1:8000](http://127.0.0.1:8000) en tu navegador.

### Terminal 2: Levantar Cliente Procesador A
Arranca un nodo trabajador llamado `procesador-a`:
```bash
py -3.11 -m clients.processor_client --name procesador-a
```

### Terminal 3: Levantar Cliente Procesador B
Arranca un segundo nodo trabajador llamado `procesador-b`:
```bash
py -3.11 -m clients.processor_client --name procesador-b
```

---

## 💻 Guía de Uso de la Interfaz Web

Para coordinar la red distribuida, abre la interfaz en **http://127.0.0.1:8000** y sigue los pasos en la tarjeta de **Configuración de Ejecución Distribuida**:

1. Haz clic en el botón **"Levantar Relay local"** (o ejecuta aparte `py network.relay_server`). Esto abrirá el puente de sockets. Los procesadores A y B se conectarán en los próximos segundos enviando su ACK, reflejándose en el *"Estado por cliente"*.
2. Si quieres subir una obra nueva distinta, usa la opción inferior de **"Subir nueva obra"**, la cual inyectará el archivo en tu carpeta `corpus`.
3. Ajusta las opciones del Cliente 1 y Cliente 2 (asignando qué obra y BPM leerá cada procesador).
4. Haz clic en **"Enviar config"** para mandar el plan de trabajo por sockets.
5. Utiliza los controles centrales para la red de procesamiento en segundo plano:
   - **Start Red:** Instruye a los clientes para arrancar los bucles e iterar emitiendo los eventos MIDI.
   - **Pausar Red:** Detiene localmente los hilos (threads) de los respectivos procesadores.
   - **Reanudar:** Remueve la pausa de la iteración.
   - **Stop Red:** Cancela la ejecución del archivo actual y limpia las variables.

#### 🎧 Reproducción y Comparación de Audio en el Navegador
Si deseas escuchar *in situ* la diferencia sintáctica o de cadencia entre dos libros:
- Sube a la parte superior de la ventana web en `"Reproducción Comparativa"`.
- Configura la **Pista 1** y la **Pista 2**, la cantidad de eventos y dale a sus botones individuales de **Play**.
- Las pistas están paneadas un poco hacia la izquierda y derecha para que las percibas simultáneamente.
- Usa los **Botones Globales** (Play Ambas / Pausar Ambas / Stop Ambas) en la esquina superior derecha para orquestar la reproducción local.
