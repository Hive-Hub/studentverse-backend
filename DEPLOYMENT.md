# Deployment Guide — StudentVerse Backend

---

## 🚀 Option A: Deploy on Render (Recommended — No Server Needed)

Render is a fully managed cloud platform. It handles HTTPS, scaling, and deployments automatically with zero server management.

### What You'll Create on Render

| Service | Type | Purpose |
|---------|------|---------|
| `studentverse-web` | Web Service | Django/Daphne ASGI app |
| `studentverse-worker` | Background Worker | Celery worker |
| `studentverse-beat` | Background Worker | Celery Beat scheduler |
| `studentverse-db` | PostgreSQL | Primary database |
| `studentverse-redis` | Redis | Cache + Celery broker |

---

### Step 1 — Create a PostgreSQL Database

1. Go to [render.com](https://render.com) → **New** → **PostgreSQL**
2. Fill in:
   - **Name**: `studentverse-db`
   - **Region**: Pick the closest to your users
   - **Plan**: Free (or Starter for production)
3. Click **Create Database**
4. Once created, copy the **Internal Database URL** — it looks like:
   ```
   postgresql://user:password@dpg-xxxxxx-a/studentverse
   ```

---

### Step 2 — Create a Redis Instance

1. Go to [render.com](https://render.com) → **New** → **Redis**
2. Fill in:
   - **Name**: `studentverse-redis`
   - **Plan**: Free (or Starter for production)
3. Click **Create Redis**
4. Once created, copy the **Internal Redis URL** — it looks like:
   ```
   redis://red-xxxxxx:6379
   ```

---

### Step 3 — Create the Web Service

1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your **GitHub repository**
3. Fill in the settings:

| Setting | Value |
|---------|-------|
| **Name** | `studentverse-web` |
| **Region** | Same as DB |
| **Branch** | `main` |
| **Root Directory** | *(leave blank)* |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `cd src && daphne -b 0.0.0.0 -p $PORT config.asgi:application` |
| **Plan** | Starter or higher (free plan doesn't support WebSockets) |

4. Click **Advanced** → **Add Environment Variables** and add all variables from the table below.
5. Click **Create Web Service**

---

### Step 4 — Create the Celery Worker

1. Go to [render.com](https://render.com) → **New** → **Background Worker**
2. Connect the **same GitHub repository**
3. Fill in:

| Setting | Value |
|---------|-------|
| **Name** | `studentverse-worker` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `cd src && celery -A config worker -l info --concurrency 2` |

4. Add the **same environment variables** as the web service.
5. Click **Create Background Worker**

---

### Step 5 — Create the Celery Beat Scheduler

1. **New** → **Background Worker**
2. Fill in:

| Setting | Value |
|---------|-------|
| **Name** | `studentverse-beat` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `cd src && celery -A config beat -l info` |

3. Add the **same environment variables**.
4. Click **Create Background Worker**

---

### Step 6 — Set Environment Variables

In **each** Render service (web, worker, beat), go to **Environment** tab and add:

#### 🔴 Required Variables

| Variable | Value | Where to Get It |
|----------|-------|-----------------|
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` | Fixed value |
| `DJANGO_SECRET_KEY` | `your-random-secret-key` | Generate below ↓ |
| `DJANGO_DEBUG` | `false` | Fixed value |
| `DJANGO_ALLOWED_HOSTS` | `your-app.onrender.com` | Your Render URL |
| `DATABASE_URL` | `postgresql://...` | Render PostgreSQL → Internal URL |
| `REDIS_URL` | `redis://red-...` | Render Redis → Internal URL |
| `CELERY_BROKER_URL` | Same as `REDIS_URL` | Same as above |
| `CELERY_RESULT_BACKEND` | Same as `REDIS_URL` | Same as above |
| `CORS_ALLOWED_ORIGINS` | `https://your-frontend.com` | Your frontend URL |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app.onrender.com` | Your Render URL |
| `DJANGO_ENVIRONMENT` | `production` | Fixed value |

#### 🟡 Supabase Storage (Required for file uploads)

| Variable | Value | Where to Get It |
|----------|-------|-----------------|
| `SUPABASE_URL` | `https://xxxx.supabase.co` | Supabase Dashboard → Settings → API |
| `SUPABASE_KEY` | `your-anon-key` | Supabase Dashboard → Settings → API → anon key |
| `SUPABASE_STORAGE_BUCKET` | `studentverse-media` | Supabase Dashboard → Storage |

#### 🟡 Firebase Auth (Required for login)

| Variable | Value | Where to Get It |
|----------|-------|-----------------|
| `FIREBASE_CREDENTIALS_PATH` | `/etc/secrets/firebase.json` | See note below |

> **Firebase credentials note**: Render supports **Secret Files**. Upload your `firebase-adminsdk.json` as a secret file at path `/etc/secrets/firebase.json`. Go to your service → **Environment** → **Secret Files** → Add file.

#### 🟢 Email (Optional — for notification emails)

| Variable | Value | Notes |
|----------|-------|-------|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | |
| `EMAIL_HOST` | `smtp.sendgrid.net` | Or any SMTP provider |
| `EMAIL_PORT` | `587` | |
| `EMAIL_USE_TLS` | `true` | |
| `EMAIL_HOST_USER` | `apikey` | For SendGrid |
| `EMAIL_HOST_PASSWORD` | `SG.xxxx...` | SendGrid API key |
| `DEFAULT_FROM_EMAIL` | `noreply@yourdomain.com` | |

#### 🟢 Sentry (Optional — for error monitoring)

| Variable | Value |
|----------|-------|
| `SENTRY_DSN` | `https://xxx@oxx.ingest.sentry.io/xxx` |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` |

#### 🟢 Security (Defaults are safe — adjust if needed)

| Variable | Default | Notes |
|----------|---------|-------|
| `DJANGO_SECURE_SSL_REDIRECT` | `true` | Render handles HTTPS already, set to `false` if you see redirect loops |
| `DJANGO_SECURE_HSTS_SECONDS` | `31536000` | |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `60` | |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `7` | |

---

### Generating a Secret Key

Run this in your terminal to generate a strong `DJANGO_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(50))"
```

Copy the output and paste it as the value for `DJANGO_SECRET_KEY`.

---

### Step 7 — Add Build/Release Commands

In the Render Web Service settings, under **Build & Deploy**:

- **Build Command**:
  ```bash
  pip install -r requirements.txt && cd src && python manage.py collectstatic --noinput
  ```

- **Pre-Deploy Command** (runs migrations before each deploy):
  ```bash
  cd src && python manage.py migrate --noinput
  ```

---

### Step 8 — Verify Deployment

Once deployed, test these URLs (replace `your-app` with your Render service name):

```bash
# Health check
curl https://your-app.onrender.com/health/

# Public API (no auth needed)
curl https://your-app.onrender.com/api/v1/public/stats/
```

Expected response:
```json
{
  "success": true,
  "message": "Platform statistics retrieved.",
  "data": { "users": 0, "communities": 0, ... }
}
```

---

### Step 9 — Set Up Auto-Deploy

Render auto-deploys from `main` branch by default. Every `git push origin main` will:
1. Install requirements
2. Collect static files
3. Run migrations (pre-deploy)
4. Restart all services

To disable auto-deploy: Service → **Settings** → **Auto-Deploy** → Off

---

### Render Environment Variables — Quick Reference Card

> Copy this table and fill in your values before creating services.

```
DJANGO_SETTINGS_MODULE    = config.settings.production
DJANGO_SECRET_KEY         = <generate with python -c "import secrets; print(secrets.token_hex(50))">
DJANGO_DEBUG              = false
DJANGO_ENVIRONMENT        = production
DJANGO_ALLOWED_HOSTS      = your-app.onrender.com
DATABASE_URL              = <from Render PostgreSQL Internal URL>
REDIS_URL                 = <from Render Redis Internal URL>
CELERY_BROKER_URL         = <same as REDIS_URL>
CELERY_RESULT_BACKEND     = <same as REDIS_URL>
CORS_ALLOWED_ORIGINS      = https://your-frontend.vercel.app
CSRF_TRUSTED_ORIGINS      = https://your-app.onrender.com
SUPABASE_URL              = https://xxxx.supabase.co
SUPABASE_KEY              = <supabase anon key>
SUPABASE_STORAGE_BUCKET   = studentverse-media
FIREBASE_CREDENTIALS_PATH = /etc/secrets/firebase.json
DJANGO_SECURE_SSL_REDIRECT = false
```

> ⚠️ Set `DJANGO_SECURE_SSL_REDIRECT=false` on Render — Render's load balancer already handles HTTPS termination, so Django should not do an additional redirect.

---

## 🐳 Option B: Deploy on Your Own Server (Docker)


## Prerequisites

On your production server:
- Docker 25+
- Docker Compose v2
- Git
- Domain name with DNS A record pointing to the server

---

## 1. Clone and Configure

```bash
git clone https://github.com/your-org/studentverse-backend.git /opt/studentverse
cd /opt/studentverse

cp .env.example .env
nano .env  # Fill in all production values
```

**Critical `.env` values for production:**
```dotenv
DJANGO_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(50))">
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://svuser:svpassword@db:5432/studentverse
REDIS_URL=redis://redis:6379/0
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
CORS_ALLOWED_ORIGINS=https://yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com
DOMAIN=yourdomain.com
```

---

## 2. Obtain SSL Certificate (Let's Encrypt)

Before starting Nginx with HTTPS, get a certificate:

```bash
# Start Nginx on HTTP only first (comment out the HTTPS server block temporarily)
docker compose up -d nginx

# Obtain certificate
docker run --rm \
  -v /opt/studentverse/nginx/certbot/www:/var/www/certbot \
  -v /opt/studentverse/nginx/certbot/conf:/etc/letsencrypt \
  certbot/certbot certonly \
  --webroot --webroot-path=/var/www/certbot \
  --email admin@yourdomain.com \
  --agree-tos --no-eff-email \
  -d yourdomain.com -d www.yourdomain.com

# Re-enable HTTPS in nginx.conf, then restart
docker compose restart nginx
```

---

## 3. Deploy All Services

```bash
cd /opt/studentverse

# Build images and start all services in the background
docker compose build
docker compose up -d

# Verify all services are healthy
docker compose ps
```

Expected output:
```
NAME             STATUS
studentverse-db          healthy
studentverse-redis       healthy
studentverse-web         running
studentverse-celery      running
studentverse-celerybeat  running
studentverse-nginx       running
```

---

## 4. Post-Deploy Setup

```bash
# Create Django superuser
docker compose exec web python manage.py createsuperuser

# Verify health endpoint
curl https://yourdomain.com/health/
# Expected: {"status": "ok", "version": "1.0.0"}

# Verify dashboard API
curl -H "Authorization: Bearer <ADMIN_TOKEN>" \
     https://yourdomain.com/api/v1/dashboard/health/
```

---

## 5. Database Backups

### Manual Backup

```bash
# Create backup
docker compose exec db pg_dump -U svuser studentverse > backup_$(date +%Y%m%d_%H%M%S).sql

# Compress
gzip backup_*.sql
```

### Automated Backup (Cron)

Add to `/etc/cron.d/studentverse-backup`:
```cron
0 3 * * * root cd /opt/studentverse && \
  docker compose exec -T db pg_dump -U svuser studentverse | \
  gzip > /backups/db_$(date +\%Y\%m\%d).sql.gz && \
  find /backups -name "*.sql.gz" -mtime +30 -delete
```

---

## 6. Celery Worker Management

```bash
# Check worker status
docker compose exec celery celery -A config inspect active

# Monitor task queue
docker compose exec celery celery -A config flower  # Install flower first

# Restart workers after code update
docker compose restart celery celerybeat
```

---

## 7. Updating the Application

```bash
cd /opt/studentverse

# Pull latest code
git pull origin main

# Rebuild and redeploy
docker compose build web celery celerybeat
docker compose up -d --remove-orphans

# Apply new migrations
docker compose exec web python manage.py migrate --noinput

# Collect updated static files
docker compose exec web python manage.py collectstatic --noinput
```

---

## 8. Monitoring

### Health Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health/` | None | Basic app health |
| `GET /api/v1/dashboard/health/` | Admin | DB + Redis status |
| `GET /api/v1/dashboard/api-usage/` | Admin | API call analytics |
| `GET /api/v1/dashboard/audit-logs/` | Admin/Mod | Request logs |

### Log Files (inside container)

```bash
# Application logs
docker compose exec web tail -f /app/logs/django.log

# Nginx access log
docker compose exec nginx tail -f /var/log/nginx/access.log

# Celery task logs
docker compose logs -f celery
```

### Sentry

Set `SENTRY_DSN` in `.env` to automatically send errors and performance traces to [sentry.io](https://sentry.io).

---

## 9. Redis Certificate Renewal

Add this to cron to auto-renew SSL every 60 days:
```cron
0 12 */60 * * root docker run --rm \
  -v /opt/studentverse/nginx/certbot/www:/var/www/certbot \
  -v /opt/studentverse/nginx/certbot/conf:/etc/letsencrypt \
  certbot/certbot renew --quiet && \
  docker compose exec nginx nginx -s reload
```

---

## 10. Environment Separation

| Setting | Development | Production |
|---------|-------------|------------|
| `DJANGO_DEBUG` | `true` | `false` |
| `DATABASE` | SQLite | PostgreSQL |
| `CACHE` | Dummy | Redis |
| `EMAIL_BACKEND` | Console | SMTP |
| `SSL_REDIRECT` | Disabled | Enabled |
| `HSTS` | Disabled | 1 year |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `502 Bad Gateway` | Check `docker compose logs web` — Daphne may have crashed |
| DB connection refused | Check `docker compose ps db` — wait for `healthy` status |
| Static files 404 | Run `python manage.py collectstatic` inside the web container |
| Celery tasks not running | Check `docker compose logs celery celerybeat` |
| Redis connection error | Verify `REDIS_URL` in `.env` matches the service name |
