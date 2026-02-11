# Quick Start: Database Migration

## 🎯 One Command Migration

Apply the full migration set (schema hardening + auth + cap table):

```bash
# Get your Render database URL from dashboard, then run:
psql "<your-render-postgres-url>" < migrations/001_add_equity_tables.sql
psql "<your-render-postgres-url>" < migrations/002_auth_tables.sql
psql "<your-render-postgres-url>" < migrations/003_production_hardening.sql
```

## ✅ Verify Migration

Check that the new tables were created:

```bash
psql "<your-render-postgres-url>" -c "\dt"
```

**Expected output:**
```
              List of relations
 Schema |      Name      | Type  |   Owner
--------+----------------+-------+----------
 public | access_requests | table | postgres
 public | audits          | table | postgres
 public | documents       | table | postgres
 public | equity_events   | table | postgres
 public | sessions        | table | postgres
 public | users           | table | postgres
```

## 📋 What This Migration Does

- **Creates/updates `documents` table**: Adds parse status/error fields required by parser pipeline
- **Creates/updates `equity_events` table**: Adds preview and summary fields used by API/UI
- **Adds auth/session tables**: Durable cookie sessions with CSRF token storage
- **Extends `audits` table**: Explicit pipeline states + quality/review gating fields
- **Adds indexes**: Optimizes queries for event_date, audit_id, session expiration, and review queues

## 🔒 Safety Notes

- Migrations use additive `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` semantics
- Existing data is preserved; no destructive migration steps are included
- Foreign keys use `ON DELETE CASCADE` where appropriate to avoid orphaned records

## 🚨 Troubleshooting

**"psql: command not found"**
- Install PostgreSQL client: `brew install postgresql` (macOS) or see [PostgreSQL downloads](https://www.postgresql.org/download/)

**"permission denied for schema public"**
- Contact Render support to verify database user permissions
- Or use Render dashboard Shell: Settings → Connect → Open Shell

**"relation already exists" / "column already exists"**
- Migration already applied successfully (safe to ignore)
- Verify with: `psql $DATABASE_URL -c "\dt"` and `psql $DATABASE_URL -c "\d audits"`

---

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for full deployment instructions and testing checklist.
