"""
osu_paths.py — Detecta la carpeta Songs/ de osu! del usuario actual.

Estrategia en cascada:
  1. Leer el archivo de configuración osu!.<usuario>.cfg en %LOCALAPPDATA%\\osu!\\
     y respetar el campo BeatmapDirectory que el usuario configuró.
  2. Si lo anterior falla, probar rutas típicas de instalación.
  3. Si nada funciona, devolver None (la app abrirá el diálogo en el directorio
     por defecto de Windows).
"""

import os
from pathlib import Path


def find_songs_folder():
    """
    Devuelve la ruta a la carpeta Songs/ de osu! como string, o None si no se
    encontró. Solo lee archivos, no escribe ni modifica nada.
    """
    found = _from_config_file()
    if found:
        return found

    found = _from_typical_paths()
    if found:
        return found

    return None


# ------------------------------------------------------------------
# Estrategia 1: leer el archivo de configuración de osu!
# ------------------------------------------------------------------

def _from_config_file():
    """
    Busca un archivo osu!.<usuario>.cfg en %LOCALAPPDATA%\\osu!\\ y lee el
    campo BeatmapDirectory.

    Casos posibles del valor de BeatmapDirectory:
      - "Songs"                  → ruta relativa al directorio de osu!
      - "D:\\osu_songs"          → ruta absoluta en otra unidad
      - "C:\\Users\\..\\Songs"    → ruta absoluta
    """
    cfg_dir = os.path.expandvars(r"%LOCALAPPDATA%\osu!")
    if not os.path.isdir(cfg_dir):
        return None

    # Puede haber múltiples archivos osu!.<usuario>.cfg si la PC tiene varias
    # cuentas. Tomamos el más reciente.
    config_files = [
        f for f in os.listdir(cfg_dir)
        if f.startswith("osu!.") and f.endswith(".cfg")
    ]
    if not config_files:
        return None

    # Ordenar por fecha de modificación, más reciente primero
    config_files.sort(
        key=lambda f: os.path.getmtime(os.path.join(cfg_dir, f)),
        reverse=True,
    )

    for config_file in config_files:
        path = _read_beatmap_directory(os.path.join(cfg_dir, config_file), cfg_dir)
        if path:
            return path

    return None


def _read_beatmap_directory(cfg_path, cfg_dir):
    """
    Lee un archivo .cfg y devuelve la ruta absoluta a la carpeta Songs,
    o None si no se pudo determinar.
    """
    try:
        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.strip().startswith("BeatmapDirectory"):
                    continue

                # Línea típica: "BeatmapDirectory = Songs"
                if "=" not in line:
                    continue
                value = line.split("=", 1)[1].strip()
                if not value:
                    continue

                # Si es ruta absoluta y existe, listo
                if os.path.isabs(value) and os.path.isdir(value):
                    return value

                # Si es relativa, combinarla con la carpeta de osu!
                combined = os.path.join(cfg_dir, value)
                if os.path.isdir(combined):
                    return combined
    except OSError:
        pass

    return None


# ------------------------------------------------------------------
# Estrategia 2: probar rutas típicas
# ------------------------------------------------------------------

# Lista de paths donde osu! suele estar instalado. Se prueban en orden
# y se devuelve el primero que exista.
TYPICAL_PATHS = [
    r"%LOCALAPPDATA%\osu!\Songs",   # instalación moderna estándar
    r"%APPDATA%\osu!\Songs",        # instalación vieja
    r"C:\Program Files\osu!\Songs",
    r"C:\Program Files (x86)\osu!\Songs",
]


def _from_typical_paths():
    for path in TYPICAL_PATHS:
        expanded = os.path.expandvars(path)
        if os.path.isdir(expanded):
            return expanded
    return None


# ------------------------------------------------------------------
# Bloque de prueba
# ------------------------------------------------------------------

if __name__ == "__main__":
    folder = find_songs_folder()
    if folder:
        print(f"✓ Songs folder: {folder}")

        # Pequeño bonus: contar mapsets para verificar que es la carpeta real
        try:
            mapsets = [d for d in os.listdir(folder)
                       if os.path.isdir(os.path.join(folder, d))]
            print(f"  Mapsets detectados: {len(mapsets)}")
            if mapsets:
                print(f"  Primer mapset: {mapsets[0]}")
        except OSError:
            pass
    else:
        print("✗ No se encontró la carpeta Songs.")
        print("  El usuario tendrá que navegar manualmente.")