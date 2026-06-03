#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-regassistant}"
APP_DIR="${APP_DIR:-/opt/regulation-assistant}"
SERVICE_NAME="${SERVICE_NAME:-reg-assistant}"
PORT="${REG_ASSISTANT_PORT:-8083}"
HOST="${REG_ASSISTANT_HOST:-0.0.0.0}"
ADMIN_EMAIL="${REG_ASSISTANT_ADMIN_EMAIL:-xingchi.wang@zf.com}"
PREWARM_CACHE="${REG_ASSISTANT_PREWARM_CACHE:-1}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root, for example: sudo bash deploy/install_on_ubuntu.sh"
  exit 1
fi

apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  rsync \
  ghostscript \
  ocrmypdf \
  tesseract-ocr \
  tesseract-ocr-eng \
  tesseract-ocr-chi-sim

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".env" \
  --exclude ".tools" \
  --exclude "server*.log" \
  --exclude "dist" \
  --exclude "data/users.json" \
  --exclude "data/feedback.jsonl" \
  --exclude "data/usage.jsonl" \
  --exclude "data/uploads" \
  --exclude "data/regulations/_cache" \
  ./ "${APP_DIR}/"

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  cat > "${APP_DIR}/.env" <<ENV
REG_ASSISTANT_HOST=${HOST}
REG_ASSISTANT_PORT=${PORT}
REG_ASSISTANT_ADMIN_EMAIL=${ADMIN_EMAIL}
REG_ASSISTANT_OCR_ENABLED=1
REG_ASSISTANT_OCR_LANGS=eng
# DeepSeek official API:
# DEEPSEEK_API_KEY=your-deepseek-api-key
# REG_ASSISTANT_LLM_BASE_URL=https://api.deepseek.com
# REG_ASSISTANT_LLM_FLASH_MODEL=deepseek-chat
# REG_ASSISTANT_LLM_PRO_MODEL=deepseek-reasoner
# Alibaba Cloud Model Studio (bailian) alternative:
# DASHSCOPE_API_KEY=your-dashscope-api-key
# REG_ASSISTANT_LLM_FLASH_MODEL=deepseek-v4-flash
# REG_ASSISTANT_LLM_PRO_MODEL=deepseek-v4-pro
ENV
fi

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [[ "${PREWARM_CACHE}" != "0" ]]; then
  echo "Prewarming regulation corpus cache. First OCR run can take several minutes; later runs should reuse the cache."
  runuser -u "${APP_USER}" -- bash -lc "cd '${APP_DIR}' && '${APP_DIR}/.venv/bin/python' -c 'import app; chunks = app.load_corpus_chunks(); print(\"Prewarmed %d regulation chunks\" % len(chunks))'"
fi

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Commercial Vehicle Regulation Assistant
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python -W ignore::DeprecationWarning ${APP_DIR}/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl --no-pager --full status "${SERVICE_NAME}" || true

echo "Health check:"
curl -fsS "http://127.0.0.1:${PORT}/healthz" || true
echo
echo "Installed ${SERVICE_NAME} at ${APP_DIR}, listening on ${HOST}:${PORT}"
