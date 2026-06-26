# Climate Intelligence Platform - Deployment Guide

## Public Deployment Options

You have 3 easy options to deploy this online:

### **Option 1: Railway.app (Recommended - Easiest)**

**Cost:** Free tier (up to 500 hours/month)  
**Time:** 5 minutes  
**Link:** https://railway.app

**Steps:**

1. Go to https://railway.app and sign up with GitHub
2. Click "New Project" → "Deploy from GitHub"
3. Select this repository: `climate-platform`
4. Railway auto-detects `Procfile` and deploys automatically
5. In 2-3 minutes, you get a live URL:
   ```
   https://climate-platform-xxxx.railway.app
   ```

6. Test endpoints:
   ```bash
   curl https://climate-platform-xxxx.railway.app/health
   curl https://climate-platform-xxxx.railway.app/
   curl https://climate-platform-xxxx.railway.app/info
   ```

**Environment Variables:**
```
DATABASE_URL=postgresql+psycopg://climate_app:climate_app@localhost:5432/climate_platform
ENVIRONMENT=production
```

---

### **Option 2: Render.com (Alternative)**

**Cost:** Free tier  
**Time:** 5 minutes  
**Link:** https://render.com

**Steps:**

1. Go to https://render.com and sign up with GitHub
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Set Build Command: `pip install -r requirements.txt`
5. Set Start Command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
6. Add Environment Variables (same as above)
7. Deploy

---

### **Option 3: Fly.io (Most Reliable)**

**Cost:** Free tier (3 shared-cpu-1x 256MB VMs)  
**Time:** 10 minutes  
**Link:** https://fly.io

**Steps:**

1. Install Fly CLI: `brew install flyctl` (macOS)
2. Sign up: `flyctl auth signup`
3. Create Fly app: `flyctl launch` (in project directory)
4. When prompted, set:
   - App name: `climate-platform`
   - Choose region: `fra` (Europe for climate data)
5. Deploy: `flyctl deploy`
6. Get URL: `flyctl open` (shows your deployed app URL)

---

## Local Deployment (Already Complete)

**Your local API is running at:**
```
http://localhost:8000
```

**Endpoints:**
- `/health` - Health check
- `/` - Platform info
- `/info` - Full capabilities
- `/docs` - Interactive API documentation
- `/redoc` - Alternative docs

**Database:**
- PostgreSQL 16 (climate_platform)
- 41 tables (26 regulatory + CRCS)
- Multi-tenancy enabled

---

## Docker Deployment

To deploy as a Docker container:

```bash
# Build image
docker build -t climate-platform .

# Run container
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+psycopg://climate_app:climate_app@db:5432/climate_platform \
  climate-platform
```

---

## Production Checklist

Before deploying to production:

- [ ] Set `ENVIRONMENT=production` in environment variables
- [ ] Use strong database password (not "climate_app")
- [ ] Enable HTTPS/SSL
- [ ] Set up monitoring/alerting
- [ ] Configure backup strategy
- [ ] Add rate limiting (in `api/main.py`)
- [ ] Enable CORS restrictions (set specific origins)
- [ ] Add API key authentication (future: JWT in Phase 1)

---

## Monitoring Your Deployed App

Once deployed, you can monitor:

1. **Health Status:**
   ```bash
   curl https://your-app.railway.app/health
   ```

2. **Full API Info:**
   ```bash
   curl https://your-app.railway.app/info | jq .
   ```

3. **API Docs:**
   ```
   https://your-app.railway.app/docs
   ```

4. **Logs:**
   - Railway: Dashboard → Deployments → View Logs
   - Render: Dashboard → View Logs
   - Fly.io: `flyctl logs`

---

## What Gets Deployed

✅ FastAPI application (port 8000)  
✅ SQLAlchemy ORM models  
✅ Database configuration  
✅ All regulatory frameworks  
✅ CRCS versioning system  
✅ API documentation  

---

## Next Steps (Phase 1)

Once deployed, begin Phase 1 work:

1. Build regulatory change detection service
2. Add web scrapers (EUR-Lex, SEC, FCA, ECB)
3. Implement change analysis
4. Build customer notifications

**Target:** Complete by Weeks 2-6 for Jan 11, 2026 deadline

---

## Questions?

- Railway support: https://docs.railway.app
- Render support: https://render.com/docs
- Fly.io support: https://fly.io/docs
- FastAPI docs: https://fastapi.tiangolo.com

**You're ready to deploy!** 🚀
