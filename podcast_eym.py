#!/usr/bin/env python3
"""
Podcast "Economía y Mercado" (El País, Uruguay)
================================================
Pipeline completo, ahora directo desde el sitio (sin depender del mail):
  1. Entra a la sección Economía y Mercado de elpais.com.uy y junta los links
     de las notas recientes (por defecto, las de los últimos 7 días).
     Si hay un cookies.txt con tu sesión de suscriptor, accede al texto completo.
  2. Scrapea cada artículo: título, autor, fecha y cuerpo.
  3. Genera un guion de podcast de ~5 minutos con la API de OpenAI (chat).
  4. Convierte el guion a MP3 con el TTS de OpenAI (gpt-4o-mini-tts),
     partiendo el texto en trozos y concatenando el audio.

Uso típico (los lunes):
    export OPENAI_API_KEY="sk-..."
    python3 podcast_eym.py --cookies cookies.txt

Otras opciones:
    python3 podcast_eym.py --dias 3 --voz onyx
    python3 podcast_eym.py --rtf "UY-E&M.rtf"      # modo viejo, desde el mail

Requisitos:
    pip install openai beautifulsoup4 curl_cffi
"""

import argparse
import http.cookiejar
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from curl_cffi import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# ─── Configuración ────────────────────────────────────────────────────────────

URL_SECCION  = "https://www.elpais.com.uy/economia-y-mercado"
MODELO_GUION = "gpt-4o-mini"        # modelo que escribe el guion
MODELO_TTS   = "gpt-4o-mini-tts"    # modelo de texto a voz
VOZ_DEFAULT  = "ash"                # alternativas: onyx, alloy, echo, nova, etc.
MAX_CHARS_TTS = 3000                # margen seguro bajo el límite por pedido
MAX_NOTAS     = 15                  # tope de notas a considerar por corrida
TZ_UY = ZoneInfo("America/Montevideo")  # para decidir qué es "hoy"

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga_es(d: date) -> str:
    """Fecha en español, sin depender del locale del sistema (distinto en GitHub Actions)."""
    return f"{DIAS_ES[d.weekday()]} {d.day} de {MESES_ES[d.month - 1]} de {d.year}"

INSTRUCCIONES_VOZ = (
    "Hablá en español con tono de locutor de informativo radial: "
    "ritmo pausado y claro, profesional pero cercano."
)

# Frases de boilerplate/paywall a filtrar (heredadas del scraper en R)
FRASES_BASURA = re.compile(
    "|".join([
        r"¿Necesitás ayuda con tu suscripción",
        r"Contenido Exclusivo",
        r"Conocé nuestros planes",
        r"¿Encontraste un error",
        r"bloqueador de anuncios",
        r"AdBlock",
        r"uBlock Origin",
        r"Generalmente, se encuentra",
        r"seleccionar una opción",
        r"Si ya sos suscriptor podés ingresar",
    ]),
    re.IGNORECASE,
)

# ─── Sesión HTTP ──────────────────────────────────────────────────────────────

def crear_sesion(cookies_path: str | None) -> requests.Session:
    """Sesión HTTP; si hay cookies.txt exportado del navegador, entra como suscriptor."""
    s = requests.Session(impersonate="chrome")
    s.headers.update({"Accept-Language": "es-UY,es;q=0.9"})
    if cookies_path:
        jar = http.cookiejar.MozillaCookieJar(cookies_path)
        jar.load(ignore_discard=True, ignore_expires=True)
        s.cookies = jar
        print("🍪 Usando cookies de sesión (acceso de suscriptor).")
    return s

# ─── 1a. Links directo desde la sección del sitio ────────────────────────────

