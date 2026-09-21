#!/usr/bin/env bash
set -euo pipefail
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-http://13.235.37.173}"
sudo mv /tmp/backend.env /opt/creativestudio/backend/.env
sudo chown root:root /opt/creativestudio/backend/.env
cd /opt/creativestudio
if grep -q '^APP_ENV=' backend/.env; then
  sudo sed -i 's/^APP_ENV=.*/APP_ENV=production/' backend/.env
else
  echo 'APP_ENV=production' | sudo tee -a backend/.env >/dev/null
fi
CORS_LINE="CORS_ORIGINS=[\"${PUBLIC_ORIGIN}\"]"
if grep -q '^CORS_ORIGINS=' backend/.env; then
  sudo sed -i "s|^CORS_ORIGINS=.*|${CORS_LINE}|" backend/.env
else
  echo "$CORS_LINE" | sudo tee -a backend/.env >/dev/null
fi
sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d --force-recreate backend
sleep 8
sudo docker logs creativestudio_backend --tail 25
curl -sf http://127.0.0.1/health && echo " health OK" || echo " health FAILED"
