# AWS EC2 deployment

Deploy Creative Studio AI to a single Ubuntu EC2 instance with Docker, nginx, Postgres, and persistent upload volume.

## URLs (default IP)

| Service | URL |
|---------|-----|
| App | http://13.235.37.173 |
| API | http://13.235.37.173/api/v1 |
| Health | http://13.235.37.173/health |
| API docs | http://13.235.37.173/docs |

Replace the IP with your domain when you attach one (`PUBLIC_ORIGIN` / `CORS_ORIGINS`).

## Prerequisites (Windows)

1. PuTTY tools (`plink`, `pscp`) — deploy script uses portable PuTTY from `%TEMP%\putty-portable` or installed PuTTY.
2. SSH key: `DM-Creative-studioppk.ppk` (from email).
3. Local `backend/.env` with API keys (OpenRouter, Higgsfield, etc.).

## One-command deploy from Windows

```powershell
powershell -ExecutionPolicy Bypass -File deploy/aws/deploy-from-windows.ps1
```

Optional parameters:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/aws/deploy-from-windows.ps1 `
  -ServerIp 13.235.37.173 `
  -PpkPath "$env:USERPROFILE\Downloads\DM-Creative-studioppk.ppk" `
  -PublicOrigin "http://13.235.37.173"
```

First run creates `deploy/aws/.env` with random Postgres/Redis passwords (keep this file safe).

## SSH with PuTTY

```
Host: ubuntu@13.235.37.173
Port: 22
Key:  DM-Creative-studioppk.ppk
```

PuTTY / plink:

```powershell
plink -batch -hostkey "ssh-ed25519 SHA256:jTOaSeVI4b8N91dCskmU0wNyKUR/TsJPI+fFkOa3X7I" `
  -i "$env:USERPROFILE\Downloads\DM-Creative-studioppk.ppk" ubuntu@13.235.37.173
```

## On-server management

```bash
cd /opt/creativestudio
sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env ps
sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env logs -f backend
sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d --build
```

## EC2 security group

Allow inbound:

- 22 (SSH)
- 80 (HTTP app)
- 443 (HTTPS when you add TLS)

## Media storage

Uploads live in Docker volume `aws_uploads_data` (survives container restarts). For S3, add a storage backend in `file_service.py` (future work).

## Custom domain

1. Point DNS A record to the EC2 IP.
2. Update `deploy/aws/.env`: `PUBLIC_ORIGIN=https://your-domain.com`
3. Update `backend/.env`: `CORS_ORIGINS=["https://your-domain.com"]`
4. Rebuild frontend (API URL is baked at build time):

```bash
cd /opt/creativestudio
sudo docker compose -f deploy/aws/docker-compose.prod.yml --env-file deploy/aws/.env up -d --build frontend nginx
```

5. Add TLS with Certbot + nginx or AWS ALB.
