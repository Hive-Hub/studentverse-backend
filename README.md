# StudentVerse Backend

A production-ready REST API and real-time backend for the **StudentVerse** platform — a community-driven social network for students to connect, share knowledge, discover events, and collaborate.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Nginx (TLS, Rate Limiting)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  Daphne ASGI (Django 5) │  ← HTTP + WebSocket
              └────────────┬────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   PostgreSQL 16        Redis 7          Supabase Storage
   (Primary DB)     (Cache/Channels/    (Media Files)
                     Celery Broker)
                           │
                    ┌──────▼──────┐
                    │  Celery     │ ← Background Jobs
                    │  Workers    │
                    └─────────────┘
```

**Tech Stack:**
- **Framework**: Django 5.2 + Django REST Framework
- **Real-time**: Django Channels + Redis (WebSockets)
- **Auth**: Firebase Auth + JWT (SimpleJWT)
- **Storage**: Supabase Storage (S3-compatible)
- **Async Jobs**: Celery + Redis + Celery Beat
- **Web Server**: Daphne (ASGI) + Nginx + Gunicorn
- **Database**: PostgreSQL 16 (SQLite for local dev)
- **Monitoring**: Sentry + Rotating file logs

---

## Features (15 Phases)

| Phase | Feature |
|-------|---------|
| 1 | Auth (Firebase + JWT) |
| 2 | User Profiles |
| 3 | Communities & Channels |
| 4 | News Feed |
| 5 | Events |
| 6 | Messaging |
| 7 | Notifications |
| 8 | Notification Center |
| 9 | Global Search |
| 10 | Supabase Storage Integration |
| 11 | Django Channels (Real-time WebSockets) |
| 12 | Moderation |
| 13 | Platform Dashboard |
| 14 | Public APIs (Landing Page, SEO, OG) |
| 15 | Production Readiness (Docker, Celery, CI/CD) |

---

## Local Development Setup

### Prerequisites
- Python 3.12+
- PostgreSQL 16 (or use SQLite for quick start)
- Redis 7

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/your-org/studentverse-backend.git
cd studentverse-backend

# 2. Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your local values

# 5. Apply migrations
cd src
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser

# 7. Run development server
python manage.py runserver
```

The API is available at `http://localhost:8000/`.

---

## Environment Variables

See [.env.example](.env.example) for the full list of required and optional environment variables.

**Required for production:**
- `DJANGO_SECRET_KEY` — Django secret key
- `DATABASE_URL` or `POSTGRES_*` vars — Database connection
- `REDIS_URL` — Redis connection string
- `DJANGO_ALLOWED_HOSTS` — Comma-separated list of allowed hosts
- `SUPABASE_URL` + `SUPABASE_KEY` — Supabase storage credentials
- `FIREBASE_CREDENTIALS_PATH` — Path to Firebase service account JSON

---

## Running Tests

```bash
cd src
python manage.py test              # Run all tests
python manage.py test apps.public  # Run specific app tests
```

All 88+ tests run in approximately 4 minutes.

---

## API Reference

See [api.txt](api.txt) for the full API documentation (15 phases, all endpoints).

**Base URL:** `/api/v1/`

**Authentication:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`

**Key Endpoint Groups:**
- `/api/v1/auth/` — Authentication
- `/api/v1/communities/` — Communities & Channels
- `/api/v1/news/` — News Feed
- `/api/v1/events/` — Events
- `/api/v1/notifications/` — Notifications
- `/api/v1/search/` — Global Search
- `/api/v1/moderation/` — Moderation
- `/api/v1/dashboard/` — Admin Dashboard
- `/api/v1/public/` — Public (no auth) APIs
- `ws://<host>/ws/channels/<id>/` — Real-time Chat

---

## Docker Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the complete step-by-step guide.

**Quick start:**
```bash
cp .env.example .env
# Edit .env with production values
docker compose up -d
```

---

## Project Structure

```
studentverse-backend/
├── src/
│   ├── apps/
│   │   ├── accounts/      # Auth, User Profiles, Storage
│   │   ├── communities/   # Communities, Channels, Members
│   │   ├── events/        # Events, RSVPs
│   │   ├── messaging/     # Messages, Reactions, Pins
│   │   ├── moderation/    # Reports, Bans, Mutes, Content Filters
│   │   ├── news/          # News Articles, Comments, Reactions
│   │   ├── notifications/ # Push Notifications, Preferences
│   │   ├── search/        # Global Search, History, Suggestions
│   │   ├── dashboard/     # Admin Dashboard, Announcements, Settings
│   │   ├── public/        # Public APIs (no auth)
│   │   ├── common/        # Shared utilities, tasks, auth helpers
│   │   ├── logs/          # Request logging
│   │   └── health/        # Health check endpoint
│   └── config/
│       ├── settings/
│       │   ├── base.py
│       │   ├── development.py
│       │   └── production.py
│       ├── celery.py      # Celery app
│       ├── asgi.py        # ASGI entrypoint
│       └── urls.py        # Root URL configuration
├── nginx/                 # Nginx configuration
├── .github/workflows/     # CI/CD pipelines
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── requirements.txt
└── api.txt                # Full API documentation
```

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for new features
4. Run `python manage.py test` and ensure all tests pass
5. Submit a pull request to `develop`
