#!/bin/bash
# ============================================================
# stop.sh - Ferma server FastAPI e pipeline Telegram bot
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Fermo server FastAPI..."
if [ -f .server.pid ]; then
    kill "$(cat .server.pid)" 2>/dev/null && echo "   ✅ Server fermato" || echo "   ⚠️  Server non in esecuzione"
    rm -f .server.pid
fi

echo "🛑 Fermo pipeline Telegram bot..."
if [ -f .pipeline.pid ]; then
    kill "$(cat .pipeline.pid)" 2>/dev/null && echo "   ✅ Pipeline fermata" || echo "   ⚠️  Pipeline non in esecuzione"
    rm -f .pipeline.pid
fi

echo ""
echo "✅ Tutti i processi fermati."
