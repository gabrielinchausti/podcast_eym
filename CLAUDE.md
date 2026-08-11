# Podcast Economía y Mercado — Contexto del proyecto

## Qué es esto
Pipeline que genera automáticamente un podcast personal de ~5 minutos resumiendo
las columnas del suplemento **Economía y Mercado** del diario El País (Uruguay),
que se publican los **lunes**. El episodio se escucha en Apple Podcasts durante
el viaje al trabajo del dueño del proyecto (Gabriel).

Este proyecto fue diseñado en conversaciones con Claude en claude.ai. Existe un
proyecto hermano con arquitectura de distribución similar (GitHub Releases + RSS
en GitHub Pages): un podcast que graba el informativo matinal de Radio Montecarlo
(CX20), repo `montecarlo-podcast`.

## Estado: en producción
El pipeline corre automático todos los lunes desde el 13/07/2026. Repo público:
https://github.com/gabrielinchausti/podcast_eym — feed en
https://gabrielinchausti.github.io/podcast_eym/feed.xml

## Arquitectura (4 etapas)
1. **Scraping** (`podcast_eym.py`): entra a https://www.elpais.com.uy/economia-y-mercado,
   junta links de notas con regex sobre el HTML crudo (patrón `/economia-y-mercado/<slug>`),
   baja cada nota y extrae título/autor/fecha/cuerpo desde metadatos
   (`og:title`, `article:author`, `article:published_time`). Usa `curl_cffi` con
   `impersonate="chrome"` en vez de `requests` — El País bloquea por fingerprint TLS.
   En producción corre con `--dias 5` (ventana de ~5 días para no perder columnas de
   jueves/viernes si el run cae más tarde en el día).
2. **Guion**: API de OpenAI (`gpt-4o-mini`) escribe el guion en español rioplatense,
   con reglas de dicción radial (números en palabras). Duración variable: piso de
   ~70-80 palabras por nota (mínimo ~30s hablados), techo total de 1800 palabras;
   instrucción explícita de no omitir ninguna nota recibida.
3. **Audio**: TTS de OpenAI (`gpt-4o-mini-tts`, voz "ash"). El guion se parte en
   trozos de ≤3000 caracteres cortando en fin de oración; los MP3 se concatenan.
4. **Distribución — 100% LOCAL, no GitHub Actions** (`publicar_episodio.sh` +
   `generar_rss.py`): GitHub Actions se probó y se abandonó — El País bloquea el
   rango de IPs de datacenter de los runners (403, incluso con curl_cffi). El
   pipeline completo corre en la Mac de Gabriel vía **launchd**
   (`~/Library/LaunchAgents/com.gabrielinchausti.podcast-eym.plist`), lunes 10:00
   hora Montevideo (coincide con una reunión recurrente de Gabriel, así que la Mac
   siempre está despierta a esa hora — no usamos `pmset` para despertarla del sueño).
   El script sube el MP3+guion a un Release de GitHub (`gh release create`, con
   fallback a `gh release upload --clobber` si el tag ya existe), actualiza y pushea
   `docs/feed.xml`, fuerza un rebuild de Pages (el automático no siempre dispara
   solo), borra Releases de más de 30 días, y limpia los archivos locales.

## Archivos
- `podcast_eym.py` — scraping + guion + audio. `--solo-guion` genera solo el guion
  (sin audio, más barato para probar). `--rtf` es modo legado.
- `generar_rss.py` — mantiene `episodios.json` y regenera `docs/feed.xml`. Retención
  por fecha (30 días, `PODCAST["dias_retencion"]`), no por cantidad fija — imprime
  `VENCIDO:<tag>` por cada episodio que sale de la ventana, para que el script
  externo borre el Release real de GitHub (si no, el feed listaría links rotos).
- `publicar_episodio.sh` — orquesta todo el pipeline de producción (ver arquitectura
  arriba). Loguea a `logs/publicar.log` (gitignored). Manda notificación de macOS
  (`osascript`) si algo falla.
- `~/Library/LaunchAgents/com.gabrielinchausti.podcast-eym.plist` — dispara
  `publicar_episodio.sh` los lunes 10:00. Para probar a mano sin esperar al lunes:
  `launchctl kickstart gui/$(id -u)/com.gabrielinchausti.podcast-eym`.
- `docs/cover.png` — logo del podcast (1400x1400) para `<itunes:image>`.
- `requirements.txt`, `README.md`.
- **NO existe `.github/workflows/`** — se borró a propósito, no dejar uno nuevo ahí
  salvo que el bloqueo de IP de GitHub Actions se resuelva de alguna forma.

## Credenciales — reglas estrictas
- `OPENAI_API_KEY` va como variable de entorno local (en `~/.zshrc`, porque
  `launchd` no hereda el shell interactivo — `publicar_episodio.sh` la sourcea
  explícito). NUNCA en el código, en commits, ni pegada en el chat.
- `cookies.txt` (sesión de El País, exportado con "Get cookies.txt LOCALLY") es
  local, NUNCA se commitea (`.gitignore`). Si la extensión exporta "todos los
  dominios" en vez de solo elpais.com.uy, filtrar con:
  `awk -F'\t' '/^#/ || /^$/ || $1 ~ /elpais\.com\.uy/' archivo_original > cookies.txt`
- **Las cookies vencen (~1 mes) y BLOQUEAN TODO el scraping con 403** (no degradan
  suave como se pensaba originalmente — probado el 10/08/2026). Diagnóstico: probar
  `extraer_links_seccion()` con y sin cookies; si sin cookies anda y con cookies
  da 403, son las cookies. Arreglo: reexportar, reemplazar `cookies.txt`, correr
  `launchctl kickstart gui/$(id -u)/com.gabrielinchausti.podcast-eym` para recuperar
  el episodio de la semana. Gabriel prefiere arreglarlo reactivo cuando pase, no
  quiso automatizar un aviso proactivo (decisión tomada, no volver a proponerlo
  salvo que él lo pida).
- No usar usuario/contraseña de El País en ningún script.

## Cómo trabajar con Gabriel
- Hablarle en español (rioplatense). Explicar cada paso ANTES de ejecutarlo: le gusta
  entender el código a nivel de componente y aprender haciendo; no entregar cajas negras.
- Ir por etapas chicas verificando entendimiento compartido antes de avanzar.
- Conoce Git de proyectos anteriores (commits, branches, rebase vs merge) pero
  agradece que se le expliquen comandos nuevos. Es su primera vez con Claude Code
  específicamente (no solo con Claude) — puede necesitar más contexto sobre el
  funcionamiento de la herramienta en sí (sesiones, memoria, tools) al principio.
- Prefiere salidas concisas y bien organizadas.
- Usa `gh` CLI (instalado y autenticado como `gabrielinchausti`) para todo lo de GitHub.
