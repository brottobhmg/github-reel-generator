#!/bin/bash
# ============================================================
# stop.sh - Stop FastAPI server and Telegram bot pipeline
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Stopping FastAPI server..."
if [ -f .server.pid ]; then
    kill "$(cat .server.pid)" 2>/dev/null && echo "   ✅ Server stopped" || echo "   ⚠️  Server not running"
    rm -f .server.pid
fi

echo "🛑 Stopping Telegram bot pipeline..."
if [ -f .pipeline.pid ]; then
    kill "$(cat .pipeline.pid)" 2>/dev/null && echo "   ✅ Pipeline stopped" || echo "   ⚠️  Pipeline not running"
    rm -f .pipeline.pid
fi

echo ""
echo "✅ All processes stopped."
