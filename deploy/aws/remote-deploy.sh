#!/usr/bin/env bash
# Run on EC2 after tarball + env files are uploaded to /tmp.
set -euo pipefail

REMOTE_ROOT="/opt/creativestudio"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-http://13.235.37.173}"

mkdir -p "$REMOTE_ROOT/backend/uploads"
if [ -d "$REMOTE_ROOT" ]; then
  sudo chown -R "$(whoami):$(whoami)" "$REMOTE_ROOT"
  sudo chmod -R u+rwX "$REMOTE_ROOT"
fi
STAGE="$(mktemp -d)"
tar -xzf /tmp/creativestudio-deploy.tar.gz -C "$STAGE" --no-same-owner --no-same-permissions --mode=u+rwX
sudo rsync -a --delete \
  --exclude 'backend/uploads/' \
  --exclude 'backend/.env' \
  --exclude 'deploy/aws/.env' \
  "$STAGE/" "$REMOTE_ROOT/"
sudo rm -rf "$STAGE"
sudo chown -R "$(whoami):$(whoami)" "$REMOTE_ROOT"
sudo chmod -R u+rwX "$REMOTE_ROOT"
mv /tmp/backend.env "$REMOTE_ROOT/backend/.env"
mkdir -p "$REMOTE_ROOT/deploy/aws"
mv /tmp/deploy.env "$REMOTE_ROOT/deploy/aws/.env"

cd "$REMOTE_ROOT"

PUBLIC_ORIGIN="$(grep -E '^PUBLIC_ORIGIN=' deploy/aws/.env | head -1 | cut -d= -f2- | tr -d '\"')"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-http://13.235.37.173}"
DOMAIN="$(grep -E '^DOMAIN=' deploy/aws/.env | head -1 | cut -d= -f2- | tr -d '\"')"
DOMAIN="${DOMAIN:-creativestudio.tools}"
CERT_FILE="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
mkdir -p deploy/aws/certbot-www deploy/aws/nginx
if sudo test -f "$CERT_FILE"; then
  cp deploy/aws/nginx/default.ssl.conf deploy/aws/nginx/active.conf
  echo "Using HTTPS nginx config (certificate present)."
else
  cp deploy/aws/nginx/default.bootstrap.conf deploy/aws/nginx/active.conf
  echo "Using HTTP bootstrap nginx config (no certificate yet)."
fi

if grep -q '^APP_ENV=' backend/.env; then
  sed -i 's/^APP_ENV=.*/APP_ENV=production/' backend/.env
else
  echo 'APP_ENV=production' >> backend/.env
fi

CORS_LINE="CORS_ORIGINS=[\"${PUBLIC_ORIGIN}\"]"
if grep -q '^CORS_ORIGINS=' backend/.env; then
  sed -i "s|^CORS_ORIGINS=.*|${CORS_LINE}|" backend/.env
else
  echo "$CORS_LINE" >> backend/.env
fi

if grep -q '^PUBLIC_APP_URL=' backend/.env; then
  sed -i "s|^PUBLIC_APP_URL=.*|PUBLIC_APP_URL=${PUBLIC_ORIGIN}|" backend/.env
else
  echo "PUBLIC_APP_URL=${PUBLIC_ORIGIN}" >> backend/.env
fi

sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d --build
sudo docker compose -f deploy/aws/docker-compose.prod.yml ps

sleep 5
if curl -sf http://127.0.0.1/health; then
  echo " HTTP health OK"
else
  echo " HTTP health check failed (containers may still be starting)"
fi

if sudo test -f "$CERT_FILE"; then
  NGINX_PORTS="$(sudo docker ps --format '{{.Ports}}' --filter name=creativestudio_nginx)"
  if ! grep -q '443' <<<"$NGINX_PORTS"; then
    echo "ERROR: Let's Encrypt cert exists but nginx is not publishing port 443."
    echo "       Fix deploy/aws/docker-compose.prod.yml (443:443 + cert volumes) and redeploy."
    exit 1
  fi
  if curl -sfk "https://127.0.0.1/health" -H "Host: ${DOMAIN}" >/dev/null; then
    echo " HTTPS health OK"
  else
    echo "WARNING: HTTPS health check failed — run: bash deploy/aws/setup-ssl.sh"
  fi
fi
