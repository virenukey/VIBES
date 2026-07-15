# Vibes Backend

Backend API for the Vibes inventory and restaurant management platform. Built with FastAPI and PostgreSQL, supporting multi-tenant operations across inventory, dishes, wastage, orders, and reconciliation.

---

## Tech Stack

- **Framework:** FastAPI
- **ORM:** SQLAlchemy 2.x
- **Database:** PostgreSQL 15 (via psycopg2)
- **Migrations:** Alembic
- **Task Queue:** Celery + Redis
- **Auth:** JWT (python-jose + passlib)
- **File Storage:** Local or AWS S3
- **Runtime:** Python 3.11

---

## Project Structure

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── authentication/   # Auth & tenant routes
│   │   └── endpoints/        # inventory, dishes, wastage, orders, alerts, reconciliation
│   ├── core/                 # Config, security, logging
│   ├── db/                   # Session, base, mixins, tenant
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── services/             # Business logic
│   └── utils/                # Unit conversion, batch helpers, file upload
├── alembic/                  # DB migration scripts
├── env/
│   └── .env.local            # Environment config
├── uploads/                  # Local file uploads (wastage images)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── alembic.ini
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/virenukey/VIBES.git
cd VIBES/backend
```

### 2. Create environment file

Create `env/.env.local`:

```env
ENVIRONMENT=local

DB_HOST=db
DB_PORT=5432
DB_NAME=vibes_local_db
DB_USER=postgres
DB_PASSWORD=password

SECRET_KEY="for_example"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_DAYS=1

DATABASE_URL=postgresql://postgres:password@db:5432/vibes_local_db
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

ALEMBIC_URL=postgresql+psycopg2://postgres:password@db:5432/vibes_local_db

CORS_ORIGINS="http://localhost:5173"
```

### 3. Build and start all services

```bash
docker-compose -f docker-compose-local.yml up -d --build
```

This starts 5 services:

| Service         | Description                             | Port |
|-----------------|-----------------------------------------|------|
| `db`            | PostgreSQL 15                           | 5433 |
| `redis`         | Redis 7                                 | 6379 |
| `api`           | FastAPI (auto-runs migrations on start) | 8000 |
| `celery_worker` | Background task worker                  | —    |
| `celery_beat`   | Scheduled task scheduler                | —    |

Migrations run automatically when the `api` container starts. No manual step needed.

### 4. Access the app

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

### 5. Stop services

```bash
# Stop services
docker-compose -f docker-compose-local.yml down

# Stop and remove everything including volumes
docker-compose -f docker-compose-local.yml down -v
```

---

## Useful Docker Commands

```bash
# Start services
docker-compose -f docker-compose-local.yml up -d

# Rebuild and start
docker-compose -f docker-compose-local.yml up -d --build

# Stop services
docker-compose -f docker-compose-local.yml down

# Stop and remove everything including volumes
docker-compose -f docker-compose-local.yml down -v

# View running containers
docker-compose -f docker-compose-local.yml ps

# View API logs
docker-compose -f docker-compose-local.yml logs api

# View logs for all services in real time
docker-compose -f docker-compose-local.yml logs -f

# Run a command inside the api container
docker-compose -f docker-compose-local.yml exec api bash

# Run migrations manually (auto-run on startup, use only if needed)
docker-compose -f docker-compose-local.yml exec api alembic upgrade head
```

---

## API Routes

All routes are prefixed with `/api/v1`.

| Prefix            | Description              |
|-------------------|--------------------------|
| `/auth`           | Login, token management  |
| `/tenant`         | Tenant management        |
| `/inventory`      | Inventory & batch ops    |
| `/dish`           | Dishes, combos, SFPs     |
| `/wastage`        | Wastage recording        |
| `/oders`          | Orders                   |
| `/alerts`         | Stock & expiry alerts    |
| `/reconciliation` | Inventory reconciliation |

---

