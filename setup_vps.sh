#!/bin/bash
# ============================================================
# BEMKT — Script de instalação do VPS
# Roda como root em Ubuntu 24.04
# Uso: bash setup_vps.sh
# ============================================================
set -e

DOMAIN="appcarrossel.bemkt.com.br"
APP_DIR="/var/www/bemkt"
REPO="https://github.com/mrenrike/bemkt.git"   # <-- trocar
PYTHON="python3.12"

echo "==> [1/8] Atualizando sistema..."
apt-get update -qq && apt-get upgrade -y -qq

echo "==> [2/8] Instalando dependências do sistema..."
apt-get install -y -qq \
  python3.12 python3.12-venv python3-pip \
  nginx certbot python3-certbot-nginx \
  git curl unzip \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
  libcairo2 libasound2t64 libxshmfence1 \
  fonts-liberation fonts-noto-color-emoji

echo "==> [3/8] Criando diretório do app..."
mkdir -p $APP_DIR/carrosseis $APP_DIR/uploads
cd $APP_DIR

echo "==> [4/8] Clonando repositório..."
git clone $REPO . || (git fetch && git reset --hard origin/main)

echo "==> [5/8] Configurando ambiente Python..."
$PYTHON -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> [6/8] Instalando Playwright + Chromium..."
playwright install chromium
playwright install-deps chromium

echo "==> [7/8] Configurando serviço systemd..."
cat > /etc/systemd/system/bemkt.service << SERVICE
[Unit]
Description=BEMKT FastAPI App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable bemkt
systemctl start bemkt

echo "==> [8/8] Configurando nginx..."
cat > /etc/nginx/sites-available/bemkt << NGINX
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/bemkt /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "============================================"
echo " Instalação concluída!"
echo " Agora rode: certbot --nginx -d $DOMAIN"
echo "============================================"
