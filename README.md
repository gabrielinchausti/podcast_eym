# Podcast Economía y Mercado (automatizado)

Cada lunes 06:30 (hora Montevideo), GitHub Actions:
1. Scrapea las notas publicadas ese mismo lunes en la sección Economía y Mercado de El País.
2. Genera un guion de ~5 min con la API de OpenAI y lo convierte a MP3.
3. Sube el MP3 (y el guion) a un Release del repo.
4. Actualiza `docs/feed.xml`, el RSS al que está suscripto Apple Podcasts.

## Puesta en marcha
1. Crear el repo y subir estos archivos.
2. Settings → Secrets and variables → Actions → New repository secret:
   - `OPENAI_API_KEY`: tu key de OpenAI.
   - `EL_PAIS_COOKIES` (opcional): el contenido completo del cookies.txt
     exportado del navegador con la sesión de El País iniciada.
3. Settings → Pages → Source: "Deploy from a branch", carpeta `/docs`.
   El feed queda en: `https://TU-USUARIO.github.io/TU-REPO/feed.xml`
4. En Apple Podcasts: Biblioteca → ⋯ → "Seguir un programa por URL" y pegar esa URL.
5. Probar a mano: pestaña Actions → "Podcast Economía y Mercado" → Run workflow.

## Uso local (para probar)
    pip install -r requirements.txt
    export OPENAI_API_KEY="sk-..."
    python3 podcast_eym.py --cookies cookies.txt --solo-guion   # barato, sin audio
    python3 podcast_eym.py --cookies cookies.txt                # corrida completa

## Mantenimiento
- Las cookies vencen cada tanto: re-exportar cookies.txt y actualizar el secret.
- El cron de GitHub puede demorar hasta ~30 min (ya conocido del proyecto Montecarlo).
