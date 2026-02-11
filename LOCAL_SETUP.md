# Local Development Setup

Guide for running the Corporate Governance Audit Platform on your local machine.

## Prerequisites

- Python 3.9+ ([download](https://www.python.org/downloads/))
- PostgreSQL 14+ ([download](https://www.postgresql.org/download/))
- Anthropic API key ([get one](https://console.anthropic.com/))

## Step 1: Clone & Install

```bash
# Clone the repository
git clone <your-repo-url>
cd corporate-audit-mvp

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Set Up PostgreSQL

### Option A: Local PostgreSQL

```bash
# Create database
createdb corporate_audit

# Run schema
psql corporate_audit < schema.sql

# Verify
psql corporate_audit -c "\dt"
# Should show "audits" table
```

### Option B: Use Docker

```bash
# Start Postgres in Docker
docker run --name corporate-audit-db \
  -e POSTGRES_DB=corporate_audit \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  -d postgres:14

# Wait a few seconds for startup, then run schema
docker exec -i corporate-audit-db psql -U postgres -d corporate_audit < schema.sql
```

## Step 3: Configure Environment

```bash
# Copy example env file
cp .env.example .env.local

# Edit .env.local with your values
nano .env.local  # or use your preferred editor
```

**Required values in `.env.local`**:

```bash
# Your Claude API key
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Local database URL
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/corporate_audit

# Comma-separated origins allowed to use cookies with API
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Set LOCAL_DEV for non-secure cookies in local HTTP
LOCAL_DEV=1
```

## Step 4: Run the Application

```bash
# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
🚀 Corporate Governance Audit Platform API started
```

## Step 5: Test the Application

1. Open browser to **http://localhost:8000**

2. You should see the upload interface

3. Create a test zip file with sample documents:
   ```bash
   # Create test directory
   mkdir test-docs

   # Add some sample PDFs, DOCX, etc. to test-docs/

   # Zip it
   zip -r test-upload.zip test-docs/
   ```

4. Upload `test-upload.zip` through the web interface

5. Watch the console logs for processing progress

## Development Tips

### Hot Reload

The `--reload` flag enables auto-reload on code changes. Edit any `.py` file and the server will restart automatically.

### View Logs

All logs appear in the console where you ran `uvicorn`. Look for:
- API requests
- Processing progress
- Errors and stack traces

### Test Claude API

```python
# Test script: test_claude.py
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

message = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello, Claude!"}]
)

print(message.content[0].text)
```

```bash
python test_claude.py
```

### Debug Database

```bash
# Connect to database
psql corporate_audit

# View recent audits
SELECT id, status, company_name, created_at FROM audits ORDER BY created_at DESC LIMIT 5;

# View specific audit details
SELECT * FROM audits WHERE id = 'your-audit-id';

# Clear all audits (for testing)
TRUNCATE audits;
```

### Common Issues

#### Issue: `ModuleNotFoundError: No module named 'app'`

**Fix**: Make sure you're in the project root directory and the virtual environment is activated.

#### Issue: `psycopg2` installation fails

**Fix** (macOS):
```bash
brew install postgresql
pip install psycopg2-binary
```

**Fix** (Ubuntu/Debian):
```bash
sudo apt-get install libpq-dev
pip install psycopg2-binary
```

#### Issue: Database connection error

**Fix**: Verify Postgres is running:
```bash
# Check if Postgres is running
pg_isready

# If not running, start it:
# macOS:
brew services start postgresql
# Linux:
sudo systemctl start postgresql
```

#### Issue: `ANTHROPIC_API_KEY not set`

**Fix**:
1. Ensure `.env.local` file exists in project root
2. Verify it contains `ANTHROPIC_API_KEY=sk-ant-...`
3. Restart the uvicorn server

## Project Structure

```
corporate-audit-mvp/
├── app/
│   ├── __init__.py        # Python package marker
│   ├── main.py            # FastAPI app & routes
│   ├── db.py              # Database operations
│   ├── processing.py      # AI pipeline
│   ├── prompts.py         # Claude prompts
│   └── utils.py           # Document parsing
├── static/
│   ├── index.html         # UI
│   ├── style.css          # Swiss design styles
│   └── script.js          # Frontend logic
├── schema.sql             # Database schema
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
└── README.md              # Documentation
```

## Making Changes

### Backend Changes

1. Edit files in `app/` directory
2. Server auto-reloads (if using `--reload` flag)
3. Test changes at http://localhost:8000

### Frontend Changes

1. Edit `static/index.html`, `static/style.css`, or `static/script.js`
2. Refresh browser (no server restart needed)

### Database Schema Changes

1. Edit `schema.sql`
2. Drop and recreate database:
   ```bash
   dropdb corporate_audit
   createdb corporate_audit
   psql corporate_audit < schema.sql
   ```

## Running Tests

Create a simple test:

```python
# test_upload.py
import requests

# Upload a test file
with open('test-upload.zip', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/upload',
        files={'file': f}
    )

print(response.json())
# {'audit_id': '...', 'message': 'Processing started'}
```

## Next Steps

- Read `DEPLOYMENT.md` for deploying to production
- Explore the code to understand the AI pipeline
- Customize prompts in `app/prompts.py` for your use case
- Enhance the UI in `static/` files
