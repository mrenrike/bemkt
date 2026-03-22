#!/bin/bash
# ============================================================
# BEMKT — Script de deploy (roda após cada git push)
# ============================================================
set -e
APP_DIR="/var/www/bemkt"

echo "==> Atualizando código..."
cd $APP_DIR
git pull origin main

echo "==> Instalando dependências novas (se houver)..."
source venv/bin/activate
pip install -q -r requirements.txt

echo "==> Reiniciando serviço..."
systemctl restart bemkt

echo "==> Deploy concluído! $(date)"
