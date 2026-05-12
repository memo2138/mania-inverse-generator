"""
osu_client.py — Cliente HTTP para tosu.
Consulta el endpoint /json de tosu y devuelve el estado actual de osu!.
"""

import requests
from pathlib import Path

TOSU_URL = "http://localhost:24050/json"
TIMEOUT_SECONDS = 1.0

OSU_STATES = {
    0:  "main_menu",
    2:  "song_select",
    3:  "loading",
    5:  "playing",
    7:  "results",
    15: "editor",
}

# Estados en los que el campo de path es confiable
STATES_WITH_MAP = {2, 3, 5, 7, 15}


def fetch_status():
    """
    Consulta tosu una vez y devuelve un dict con el estado actual.
    Ver el bloque de prueba abajo para los posibles formatos de respuesta.
    """
    try:
        response = requests.get(TOSU_URL, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException:
        return {"connected": False}

    # ¿osu! está corriendo? tosu pone state=-1 si no detecta el proceso.
    state_code = _deep_get(data, "menu", "state", default=-1)
    osu_running = state_code >= 0

    if not osu_running:
        return {"connected": True, "osu_running": False}

    # Reconstruimos el path absoluto del .osu actual.
    # tosu pone el path como (carpeta_songs + folder_del_mapset + archivo.osu)
    songs_folder = _deep_get(data, "settings", "folders", "songs", default="")
    map_folder   = _deep_get(data, "menu", "bm", "path", "folder", default="")
    map_file     = _deep_get(data, "menu", "bm", "path", "file",   default="")

    full_path = ""
    if songs_folder and map_folder and map_file:
        full_path = str(Path(songs_folder) / map_folder / map_file)

    map_loaded = bool(full_path) and Path(full_path).exists() and state_code in STATES_WITH_MAP

    if not map_loaded:
        return {
            "connected":   True,
            "osu_running": True,
            "map_loaded":  False,
            "osu_state":   OSU_STATES.get(state_code, f"unknown({state_code})"),
        }

    metadata = {
        "artist":     _deep_get(data, "menu", "bm", "metadata", "artist",     default="?"),
        "title":      _deep_get(data, "menu", "bm", "metadata", "title",      default="?"),
        "mapper":     _deep_get(data, "menu", "bm", "metadata", "mapper",     default="?"),
        "difficulty": _deep_get(data, "menu", "bm", "metadata", "difficulty", default="?"),
    }

    # Stats útiles para mostrar en la UI
    bpm_common = _deep_get(data, "menu", "bm", "stats", "BPM", "common", default=0)
    bpm_min    = _deep_get(data, "menu", "bm", "stats", "BPM", "min",    default=0)
    bpm_max    = _deep_get(data, "menu", "bm", "stats", "BPM", "max",    default=0)
    circles    = _deep_get(data, "menu", "bm", "stats", "circles",       default=0)
    holds      = _deep_get(data, "menu", "bm", "stats", "holds",         default=0)
    circle_size = _deep_get(data, "menu", "bm", "stats", "memoryCS",     default=0)

    return {
        "connected":   True,
        "osu_running": True,
        "map_loaded":  True,
        "osu_state":   OSU_STATES.get(state_code, f"unknown({state_code})"),
        "path":        full_path,
        "metadata":    metadata,
        "stats": {
            "key_count": int(circle_size),
            "circles":     int(circles),
            "holds":       int(holds),
            "notes_total": int(circles) + int(holds),
            "bpm_common":  round(float(bpm_common), 1),
            "bpm_min":     round(float(bpm_min),    1),
            "bpm_max":     round(float(bpm_max),    1),
        },
    }


def _deep_get(d, *keys, default=None):
    """
    Atraviesa un dict anidado sin romperse si falta alguna clave.
    """
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


# ------------------------------------------------------------------
# Bloque de prueba
# ------------------------------------------------------------------

if __name__ == "__main__":
    import time

    print("Probando conexión con tosu... (Ctrl+C para salir)\n")

    last_path = None
    while True:
        status = fetch_status()

        if not status["connected"]:
            print("✗ tosu no responde. ¿Está corriendo tosu.exe?")
        elif not status["osu_running"]:
            print("✗ tosu OK pero osu! no detectado. Abre osu!.")
        elif not status["map_loaded"]:
            print(f"… esperando mapa (osu! en estado: {status['osu_state']})")
        else:
            if status["path"] != last_path:
                m = status["metadata"]
                s = status["stats"]
                bpm_str = (
                    f"{s['bpm_common']}"
                    if s["bpm_min"] == s["bpm_max"]
                    else f"{s['bpm_min']}-{s['bpm_max']} ({s['bpm_common']} avg)"
                )
                print(f"✓ {m['artist']} — {m['title']} [{m['difficulty']}]")
                print(f"  by {m['mapper']}")
                print(f"  state: {status['osu_state']}  ·  {s['key_count']}K  ·  BPM: {bpm_str}")
                print(f"  notes: {s['notes_total']} ({s['circles']} taps + {s['holds']} LNs)")
                print(f"  path: {status['path']}")
                print()
                last_path = status["path"]

        time.sleep(2)