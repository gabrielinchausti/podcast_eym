#!/usr/bin/env python3
"""
Genera/actualiza el feed RSS del podcast a partir de episodios.json.

Uso (lo llama el workflow después de subir el MP3 al Release):
    python3 generar_rss.py --titulo "Economía y Mercado — 6 de julio de 2026" \
                           --url "https://github.com/USUARIO/REPO/releases/download/eym-2026-07-06/episodio.mp3" \
                           --bytes 4800000 \
                           --descripcion "Resumen de las columnas de la semana."

Mantiene el estado en episodios.json y escribe docs/feed.xml
(servido por GitHub Pages, o vía raw.githubusercontent.com).
"""

import argparse
import json
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

# ─── Datos del programa (editá a gusto) ──────────────────────────────────────
PODCAST = {
    "titulo": "Economía y Mercado — Resumen semanal",
    "descripcion": "Resumen automatizado de las columnas del suplemento "
                   "Economía y Mercado del diario El País (Uruguay). "
                   "Uso personal.",
    "autor": "Automatización personal",
    "idioma": "es-uy",
    "link": "https://github.com",   # se puede apuntar al repo
    "max_episodios": 20,            # los más viejos salen del feed
}

ESTADO = Path("episodios.json")
FEED   = Path("docs/feed.xml")


def cargar_estado() -> list[dict]:
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return []


def escribir_feed(episodios: list[dict]) -> None:
    items = []
    for ep in episodios[: PODCAST["max_episodios"]]:
        items.append(f"""    <item>
      <title>{escape(ep["titulo"])}</title>
      <description>{escape(ep["descripcion"])}</description>
      <enclosure url="{escape(ep["url"])}" length="{ep["bytes"]}" type="audio/mpeg"/>
      <guid isPermaLink="false">{escape(ep["url"])}</guid>
      <pubDate>{ep["pubdate"]}</pubDate>
    </item>""")

    ahora = format_datetime(datetime.now(timezone.utc))
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(PODCAST["titulo"])}</title>
    <description>{escape(PODCAST["descripcion"])}</description>
    <language>{PODCAST["idioma"]}</language>
    <link>{escape(PODCAST["link"])}</link>
    <lastBuildDate>{ahora}</lastBuildDate>
    <itunes:author>{escape(PODCAST["autor"])}</itunes:author>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
"""
    FEED.parent.mkdir(parents=True, exist_ok=True)
    FEED.write_text(xml, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--titulo", required=True)
    parser.add_argument("--url", required=True, help="URL pública del MP3 (asset del Release)")
    parser.add_argument("--bytes", type=int, required=True, help="Tamaño del MP3 en bytes")
    parser.add_argument("--descripcion", default="Resumen semanal de Economía y Mercado.")
    args = parser.parse_args()

    episodios = cargar_estado()

    # Evitar duplicados si el workflow se corre dos veces el mismo día
    episodios = [e for e in episodios if e["url"] != args.url]

    episodios.insert(0, {
        "titulo": args.titulo,
        "descripcion": args.descripcion,
        "url": args.url,
        "bytes": args.bytes,
        "pubdate": format_datetime(datetime.now(timezone.utc)),
    })

    ESTADO.write_text(json.dumps(episodios, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_feed(episodios)
    print(f"✅ Feed actualizado con {len(episodios)} episodio(s) → {FEED}")


if __name__ == "__main__":
    main()
