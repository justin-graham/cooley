# Quick Start: Database Migration

## 🎯 One Command Migration

Apply the database migration to enable the time-travel cap table feature:

```bash
# Get your Render database URL from dashboard, then run:
psql "<your-render-postgres-url>" < migrations/001_add_equity_tables.sql
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
 public | audits         | table | postgres
 public | documents      | table | postgres
 public | equity_events  | table | postgres
```

## 📋 What This Migration Does

- **Creates `documents` table**: Stores individual documents with classification and full text
- **Creates `equity_events` table**: Transaction ledger for time-travel cap table
- **Adds indexes**: Optimizes queries for event_date, audit_id, and shareholder lookups
- **Backward compatible**: Existing audits continue to work unchanged

## 🔒 Safety Notes

- Migration uses `CREATE TABLE IF NOT EXISTS` (safe to run multiple times)
- Does NOT modify existing `audits` table
- Does NOT delete or migrate existing audit data
- Adds foreign key constraints with `ON DELETE CASCADE` (child records auto-delete when audit is deleted)

## 🚨 Troubleshooting

**"psql: command not found"**
- Install PostgreSQL client: `brew install postgresql` (macOS) or see [PostgreSQL downloads](https://www.postgresql.org/download/)

**"permission denied for schema public"**
- Contact Render support to verify database user permissions
- Or use Render dashboard Shell: Settings → Connect → Open Shell

**"relation already exists"**
- Migration already applied successfully (safe to ignore)
- Verify with: `psql $DATABASE_URL -c "\dt"`

---

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for full deployment instructions and testing checklist.
