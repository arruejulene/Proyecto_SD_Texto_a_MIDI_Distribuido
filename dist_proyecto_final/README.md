# Proyecto_SD

## Mejoras incluidas
- Reproducción ampliada a todo el ancho de la pantalla.
- Opciones de reproducción: 10, 50, 100, 150 o obra completa.
- Barra de progreso, pausa, stop y mensaje final `Obra terminada`.
- Detección de **prosa** frente a **verso** para diferenciar Quijote y Mio Cid.
- Métricas lingüísticas adicionales: densidad léxica, diversidad léxica, ratios gramaticales y longitud media de unidad textual.
- Mapeo MIDI multivariable con cambios de nota, velocidad, canal e intensidad según la estructura del texto.
- Relay con logs más detallados, ACK de entrega y manejo de nombres duplicados.
- Clientes con logs de ejecución y confirmaciones de entrega básicas.

## Arranque
Desde la carpeta `dist_proyecto_final`:

```bash
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install -r requirements.txt
py -3.11 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Flujo distribuido
### Terminal 1
```bash
py -3.11 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Terminal 2
```bash
py -3.11 -m clients.processor_client --name procesador-a
```

### Terminal 3
```bash
py -3.11 -m clients.processor_client --name procesador-b
```

Luego en la web:
1. `Levantar relay local`
2. `Enviar configuración`
3. `Enviar START`

## Nota
También puedes iniciar el relay aparte:

```bash
py -3.11 -m network.relay_server
```