def extraer_links_seccion(sesion: requests.Session, url_seccion: str) -> list[str]:
    """
    Baja la portada de la sección y extrae los links a notas.
    Busca en el HTML crudo (sirve tanto para links <a> como para URLs
    embebidas en el JSON con que el sitio arma la página), lo que lo hace
    resistente a que la portada se renderice con JavaScript.
    """
    resp = sesion.get(url_seccion, timeout=30)
    resp.raise_for_status()
    html = resp.text

    # URLs absolutas o relativas bajo /economia-y-mercado/<slug>
    crudos = re.findall(
        r'(?:https?://www\.elpais\.com\.uy)?(/economia-y-mercado/[a-z0-9][a-z0-9\-/]*[a-z0-9])',
        html,
        flags=re.IGNORECASE,
    )

    limpios, vistos = [], set()
    for ruta in crudos:
        # Descartar la raíz de la sección y rutas cortas que no son notas
        slug = ruta.rstrip("/").split("/")[-1]
        if len(slug) < 15 or "-" not in slug:
            continue
        url = "https://www.elpais.com.uy" + ruta
        if url not in vistos:
            vistos.add(url)
            limpios.append(url)
    return limpios[:MAX_NOTAS * 2]  # margen: después se filtra por fecha

# ─── 1b. Links desde el mail RTF (modo compatibilidad) ────────────────────────

def extraer_links_rtf(rtf_path: str) -> list[str]:
    contenido = Path(rtf_path).read_text(encoding="utf-8", errors="ignore")
    links = re.findall(r'HYPERLINK "(https://www\.elpais\.com\.uy[^"]+)"', contenido)
    if not links:
        links = re.findall(r'https://www\.elpais\.com\.uy[^\s"\\}]+', contenido)
    limpios, vistos = [], set()
    for url in links:
        url = url.rstrip("\\").rstrip(".")
        if url not in vistos:
            vistos.add(url)
            limpios.append(url)
    return limpios

# ─── 2. Scrapear artículos ────────────────────────────────────────────────────

def leer_articulo(sesion: requests.Session, url: str) -> dict:
    """Baja una nota y devuelve título, autor, fecha de publicación y cuerpo limpio."""
    try:
        resp = sesion.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        meta_titulo = soup.find("meta", attrs={"name": "twitter:title"}) or \
                      soup.find("meta", attrs={"property": "og:title"})
        titulo = meta_titulo["content"].strip() if meta_titulo else "(sin título)"

        meta_autor = soup.find("meta", attrs={"property": "article:author"})
        if meta_autor and meta_autor.get("content"):
            autor = meta_autor["content"].rstrip("/").split("/")[-1]
            autor = autor.replace("-", " ").title()
        else:
            autor = "Autor no disponible"

        fecha = None
        meta_fecha = soup.find("meta", attrs={"property": "article:published_time"})
        if meta_fecha and meta_fecha.get("content"):
            try:
                fecha = datetime.fromisoformat(meta_fecha["content"].replace("Z", "+00:00"))
                if fecha.tzinfo is None:
                    # El sitio no manda offset; sus timestamps son hora de Montevideo.
                    fecha = fecha.replace(tzinfo=TZ_UY)
            except ValueError:
                pass

        parrafos = [
            p.get_text(strip=True)
            for p in soup.find_all("p")
            if p.get_text(strip=True) and not FRASES_BASURA.search(p.get_text())
        ]
        cuerpo = "\n\n".join(parrafos)

        return {"titulo": titulo, "autor": autor, "fecha": fecha, "cuerpo": cuerpo, "url": url}
    except Exception as e:
        return {"titulo": "Error al leer", "autor": "", "fecha": None,
                "cuerpo": f"No se pudo acceder: {e}", "url": url}

# ─── 3. Generar el guion con GPT ──────────────────────────────────────────────

