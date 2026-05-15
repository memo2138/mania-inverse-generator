"""
beatmap.py — Parser de archivos .osu (osu!mania 4K)
"""

from pathlib import Path
from dataclasses import dataclass

HERE = Path(__file__).parent


# ------------------------------------------------------------------
# Funciones auxiliares "puras" — solo hacen una cosa, sin estado
# ------------------------------------------------------------------

def column_from_x(x, key_count):
    """
    Convierte la coordenada x de osu! al número de columna (0..key_count-1).
    
    Fórmula general para osu!mania xK:
        x = (column + 0.5) * (512 / key_count)
    
    Ejemplos:
      4K: x=64→col 0, x=192→col 1, x=320→col 2, x=448→col 3
      7K: x≈36→col 0, x≈109→col 1, etc.
    """
    return int(x * key_count / 512)


def x_from_column(col, key_count):
    """
    Inverso: dado el número de columna y el key_count del mapa,
    devuelve la coordenada x que escribirías en el .osu.
    """
    return int((col + 0.5) * 512 / key_count)


def _sanitize_filename(name):
    """
    Quita caracteres que Windows no permite en nombres de archivo.
    osu! sigue esa convención para nombrar los .osu.
    """
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "")
    return name.strip()

def _ordinal_suffix(n):
    """Devuelve '2nd', '3rd', '4th', '11th', etc."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    return f"{n}{suffixes.get(n % 10, 'th')}"


def find_unique_path(path):
    """
    Si `path` no existe, lo devuelve tal cual.
    Si existe, le mete un sufijo dentro de los corchetes hasta encontrar
    uno libre.

    Ejemplo:
        foo [Inverse].osu          → existe
        foo [Inverse 2nd ver].osu  → existe
        foo [Inverse 3rd ver].osu  → libre, devuelve este
    """
    path = Path(path)
    if not path.exists():
        return path

    stem = path.stem        # nombre sin extensión
    suffix = path.suffix    # ".osu"
    parent = path.parent

    n = 2
    while True:
        if stem.endswith("]"):
            # Mete el sufijo dentro de los corchetes finales
            new_stem = stem[:-1] + f" {_ordinal_suffix(n)} ver]"
        else:
            new_stem = f"{stem} {_ordinal_suffix(n)} ver"

        candidate = parent / f"{new_stem}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


# ------------------------------------------------------------------
# Estructuras de datos
# ------------------------------------------------------------------

@dataclass
class HitObject:
    """Una nota individual del mapa."""
    column: int          # 0..3
    time: int            # ms desde el inicio del audio
    is_long_note: bool   # True si es LN, False si es tap
    end_time: int        # igual a time si es tap
    raw_line: str        # línea original, para preservar hitsounds custom


@dataclass
class TimingPoint:
    """Un cambio real de BPM (uninherited timing point)."""
    time: int            # desde cuándo aplica este BPM
    beat_length: float   # ms por beat

    @property
    def bpm(self):
        return 60_000 / self.beat_length


# ------------------------------------------------------------------
# Parseo de secciones
# ------------------------------------------------------------------

def parse_sections(osu_path):
    """Lee un .osu y lo divide en secciones por su header [Nombre]."""
    text = Path(osu_path).read_text(encoding="utf-8-sig")
    sections = {}
    current = None

    for line in text.splitlines():
        line = line.strip()

        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections[current] = []
        elif current and line:
            sections[current].append(line)

    return sections


def parse_key_value(lines):
    """Convierte líneas tipo 'Clave: valor' en un dict."""
    result = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def parse_hit_object(line, key_count):
    """Parsea una línea de [HitObjects] a un HitObject."""
    fields = line.split(",")
    x = int(fields[0])
    time = int(fields[2])
    type_flag = int(fields[3])

    is_ln = bool(type_flag & 128)

    if is_ln:
        end_time = int(fields[5].split(":")[0])
    else:
        end_time = time

    return HitObject(
        column=column_from_x(x, key_count),
        time=time,
        is_long_note=is_ln,
        end_time=end_time,
        raw_line=line,
    )


def parse_timing_points(lines):
    """
    Devuelve SOLO los timing points uninherited (cambios reales de BPM).
    Ignora los inherited (SV en mania) — no afectan el cálculo del gap.
    """
    points = []
    for line in lines:
        fields = line.split(",")
        if len(fields) < 7:
            continue
        # Campo 6 (índice 6) = uninherited flag. 1 = real BPM, 0 = SV.
        if fields[6].strip() != "1":
            continue
        time = int(float(fields[0]))
        beat_length = float(fields[1])
        if beat_length <= 0:
            continue  # protección extra
        points.append(TimingPoint(time=time, beat_length=beat_length))

    # Ordenamos por tiempo por si el archivo viene desordenado
    points.sort(key=lambda tp: tp.time)
    return points


def last_hit_object_time(hit_objects):
    """Devuelve el tiempo de la última nota (en ms)."""
    if not hit_objects:
        return 0
    return hit_objects[-1].time


# ------------------------------------------------------------------
# Clase principal: representa un mapa entero
# ------------------------------------------------------------------

class Beatmap:
    """Representa un mapa .osu cargado en memoria."""

    def __init__(self, osu_path):
        self.path = Path(osu_path)
        self.sections = parse_sections(self.path)

        # Secciones clave:valor
        self.general    = parse_key_value(self.sections.get("General",    []))
        self.editor     = parse_key_value(self.sections.get("Editor",     []))
        self.metadata   = parse_key_value(self.sections.get("Metadata",   []))
        self.difficulty = parse_key_value(self.sections.get("Difficulty", []))

        # IMPORTANTE: parsear key_count ANTES de los hit objects, porque
        # column_from_x depende de cuántas columnas tiene el mapa.
        self._key_count = int(self.difficulty.get("CircleSize", "4"))

        # Secciones de "lista de cosas"
        raw_hits = self.sections.get("HitObjects", [])
        raw_times = self.sections.get("TimingPoints", [])
        self.hit_objects = [parse_hit_object(line, self._key_count) for line in raw_hits]
        self.timing_points = parse_timing_points(raw_times)


        # Bookmarks parseados a pares (start, end)
        self.bookmarks = self._parse_bookmarks()

    def _parse_bookmarks(self):
        raw = self.editor.get("Bookmarks", "")
        if not raw:
            return []
        numbers = [int(x) for x in raw.split(",")]
        if len(numbers) % 2 == 1:
            numbers.append(last_hit_object_time(self.hit_objects))
        return [(numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)]

    def is_mania(self):
        """¿Es un mapa de osu!mania (cualquier número de teclas)?"""
        return self.general.get("Mode") == "3"

    def is_mania_4k(self):
        """¿Es específicamente un mapa de 4K mania?"""
        return self.is_mania() and self._key_count == 4

    def key_count(self):
        """Número de teclas del mapa (4 para 4K, 7 para 7K, etc.)."""
        return self._key_count

    def title(self):
        artist = self.metadata.get("Artist", "?")
        title  = self.metadata.get("Title",  "?")
        diff   = self.metadata.get("Version", "?")
        return f"{artist} - {title} [{diff}]"

    def bpm_at(self, time):
        """
        Devuelve el BPM vigente en el tiempo dado (ms).
        Lógica: el último TP cuyo time <= 'time' es el que está activo.
        """
        if not self.timing_points:
            return 120.0  # fallback razonable

        current = self.timing_points[0]
        for tp in self.timing_points:
            if tp.time <= time:
                current = tp
            else:
                break  # como están ordenados, podemos cortar aquí
        return current.bpm

    def save(self, new_difficulty="Inverse"):
        """
        Escribe este beatmap como un .osu nuevo en la misma carpeta
        del original. Convención de osu!:
            Artist - Title (Creator) [Difficulty].osu

        Cambia automáticamente:
            - Version → new_difficulty
            - BeatmapID → 0 (es una diff nueva)

        Devuelve la ruta del archivo generado.
        """
        artist = _sanitize_filename(self.metadata.get("Artist", "Unknown"))
        title = _sanitize_filename(self.metadata.get("Title", "Untitled"))
        creator = _sanitize_filename(self.metadata.get("Creator", "Unknown"))
        version = _sanitize_filename(new_difficulty)

        filename = f"{artist} - {title} ({creator}) [{version}].osu"
        out_path = self.path.parent / filename
        out_path = find_unique_path(out_path)

        # Reconstruimos el archivo entero, sección por sección
        lines = ["osu file format v14", ""]

        for section_name in ["General", "Editor", "Metadata",
                             "Difficulty", "Events",
                             "TimingPoints", "HitObjects"]:

            section_lines = self.sections.get(section_name, [])
            if not section_lines and section_name != "HitObjects":
                continue

            lines.append(f"[{section_name}]")

            if section_name == "Metadata":
                # Regeneramos [Metadata] con los cambios en Version y BeatmapID
                meta = dict(self.metadata)  # copia, no muta el original
                meta["Version"] = new_difficulty
                meta["BeatmapID"] = "0"
                for key, value in meta.items():
                    lines.append(f"{key}:{value}")

            elif section_name == "HitObjects":
                # Reescribimos las notas desde self.hit_objects (con las LNs nuevas)
                for hit in self.hit_objects:
                    lines.append(hit.raw_line)

            else:
                # Las demás secciones se copian tal cual del original
                lines.extend(section_lines)

            lines.append("")  # línea en blanco entre secciones

        # Escribimos con CRLF (line endings de Windows, como el original).
        # newline="" desactiva la conversión automática \n→\r\n de Python
        # en Windows, porque ya unimos con \r\n nosotros mismos.
        out_path.write_text("\r\n".join(lines), encoding="utf-8", newline="")

        return out_path

# ------------------------------------------------------------------
# Bloque de prueba
# ------------------------------------------------------------------

if __name__ == "__main__":
    # Bloque de prueba/inspección — útil para verificar el parser con un .osu real.
    # Pasa la ruta del archivo como argumento de línea de comandos:
    #
    #   python beatmap.py "C:\ruta\a\tu\mapa.osu"
    #
    # Si lo corres sin argumentos, te recuerda cómo usarlo y sale.
    import sys

    if len(sys.argv) < 2:
        print("Uso: python beatmap.py <ruta_al_archivo.osu>")
        sys.exit(0)

    bm = Beatmap(sys.argv[1])

    print(bm.title())
    print(f"  ¿Es mania?       {bm.is_mania()}")
    print(f"  Key count:       {bm.key_count()}")
    print(f"  Notas:           {len(bm.hit_objects)}")
    print(f"  TPs (uninherit): {len(bm.timing_points)}")
    print()

    print("  Primeras 5 notas parseadas:")
    for hit in bm.hit_objects[:5]:
        kind = "LN" if hit.is_long_note else "tap"
        print(f"    t={hit.time:>6} col={hit.column} {kind:3} end={hit.end_time}")
    print()

    print("  Primeros 5 cambios de BPM:")
    for tp in bm.timing_points[:5]:
        print(f"    t={tp.time:>6}  beat_length={tp.beat_length:.4f}  BPM={tp.bpm:.2f}")
    print()

    print("  BPM en el inicio de cada bookmark:")
    for i, (start, end) in enumerate(bm.bookmarks, start=1):
        bpm = bm.bpm_at(start)
        print(f"    #{i}  t={start:>6}  BPM={bpm:.2f}")