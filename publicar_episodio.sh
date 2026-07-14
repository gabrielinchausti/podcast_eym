#!/bin/zsh
# Pipeline completo: genera el episodio y lo publica en GitHub.
# Pensado para correr sin supervisión desde launchd (ver eym.launchd.plist).
set -euo pipefail

PROJECT_DIR="/Users/gabrielinchausti/Dropbox/Github/podcast_eym"
REPO="gabrielinchausti/podcast_eym"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/publicar.log"

mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

trap 'osascript -e "display notification \"Revisá logs/publicar.log\" with title \"Podcast EyM: falló la publicación\""' ERR

echo "===== $(date '+%Y-%m-%d %H:%M:%S') Arrancando publicación ====="

export PATH="/opt/homebrew/bin:$PATH"
source ~/.zshrc 2>/dev/null || true

cd "$PROJECT_DIR"
PYTHON="$PROJECT_DIR/venv/bin/python3"

FECHA=$(date +%F)
MP3="episodio-eym-$FECHA.mp3"
GUION="guion-eym-$FECHA.txt"
TAG="eym-$FECHA"

echo "Paso 1/6: generando episodio (scraping + guion + audio)..."
"$PYTHON" podcast_eym.py --dias 5 --cookies cookies.txt --salida "$MP3"

if [ ! -f "$MP3" ] || [ ! -f "$GUION" ]; then
    echo "ERROR: no se generaron los archivos esperados ($MP3 / $GUION)."
    exit 1
fi

echo "Paso 2/6: subiendo Release a GitHub..."
gh release create "$TAG" \
    --repo "$REPO" \
    --title "Economía y Mercado — $FECHA" \
    --notes "Episodio generado automáticamente." \
    "$MP3" "$GUION" \
  || gh release upload "$TAG" "$MP3" "$GUION" --repo "$REPO" --clobber

MP3_URL="https://github.com/$REPO/releases/download/$TAG/$MP3"
BYTES=$(stat -f%z "$MP3")

echo "Paso 3/6: actualizando feed RSS..."
SALIDA_RSS=$("$PYTHON" generar_rss.py \
    --titulo "Economía y Mercado — $FECHA" \
    --url "$MP3_URL" \
    --bytes "$BYTES")
echo "$SALIDA_RSS"

echo "Paso 4/6: borrando releases de más de 30 días (si hay)..."
VENCIDOS=$(echo "$SALIDA_RSS" | grep "^VENCIDO:" | cut -d: -f2 || true)
if [ -n "$VENCIDOS" ]; then
    echo "$VENCIDOS" | while read -r tag_viejo; do
        echo "  Borrando release $tag_viejo..."
        gh release delete "$tag_viejo" --repo "$REPO" --yes --cleanup-tag \
            || echo "  (no se pudo borrar $tag_viejo, sigo igual)"
    done
else
    echo "  Ningún release vencido esta vez."
fi

echo "Paso 5/6: commiteando feed actualizado..."
git add docs/feed.xml episodios.json
git commit -m "Episodio $FECHA" || echo "  Sin cambios para commitear."
git push

echo "  Forzando rebuild de GitHub Pages (el automático a veces no dispara)..."
gh api "repos/$REPO/pages/builds" -X POST >/dev/null || echo "  (no se pudo forzar el rebuild, GitHub debería igual dispararlo solo)"

echo "Paso 6/6: limpiando archivos locales..."
rm -f "$MP3" "$GUION"

osascript -e "display notification \"Episodio del $FECHA publicado.\" with title \"Podcast EyM\""
echo "===== $(date '+%Y-%m-%d %H:%M:%S') Publicación completa ====="