def generar_guion(client: OpenAI, articulos: list[dict]) -> str:
    hoy = fecha_larga_es(date.today())

    notas = "\n\n".join(
        f"=== NOTA {i} ===\nTítulo: {a['titulo']}\nAutor: {a['autor']}\nTexto:\n{a['cuerpo'][:8000]}"
        for i, a in enumerate(articulos, 1)
    )

    prompt_sistema = (
        "Sos el guionista y conductor de un micro-podcast semanal en español rioplatense "
        "(Uruguay) que resume el suplemento 'Economía y Mercado' del diario El País. "
        "Tu oyente es una persona informada que escucha mientras maneja."
    )

    prompt_usuario = f"""Con las notas de abajo, escribí el guion COMPLETO de un episodio de podcast.
Te paso {len(articulos)} notas (NOTA 1 a NOTA {len(articulos)}). Es OBLIGATORIO incluir un bloque para
cada una de las {len(articulos)} — ninguna puede quedar afuera del guion, ni siquiera las que te
parezcan menos relevantes.

La duración total depende de cuántas notas haya, no es un número fijo:
- Cada nota tiene que desarrollarse en al menos 70-80 palabras (unos 30 segundos hablados como mínimo) — no la resumas en una sola frase aunque haya muchas notas.
- Aun así, no superes en total las 1800 palabras entre todas las notas (unos 13 minutos hablados) — si hay muchas notas, priorizá y sintetizá más las menos relevantes antes que estirar el episodio de más.

Estructura:
- Apertura breve: empezá literalmente con "Resumen de Economía y Mercado de El País, edición del {hoy}."
  No menciones ni inventes ningún otro día de la semana o fecha distinta a esa.
- Un bloque por cada nota: mencioná al autor y contá con claridad su argumento central, los datos más relevantes y su conclusión. Usá transiciones naturales entre notas.
- Cierre de una o dos frases.

Reglas importantes:
- Texto corrido listo para leer en voz alta: SIN títulos, SIN viñetas, SIN indicaciones entre corchetes, SIN emojis.
- Resumí y parafraseá con tus palabras; no copies frases textuales largas de las notas.
- Si una nota llegó incompleta o cortada por el muro de pago, resumí lo que haya y aclaralo con naturalidad ("en su columna, de la que conocemos el planteo inicial, ...").
- Números y siglas escritos para dicción radial (por ejemplo "tres coma cinco por ciento", "el Banco Central").

NOTAS:
{notas}"""

    respuesta = client.chat.completions.create(
        model=MODELO_GUION,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario},
        ],
        temperature=0.7,
    )
    return respuesta.choices[0].message.content.strip()

# ─── 4. Texto a voz ───────────────────────────────────────────────────────────

def partir_texto(texto: str, max_chars: int) -> list[str]:
    """Parte el guion en trozos de hasta max_chars, cortando en fin de oración."""
    oraciones = re.split(r"(?<=[.!?])\s+", texto)
    trozos, actual = [], ""
    for o in oraciones:
        if len(actual) + len(o) + 1 <= max_chars:
            actual = f"{actual} {o}".strip()
        else:
            if actual:
                trozos.append(actual)
            actual = o
    if actual:
        trozos.append(actual)
    return trozos


