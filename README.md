# CreativeStudio AI

Multi-tenant AI creative generation platform for Meta Ads. Generate on-brand ad copy, hooks, and captions using AI.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 · TypeScript · Tailwind CSS · Axios |
| Backend | Python FastAPI · SQLAlchemy (async) · Alembic |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Auth | JWT (access + refresh tokens) |
| AI | Anthropic Claude · OpenAI GPT-4o |
| Files | Local storage (uploads/) |
| Infra | Docker · Docker Compose |

## Quick Start (Docker)

```bash
# 1. Clone and enter directory
cd "CreativeStudio AI"

# 2. Copy env file and fill in your keys
cp .env.example backend/.env
cp .env.example frontend/.env.local

# 3. Start everything
docker-compose up --build

# App:      http://localhost:3000
# API:      http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Manual Development Setup

### Backend

```bash
cd backend

# Create virtualenv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit env
cp .env.example .env
# Edit .env — add DATABASE_URL, SECRET_KEY, ANTHROPIC_API_KEY, etc.

# Run database migrations
alembic upgrade head

# Start dev server
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Copy and edit env
cp .env.example .env.local
# Edit NEXT_PUBLIC_API_URL

# Start dev server
npm run dev
```

## Project Structure

```
CreativeStudio AI/
├── backend/
│   ├── app/
│   │   ├── core/          # config, database, security
│   │   ├── models/        # SQLAlchemy ORM models
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── api/v1/        # FastAPI route handlers
│   │   ├── services/      # Business logic
│   │   └── middleware/    # JWT auth middleware
│   ├── alembic/           # DB migrations
│   ├── uploads/           # Uploaded files (local storage)
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/               # Next.js App Router pages
│   │   ├── (auth)/        # Login, Register
│   │   ├── (dashboard)/   # All dashboard pages
│   │   └── onboarding/    # 3-step onboarding wizard
│   ├── components/        # Reusable React components
│   ├── lib/               # API client, auth helpers, utils
│   ├── hooks/             # React hooks
│   ├── types/             # TypeScript interfaces
│   └── Dockerfile
├── docker-compose.yml
├── init.sql               # PostgreSQL schema
└── .env.example
```

## Environment Variables

See `.env.example` for all required variables. Key ones:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing secret (generate: `openssl rand -hex 32`) |
| `ANTHROPIC_API_KEY` | Claude API key (ai.anthropic.com) |
| `OPENAI_API_KEY` | OpenAI API key (optional) |
| `UPLOAD_DIR` | Local path for file uploads |

## API Documentation

Once running, visit `http://localhost:8000/docs` for the interactive Swagger UI.

Key endpoints:

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account + tenant |
| POST | `/api/v1/auth/login` | Login, get JWT tokens |
| GET | `/api/v1/brands` | List brands |
| POST | `/api/v1/briefs` | Create brief |
| POST | `/api/v1/briefs/{id}/generate` | Generate AI variants |
| GET | `/api/v1/variants` | List all variants |
| GET | `/api/v1/performance/dashboard` | Dashboard KPIs |
| POST | `/api/v1/assets/upload` | Upload file |

## Database Migrations

```bash
cd backend

# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Default Admin Account

After first run, register via `/api/v1/auth/register` — the first user of each tenant gets `role=admin` automatically.

## File Storage

Uploaded files are stored in `backend/uploads/{tenant_id}/{subfolder}/`. In Docker the `uploads/` folder is mounted as a volume so files persist across restarts.
