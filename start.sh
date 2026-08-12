#!/bin/bash
# ============================================================
# start.sh - Setup + start FastAPI server and Telegram pipeline
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── 0. Initial setup (one-time) ─────────────────────────────
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Copy .env.example to .env and add your keys."
    exit 1
fi

# Load environment variables from the .env file
set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

# Install dependencies if needed
pip install -r requirements.txt >/dev/null 2>&1 || true

mkdir -p "$PROJECT_DIR/logs"

# ── 1. Start the FastAPI server with uvicorn ────────────────
echo "🚀 Starting FastAPI server (uvicorn) on port 8006..."
nohup uvicorn server:app --host 0.0.0.0 --port 8006 \
    > "$PROJECT_DIR/logs/server.log" 2>&1 &
SERVER_PID=$!
echo "   ✅ Server PID: $SERVER_PID"

# ── 2. Start the Telegram bot pipeline ──────────────────────
echo "🤖 Starting Telegram bot pipeline..."
nohup python pipeline.py \
    > "$PROJECT_DIR/logs/pipeline.log" 2>&1 &
PIPELINE_PID=$!
echo "   ✅ Pipeline PID: $PIPELINE_PID"

# ── 3. Save PIDs for later stop ─────────────────────────────
echo "$SERVER_PID" > "$PROJECT_DIR/.server.pid"
echo "$PIPELINE_PID" > "$PROJECT_DIR/.pipeline.pid"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Project started successfully!"
echo "  📍 Server:  http://localhost:8006"
echo "  📍 Logs:    $PROJECT_DIR/logs/"
echo "  📍 To stop:  ./stop.sh"
echo "═══════════════════════════════════════════════════════"