def generar_audio(client: OpenAI, guion: str, salida_mp3: str, voz: str) -> None:
    trozos = partir_texto(guion, MAX_CHARS_TTS)
    print(f"🎙️  Generando audio en {len(trozos)} parte(s)...")

    partes = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, trozo in enumerate(trozos, 1):
            destino = os.path.join(tmp, f"parte_{i:02d}.mp3")
            with client.audio.speech.with_streaming_response.create(
                model=MODELO_TTS,
                voice=voz,
                input=trozo,
                instructions=INSTRUCCIONES_VOZ,
                response_format="mp3",
            ) as resp:
                resp.stream_to_file(destino)
            partes.append(destino)
            print(f"   ✔ parte {i}/{len(trozos)}")

        # Concatenar los MP3 (los frames MP3 se pueden unir directamente)
        with open(salida_mp3, "wb") as final:
            for p in partes:
                final.write(Path(p).read_bytes())

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Genera el podcast de Economía y Mercado")
    parser.add_argument("--rtf", default=None, help="Modo viejo: mail del newsletter guardado como .rtf")
    parser.add_argument("--seccion", default=URL_SECCION, help="URL de la sección a scrapear")
    parser.add_argument("--dias", type=int, default=None,
                        help="Ampliar la ventana a los últimos N días. "
                             "Sin esta opción, solo toma las notas publicadas HOY (hora de Montevideo).")
    parser.add_argument("--cookies", default=None, help="cookies.txt exportado del navegador (para notas de suscriptor)")
    parser.add_argument("--voz", default=VOZ_DEFAULT, help=f"Voz del TTS (default: {VOZ_DEFAULT})")
    parser.add_argument("--salida", default=None, help="Nombre del MP3 de salida")
    parser.add_argument("--solo-guion", action="store_true", help="Generar solo el guion, sin audio (para probar barato)")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("❌ Falta la variable de entorno OPENAI_API_KEY.")

    client = OpenAI()
    sesion = crear_sesion(args.cookies)

    # 1. Conseguir los links
    if args.rtf:
        print(f"🔗 Extrayendo links del mail {args.rtf}...")
        links = extraer_links_rtf(args.rtf)
    else:
        print(f"🌐 Buscando notas en {args.seccion} ...")
        links = extraer_links_seccion(sesion, args.seccion)

    if not links:
        sys.exit(
            "❌ No se encontraron links a notas.\n"
            "   Sugerencia: abrí la sección en el navegador, copiá la URL de una nota\n"
            "   y fijate si el patrón coincide con /economia-y-mercado/<slug>."
        )
    print(f"   {len(links)} candidata(s) encontrada(s).")

    # 2. Bajar artículos y filtrar por fecha
    hoy_uy = datetime.now(TZ_UY).date()
    if args.dias:
        limite = datetime.now(timezone.utc) - timedelta(days=args.dias)
        criterio = f"últimos {args.dias} días"
    else:
        limite = None
        criterio = f"publicadas hoy ({hoy_uy.strftime('%d/%m/%Y')})"
    print(f"📰 Bajando artículos ({criterio})...")

    articulos, descartadas = [], 0
    for url in links:
        art = leer_articulo(sesion, url)
        if args.rtf is None and art["fecha"] is not None:
            if limite is not None:
                es_reciente = art["fecha"] >= limite
            else:
                # Comparar la fecha de publicación EN HORA DE MONTEVIDEO con la de hoy
                es_reciente = art["fecha"].astimezone(TZ_UY).date() == hoy_uy
            if not es_reciente:
                descartadas += 1
                continue
        etiqueta_fecha = art["fecha"].astimezone(TZ_UY).strftime("%d/%m %H:%M") if art["fecha"] else "s/f"
        print(f"   • [{etiqueta_fecha}] {art['titulo'][:65]} — {art['autor']}")
        articulos.append(art)
        if len(articulos) >= MAX_NOTAS:
            break

    if descartadas:
        print(f"   ({descartadas} nota(s) descartada(s) por fecha)")
    if not articulos:
        sys.exit(f"❌ Se encontraron {len(links)} links pero ninguna nota {criterio}.\n"
                 "   Si estás probando un día que no es lunes, usá --dias 7.")

    # 3. Guion
    print("✍️  Generando guion con GPT...")
    guion = generar_guion(client, articulos)

    fecha = date.today().isoformat()
    guion_path = f"guion-eym-{fecha}.txt"
    Path(guion_path).write_text(guion, encoding="utf-8")
    print(f"   Guion guardado en {guion_path} ({len(guion.split())} palabras).")

    if args.solo_guion:
        print("⏭️  Modo --solo-guion: no se genera audio.")
        return

    # 4. Audio
    salida = args.salida or f"episodio-eym-{fecha}.mp3"
    generar_audio(client, guion, salida, args.voz)
    print(f"✅ ¡Listo! Episodio generado: {salida}")


if __name__ == "__main__":
    main()
