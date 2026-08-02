#!/bin/bash
# ============================================================
# start.sh - Setup + avvio server FastAPI e pipeline Telegram
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── 0. Setup iniziale (una tantum) ──────────────────────────
if [ ! -d "venv" ]; then
    echo "📦 Creazione virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ ! -f ".env" ]; then
    echo "⚠️  File .env non trovato. Copia .env.example in .env e inserisci le chiavi."
    exit 1
fi

# Carica le variabili d'ambiente dal file .env
set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

# Installa le dipendenze se necessario
pip install -r requirements.txt >/dev/null 2>&1 || true

mkdir -p "$PROJECT_DIR/logs"

# ── 1. Avvia il server FastAPI con uvicorn ──────────────────
echo "🚀 Avvio server FastAPI (uvicorn) sulla porta 8000..."
nohup uvicorn server:app --host 0.0.0.0 --port 8000 \
    > "$PROJECT_DIR/logs/server.log" 2>&1 &
SERVER_PID=$!
echo "   ✅ Server PID: $SERVER_PID"

# ── 2. Avvia la pipeline Telegram bot ────────────────────────
echo "🤖 Avvio pipeline Telegram bot..."
nohup python pipeline.py \
    > "$PROJECT_DIR/logs/pipeline.log" 2>&1 &
PIPELINE_PID=$!
echo "   ✅ Pipeline PID: $PIPELINE_PID"

# ── 3. Salva i PID per eventuale stop ────────────────────────
echo "$SERVER_PID" > "$PROJECT_DIR/.server.pid"
echo "$PIPELINE_PID" > "$PROJECT_DIR/.pipeline.pid"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Progetto avviato con successo!"
echo "  📍 Server:  http://localhost:8000"
echo "  📍 Logs:    $PROJECT_DIR/logs/"
echo "  📍 Per fermare:  ./stop.sh"
echo "═══════════════════════════════════════════════════════"
