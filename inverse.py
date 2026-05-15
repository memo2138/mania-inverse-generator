"""
inverse.py — Convierte un Beatmap normal en su versión inverse.
"""

from beatmap import Beatmap, HitObject, x_from_column


def gap_ms(bpm, denominator):
    """
    Calcula el gap en milisegundos.
    A un BPM dado, 1/denominator de beat dura este tiempo.

    Ejemplo: 120 BPM, denominador 4 → (60000/120)/4 = 125 ms.
    """
    return (60_000 / bpm) / denominator


def next_note_in_column(hit_objects, column, after_time):
    """
    Busca la siguiente nota en la columna dada que ocurra DESPUÉS de
    'after_time'. Devuelve el HitObject o None si no hay.
    """
    for h in hit_objects:
        if h.column == column and h.time > after_time:
            return h
    return None


def invert_section(beatmap, start, end, denominator, min_ln_ms=30):
    """
    Aplica la inversión a las notas dentro de [start, end] del beatmap.
    Devuelve una lista nueva de HitObjects con las notas modificadas.

    min_ln_ms: duración mínima de una LN para considerarla válida.
               Si una LN resultante duraría menos que esto, la nota se
               deja como tap (evita LNs injugables en jacks rápidos).
    """
    new_notes = []

    for note in beatmap.hit_objects:
        if note.time < start or note.time > end:
            new_notes.append(note)
            continue

        if note.is_long_note:
            new_notes.append(note)
            continue

        next_note = next_note_in_column(beatmap.hit_objects, note.column, note.time)
        if next_note is None:
            new_notes.append(note)
            continue

        bpm_local = beatmap.bpm_at(note.time)
        gap = gap_ms(bpm_local, denominator)
        end_time = int(next_note.time - gap)

        # Filtro de duración mínima — evita LNs injugables (los "blips" de 19 ms)
        if end_time - note.time < min_ln_ms:
            new_notes.append(note)
            continue

        ln = HitObject(
            column=note.column,
            time=note.time,
            is_long_note=True,
            end_time=end_time,
            raw_line=build_ln_line(
                note.column, note.time, end_time, note.raw_line,
                beatmap.key_count(),
            ),
        )
        new_notes.append(ln)

    return new_notes


def build_ln_line(column, start_time, end_time, original_raw, key_count):
    """
    Construye la línea .osu para una LN, PRESERVANDO el hitsample
    de la nota original (whistle, finish, clap, sample...).

    Formato de una LN en mania:
        x,192,startTime,128,hitSound,endTime:hitSample
    """
    x = x_from_column(column, key_count)

    # De la línea original sacamos hitSound (campo 4) y hitSample (campo 6)
    fields = original_raw.split(",")
    hit_sound = fields[4] if len(fields) > 4 else "0"
    hit_sample = fields[5] if len(fields) > 5 else "0:0:0:0:"

    return f"{x},192,{start_time},128,{hit_sound},{end_time}:{hit_sample}"

def invert_beatmap(beatmap, gaps):
    """
    Aplica inversión a todas las secciones del beatmap usando una lista
    de denominadores (uno por bookmark).
    """
    sections = list(zip(beatmap.bookmarks, gaps))

    for (start, end), denominator in sections:
        beatmap.hit_objects = invert_section(beatmap, start, end, denominator)

    return beatmap


# ------------------------------------------------------------------
# Auto-detección de secciones (cuando el mapa no tiene bookmarks)
# ------------------------------------------------------------------

def auto_detect_sections(beatmap, min_section_ms=4000):
    """
    Detecta secciones automáticamente buscando gaps largos entre notas.

    Heurística:
    - Calcula la longitud de un compás (4 beats) según el BPM dominante.
    - Un "gap de sección" = espacio entre notas > 2 compases.
    - Cada sección debe durar al menos `min_section_ms` para descartarse
      breaks muy cortos.

    Devuelve lista de tuplas (start_ms, end_ms) lista para usar como bookmarks.
    """
    if not beatmap.hit_objects:
        return []

    # Notas ordenadas por tiempo
    times = sorted(ho.time for ho in beatmap.hit_objects)

    # BPM dominante al inicio del mapa
    bpm = beatmap.bpm_at(times[0])
    if bpm <= 0:
        bpm = 120  # fallback razonable

    # Longitud de un compás (4 beats) en ms
    measure_ms = (60_000 / bpm) * 4

    # Umbral: gap mayor a 2 compases = fin de sección
    gap_threshold = measure_ms * 2

    sections = []
    section_start = times[0]
    prev_time = times[0]

    for t in times[1:]:
        gap = t - prev_time
        if gap > gap_threshold:
            sections.append((section_start, prev_time))
            section_start = t
        prev_time = t

    # Cerrar la última sección con la última nota
    sections.append((section_start, prev_time))

    # Filtrar secciones demasiado cortas
    sections = [(s, e) for s, e in sections if (e - s) >= min_section_ms]

    return sections


# ------------------------------------------------------------------
# Bloque de prueba
# ------------------------------------------------------------------

if __name__ == "__main__":
    # Bloque de prueba — invierte todas las secciones (bookmarks) de un .osu
    # con gap 1/4 y guarda el resultado como [Inverse 1/4 test].
    #
    # Uso:
    #   python inverse.py <ruta_al_archivo.osu>
    import sys

    if len(sys.argv) < 2:
        print("Uso: python inverse.py <ruta_al_archivo.osu>")
        sys.exit(0)

    bm = Beatmap(sys.argv[1])

    print(f"Mapa: {bm.title()}")
    print(f"Notas originales: {len(bm.hit_objects)}")

    gaps = [4] * len(bm.bookmarks)
    print(f"Invirtiendo {len(bm.bookmarks)} secciones con gap 1/4...")
    invert_beatmap(bm, gaps)

    lns = sum(1 for h in bm.hit_objects if h.is_long_note)
    print(f"LNs en el resultado: {lns}")

    out = bm.save(new_difficulty="Inverse 1/4 test")
    print(f"\nArchivo guardado en:\n  {out}")