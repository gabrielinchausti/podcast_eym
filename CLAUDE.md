# Podcast Economía y Mercado — Contexto del proyecto

## Qué es esto
Pipeline que genera automáticamente un podcast personal de ~5 minutos resumiendo
las columnas del suplemento **Economía y Mercado** del diario El País (Uruguay),
que se publican los **lunes**. El episodio se escucha en Apple Podcasts durante
el viaje al trabajo del dueño del proyecto (Gabriel).

Este proyecto fue diseñado en conversaciones con Claude en claude.ai. Existe un
proyecto hermano ya funcionando con la misma arquitectura de distribución:
un podcast que graba el informativo matinal de Radio Montecarlo (CX20) usando
GitHub Actions + Releases + RSS en GitHub Pages + cron-job.org.

## Arquitectura (4 etapas)
1. **Scraping** (`podcast_eym.py`): entra a https://www.elpais.com.uy/economia-y-mercado,
   junta links de notas con regex sobre el HTML crudo (patrón `/economia-y-mercado/<slug>`),
   baja cada nota y extrae título/autor/fecha/cuerpo desde metadatos
   (`og:title`, `article:author`, `article:published_time`).
   **Por defecto solo toma notas publicadas HOY en hora de Montevideo** (zoneinfo
   `America/Montevideo`); `--dias N` amplía la ventana (útil para probar en días
   que no son lunes).
2. **Guion**: API de OpenAI (`gpt-4o-mini`) escribe un guion de 750-850 palabras
   en español rioplatense, con reglas de dicción radial (números en palabras).
3. **Audio**: TTS de OpenAI (`gpt-4o-mini-tts`, voz "ash"). El guion se parte en
   trozos de ≤3000 caracteres cortando en fin de oración; los MP3 se concatenan.
4. **Distribución** (`generar_rss.py` + `.github/workflows/podcast.yml`):
   GitHub Actions corre lunes 09:30 UTC (06:30 Montevideo), sube MP3 y guion a un
   Release, actualiza `docs/feed.xml` (servido por GitHub Pages) y commitea.
   Apple Podcasts sigue ese feed por URL.

## Archivos
- `podcast_eym.py` — pipeline principal (scraping + guion + audio). Tiene `--solo-guion`
  para probar barato sin generar audio, y `--rtf` como modo legado (scrapear desde el
  mail del newsletter guardado como RTF, herencia de un scraper anterior en R).
- `generar_rss.py` — mantiene `episodios.json` y regenera `docs/feed.xml`. Idempotente
  (correr dos veces el mismo día reemplaza, no duplica).
- `.github/workflows/podcast.yml` — el workflow. Secrets esperados: `OPENAI_API_KEY`
  y `EL_PAIS_COOKIES` (contenido del cookies.txt, opcional).
- `requirements.txt`, `README.md`.

## Estado: qué está probado y qué NO
Probado (offline, con datos simulados):
- Sintaxis de todo; extracción de links de sección (links en <a> y en JSON embebido);
  partido de texto para TTS; generador de RSS de punta a punta; filtro "solo hoy"
  en zona Montevideo; YAML del workflow válido.

**NO probado (pendiente, en este orden):**
1. Que el regex de links matchee la portada REAL de la sección (Claude en claude.ai
   no pudo verificarla: El País bloquea sus fetchers; desde esta máquina debería andar).
2. Que las cookies de sesión den acceso al texto completo de notas "Contenido Exclusivo".
3. Llamadas reales a OpenAI (guion y TTS) — probar primero con `--solo-guion`.
4. La cadena completa en GitHub Actions. Riesgo conocido: El País podría bloquear
   las IPs de datacenter de GitHub. Plan B si pasa: correr local con cron/launchd.

## Credenciales — reglas estrictas
- `OPENAI_API_KEY` va como variable de entorno local y como secret en GitHub. NUNCA
  en el código, en commits, ni pegada en el chat.
- `cookies.txt` (sesión de El País, exportado con una extensión tipo "Get cookies.txt
  LOCALLY") es un archivo local que NUNCA se commitea. Agregarlo a `.gitignore` junto
  con `episodios.json` de pruebas locales, `*.mp3` y `guion-*.txt`.
  En Actions viaja como secret `EL_PAIS_COOKIES`.
- Las cookies vencen: si los episodios salen "recortados", re-exportar y actualizar el secret.
- No usar usuario/contraseña de El País en ningún script.

## Cómo trabajar con Gabriel
- Hablarle en español (rioplatense). Explicar cada paso ANTES de ejecutarlo: le gusta
  entender el código a nivel de componente y aprender haciendo; no entregar cajas negras.
- Ir por etapas chicas verificando entendimiento compartido antes de avanzar.
- Conoce Git de proyectos anteriores (commits, branches, rebase vs merge) pero
  agradece que se le expliquen comandos nuevos.
- Prefiere salidas concisas y bien organizadas.

## Primera sesión sugerida
1. Verificar estructura de carpeta y crear `.gitignore`.
2. `pip install -r requirements.txt` (o venv).
3. Probar scraping real: correr con `--solo-guion --dias 7` (si no es lunes) y revisar
   la lista de notas detectadas. Ajustar regex/selectores si la portada real difiere.
4. Probar con cookies para validar acceso de suscriptor.
5. Corrida completa con audio; escuchar el MP3.
6. Recién entonces: crear repo en GitHub (privado o público según decida Gabriel;
   ojo que Pages en repo privado requiere plan pago), pushear, cargar secrets
   (Gabriel los carga en la web de GitHub), habilitar Pages desde /docs,
   y disparar el workflow a mano (workflow_dispatch) para validar la cadena.
