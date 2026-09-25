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

sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d --build
sudo docker compose -f deploy/aws/docker-compose.prod.yml ps

sleep 5
if curl -sf http://127.0.0.1/health; then
  echo " health OK"
else
  echo " health check failed (containers may still be starting)"
fi
