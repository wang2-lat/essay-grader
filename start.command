#!/bin/bash
# Double-click on macOS (or run ./start.command) to launch your OWN local grading
# backend. Nothing is sent to the plugin author — you use your own model access.
set -e
cd "$(dirname "$0")"

echo "▶ 作文评分 · 本地后端启动中…"

# 1) Python check
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ 需要先安装 Python 3（https://www.python.org/downloads/）"; exit 1
fi

# 2) venv + deps (first run only)
if [ ! -d .venv ]; then
  echo "  创建虚拟环境…"; python3 -m venv .venv
fi
echo "  安装依赖（首次较慢）…"
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

# 3) first-run .env (no model key yet — you set it on the setup page)
if [ ! -f .env ]; then
  echo "  生成本地配置 .env …"
  SECRET=$(./.venv/bin/python -c 'import secrets;print(secrets.token_hex(32))')
  cat > .env <<EOF
# 本地后端配置。GRADER_API_KEY 留空，启动后在 http://127.0.0.1:8011/setup 填写你自己的来源。
GRADER_BASE_URL=http://127.0.0.1:11434/v1
GRADER_API_KEY=
GRADER_MODEL=qwen2.5:7b
GRADER_MAX_TOKENS=8000
SESSION_SECRET=$SECRET
GRADER_API_TOKEN=
# Abuse guard for YOUR OWN key (set any to 0 to disable):
GRADER_MAX_CHARS=15000
GRADER_RATE_PER_MIN=12
GRADER_DAILY_LIMIT=200
EOF
fi

# 4) open the setup page, then run the server
( sleep 2; open "http://127.0.0.1:8011/setup" >/dev/null 2>&1 || true ) &
echo "✓ 已启动：http://127.0.0.1:8011  （按 Ctrl+C 停止）"
exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8011
