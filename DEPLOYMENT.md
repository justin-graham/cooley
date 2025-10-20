# Deployment Guide

This guide covers deploying the Corporate Governance Audit Platform to Render with Postgres.

## Prerequisites

- GitHub account
- Render account (free tier works)
- Anthropic API key ([get one here](https://console.anthropic.com/))

## Step 1: Prepare Your Code

1. **Initialize Git repository**:
   ```bash
   cd corporate-audit-mvp
   git init
   git add .
   git commit -m "Initial commit: Corporate Governance Audit Platform MVP"
   ```

2. **Push to GitHub**:
   ```bash
   # Create a new repo on GitHub, then:
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git branch -M main
   git push -u origin main
   ```

## Step 2: Set Up Render

### Create PostgreSQL Database

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"PostgreSQL"**
3. Configure:
   - **Name**: `corporate-audit-db`
   - **Database**: `corporate_audit`
   - **User**: (auto-generated)
   - **Region**: Choose closest to you
   - **Plan**: Free
4. Click **"Create Database"**
5. Wait for database to provision (~2 minutes)
6. Copy the **Internal Database URL** (starts with `postgresql://`)

### Initialize Database Schema

1. In Render dashboard, go to your database
2. Click **"Connect"** → **"External Connection"**
3. Use the provided `psql` command or connection details
4. Run the schema:
   ```bash
   # From your local machine
   psql "YOUR_EXTERNAL_DATABASE_URL" < schema.sql
   ```

### Create Web Service

1. In Render dashboard, click **"New +"** → **"Web Service"**
2. Connect your GitHub repository
3. Configure:
   - **Name**: `corporate-audit-api`
   - **Environment**: `Python 3`
   - **Region**: Same as your database
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free

4. **Environment Variables** (click "Advanced" → "Add Environment Variable"):

   | Key | Value |
   |-----|-------|
   | `ANTHROPIC_API_KEY` | Your Claude API key (sk-ant-...) |
   | `DATABASE_URL` | Your Postgres Internal Database URL |

5. Click **"Create Web Service"**

6. Wait for deployment (~5 minutes for first build)

## Step 3: Verify Deployment

1. Once deployed, Render will give you a URL: `https://corporate-audit-api.onrender.com`

2. Visit the URL in your browser

3. You should see the upload interface

4. Test with a sample .zip file containing a few PDFs

## Troubleshooting

### Build Fails

**Issue**: `ModuleNotFoundError` or dependency errors

**Fix**: Check that `requirements.txt` is committed and in the root directory

### Runtime Error: "DATABASE_URL not set"

**Issue**: Environment variable not configured

**Fix**:
1. Go to Render dashboard → Your web service → "Environment"
2. Verify `DATABASE_URL` is set to your Postgres Internal URL
3. Click "Save Changes" and wait for automatic redeploy

### Runtime Error: "ANTHROPIC_API_KEY not set"

**Issue**: Missing or invalid API key

**Fix**:
1. Get your API key from https://console.anthropic.com/
2. Add it as environment variable in Render
3. Ensure it starts with `sk-ant-`

### Upload Fails with 500 Error

**Issue**: Database connection issue

**Fix**:
1. Check Render logs: Dashboard → Web Service → "Logs"
2. Verify database is running and accessible
3. Ensure schema.sql was run successfully:
   ```bash
   psql "YOUR_DB_URL" -c "\dt"
   # Should show "audits" table
   ```

### Processing Takes Forever

**Issue**: Claude API rate limits or network issues

**Fix**:
1. Check Claude API dashboard for rate limit status
2. For large document sets (100+ files), processing can take 5-10 minutes
3. Check Render logs for specific errors

## Monitoring

### View Logs

```bash
# Real-time logs
render logs -t

# Or in dashboard:
# Dashboard → Your Web Service → "Logs" tab
```

### Check Database

```bash
# Connect to database
psql "YOUR_EXTERNAL_DB_URL"

# View audits
SELECT id, status, company_name, created_at FROM audits ORDER BY created_at DESC LIMIT 10;

# Count audits by status
SELECT status, COUNT(*) FROM audits GROUP BY status;
```

## Updating the Application

1. Make changes to your code locally
2. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Your changes"
   git push
   ```
3. Render will automatically detect the push and redeploy

## Cost Estimates

### Render (Free Tier)

- Web Service: Free (spins down after 15 min inactivity)
- PostgreSQL: Free (1GB storage, 90 day data retention)

### Anthropic Claude API

- ~$3-15 per 1M input tokens (Claude 3.5 Sonnet)
- Average audit (50 docs): ~$0.50-2.00
- 100 audits/month: ~$50-200

### Scaling to Paid Tiers

When you outgrow free tier:

- **Render Web Service** ($7/month): No spin-down, always available
- **Render PostgreSQL** ($7/month): 10GB storage, continuous backups
- **Total**: ~$14/month + Claude API usage

## Security Best Practices

1. **Never commit `.env` file** (already in `.gitignore`)

2. **Rotate API keys regularly**:
   - Generate new Claude API key
   - Update in Render environment variables
   - Delete old key from Anthropic dashboard

3. **Monitor usage**:
   - Set up alerts in Anthropic dashboard
   - Review Render logs weekly

4. **Add authentication** (for production):
   - Implement basic auth or OAuth
   - See FastAPI docs: https://fastapi.tiangolo.com/tutorial/security/

## Support

- **Render Docs**: https://render.com/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Anthropic Docs**: https://docs.anthropic.com/
- **Issues**: Open an issue on GitHub
