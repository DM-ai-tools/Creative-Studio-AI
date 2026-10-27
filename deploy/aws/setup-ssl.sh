#!/usr/bin/env bash
# Issue or renew Let's Encrypt cert and switch nginx to HTTPS (run on EC2 as ubuntu).
set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/opt/creativestudio}"
WEBROOT="${REMOTE_ROOT}/deploy/aws/certbot-www"

cd "$REMOTE_ROOT"
PUBLIC_ORIGIN="$(grep -E '^PUBLIC_ORIGIN=' deploy/aws/.env | head -1 | cut -d= -f2- | tr -d '\"')"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-$(grep -E '^CERTBOT_EMAIL=' deploy/aws/.env | head -1 | cut -d= -f2- | tr -d '\"')}"
DOMAIN="${DOMAIN:-$(grep -E '^DOMAIN=' deploy/aws/.env | head -1 | cut -d= -f2- | tr -d '\"')}"
DOMAIN="${DOMAIN:-creativestudio.tools}"
EMAIL="${CERTBOT_EMAIL:-admin@creativestudio.tools}"
CERT_PATH="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

mkdir -p "$WEBROOT" deploy/aws/nginx
sudo mkdir -p /etc/letsencrypt

if ! command -v certbot >/dev/null 2>&1; then
  echo "Installing certbot..."
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y certbot
fi

select_nginx_conf() {
  if sudo test -f "$CERT_PATH"; then
    cp deploy/aws/nginx/default.ssl.conf deploy/aws/nginx/active.conf
  else
    cp deploy/aws/nginx/default.bootstrap.conf deploy/aws/nginx/active.conf
  fi
}

select_nginx_conf
sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d nginx

if ! sudo test -f "$CERT_PATH"; then
  echo "Requesting certificate for ${DOMAIN}..."
  if ! sudo certbot certonly --webroot \
    -w "$WEBROOT" \
    -d "$DOMAIN" \
    -d "www.${DOMAIN}" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -n \
    --non-interactive; then
    echo "Retrying certificate for apex only (www may not be in DNS)..."
    sudo certbot certonly --webroot \
      -w "$WEBROOT" \
      -d "$DOMAIN" \
      --email "$EMAIL" \
      --agree-tos \
      --no-eff-email \
      -n \
      --non-interactive
  fi
  cp deploy/aws/nginx/default.ssl.conf deploy/aws/nginx/active.conf
  sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d --force-recreate nginx
fi

if grep -q '^PUBLIC_ORIGIN=http://' deploy/aws/.env; then
  sudo sed -i "s|^PUBLIC_ORIGIN=.*|PUBLIC_ORIGIN=https://${DOMAIN}|" deploy/aws/.env
  PUBLIC_ORIGIN="https://${DOMAIN}"
fi

CORS_LINE="CORS_ORIGINS=[\"https://${DOMAIN}\"]"
if grep -q '^CORS_ORIGINS=' backend/.env; then
  sudo sed -i "s|^CORS_ORIGINS=.*|${CORS_LINE}|" backend/.env
else
  echo "$CORS_LINE" | sudo tee -a backend/.env >/dev/null
fi

echo "Rebuilding frontend with HTTPS API URL..."
sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d --build frontend backend nginx

sleep 5
if curl -sf "https://${DOMAIN}/health" >/dev/null; then
  echo "HTTPS health OK: https://${DOMAIN}/health"
elif curl -sf "http://127.0.0.1/health" >/dev/null; then
  echo "HTTP health OK (check security group allows 443 and DNS points to this host)"
else
  echo "Health check failed — inspect: sudo docker compose -f deploy/aws/docker-compose.prod.yml logs nginx"
  exit 1
fi

if ! sudo grep -q "certbot renew" /etc/cron.d/creativestudio-certbot 2>/dev/null; then
  echo "0 3 * * * root certbot renew --quiet --deploy-hook 'docker exec creativestudio_nginx nginx -s reload'" | \
    sudo tee /etc/cron.d/creativestudio-certbot >/dev/null
  sudo chmod 644 /etc/cron.d/creativestudio-certbot
  echo "Installed daily cert renewal cron (03:00 UTC)."
fi

echo "Done. App: https://${DOMAIN}"
