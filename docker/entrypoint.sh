#!/bin/sh
set -eu

APP_ENV="${APP_ENV:-prod}"
CORS_ORIGINS="${CORS_ORIGINS:-}"
METRIC_SOURCE_MODE="${METRIC_SOURCE_MODE:-real}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

cat > /app/src/backend/.env <<EOF
APP_ENV=${APP_ENV}
CORS_ORIGINS=${CORS_ORIGINS}
METRIC_SOURCE_MODE=${METRIC_SOURCE_MODE}
LOG_LEVEL=${LOG_LEVEL}
EOF

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
