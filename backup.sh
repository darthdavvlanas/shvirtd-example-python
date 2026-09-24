#!/usr/bin/env bash
set -euo pipefail

# --- Загружаем секреты из внешнего файла ---
SECRET_FILE="./.backup_secrets"
if [[ ! -f "${SECRET_FILE}" ]]; then
    echo "[!] Файл секретов ${SECRET_FILE} не найден" >&2
    exit 1
fi
source "${SECRET_FILE}"

# --- Настройки ---
BACKUP_DIR="/opt/backup"
NETWORK="myapp_backend"
CONTAINER_NAME="mysql"
MYSQL_HOST="${CONTAINER_NAME}"
MYSQL_USER="${DB_USER}"
MYSQL_PASSWORD="${DB_PASSWORD}"
MYSQL_DATABASE="${DB_NAME}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="/backup/${TIMESTAMP}_${MYSQL_DATABASE}.sql"

echo "[+] $(date) — начинаю бэкап БД '${MYSQL_DATABASE}'"

# --- Запуск контейнера с mysqldump ---
docker run --rm \
  --network "${NETWORK}" \
  --entrypoint "" \
  -v "${BACKUP_DIR}:/backup" \
  schnitzler/mysqldump \
  mysqldump --opt \
    -h "${MYSQL_HOST}" \
    -u "${MYSQL_USER}" \
    -p"${MYSQL_PASSWORD}" \
    "--result-file=${BACKUP_FILE}" \
    "${MYSQL_DATABASE}"

echo "[+] Бэкап завершён: ${BACKUP_DIR}/${TIMESTAMP}_${MYSQL_DATABASE}.sql"