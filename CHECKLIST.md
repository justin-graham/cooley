# Pre-Deployment Checklist

Use this checklist before deploying to production.

## Code Quality

- [ ] All files are committed to Git
- [ ] `.env` is in `.gitignore` (never commit secrets!)
- [ ] No hardcoded API keys or passwords in code
- [ ] All TODO comments resolved or documented
- [ ] Code follows consistent style (PEP 8 for Python)

## Configuration

- [ ] `.env.example` contains all required variables
- [ ] `requirements.txt` includes all dependencies
- [ ] `schema.sql` is complete and tested
- [ ] README.md is up to date

## Testing

- [ ] Successfully uploaded and processed a test .zip locally
- [ ] All 6 core features work:
  - [ ] Document classification (by category)
  - [ ] Timeline generation (chronological events)
  - [ ] Cap table generation (shareholders & ownership)
  - [ ] Issue tracker (missing/inconsistent docs)
  - [ ] Company name extraction
  - [ ] Organized document display
- [ ] Error handling works (tried invalid file types, oversized files)
- [ ] Progress updates display correctly during processing
- [ ] Results render properly in UI
- [ ] Failed documents are flagged appropriately
- [ ] Database records are created and updated correctly

## API Integration

- [ ] Claude API key is valid and has credits
- [ ] Tested API calls work locally
- [ ] Error handling for API failures (rate limits, timeouts)
- [ ] API responses are parsed correctly

## Database

- [ ] Schema.sql runs without errors
- [ ] All required columns are present
- [ ] Indexes are created
- [ ] JSONB columns handle complex data correctly

## UI/UX

- [ ] Swiss design aesthetic is consistent
- [ ] Red accent color (#D42B1E) is used appropriately
- [ ] Space Grotesk font loads for headings
- [ ] Space Mono font loads for data/code
- [ ] Layout is responsive on mobile
- [ ] Upload zone provides clear feedback
- [ ] Progress updates are visible and helpful
- [ ] Results are clearly organized and readable

## Security

- [ ] No sensitive data logged to console
- [ ] File upload size limits enforced (50MB)
- [ ] File type validation (only .zip accepted)
- [ ] Database connection uses environment variables
- [ ] CORS is configured appropriately
- [ ] CSRF protection enabled on cookie-authenticated POST endpoints
- [ ] Session storage is durable (DB/Redis), not in-memory
- [ ] Auth/upload routes are rate-limited

## Documentation

- [ ] README.md explains what the platform does
- [ ] LOCAL_SETUP.md has clear setup instructions
- [ ] DEPLOYMENT.md covers production deployment
- [ ] Code comments explain complex logic
- [ ] All functions have docstrings

## Pre-Production

- [ ] Tested with realistic document sets (50-100 files)
- [ ] Processing time is acceptable (<5 minutes for 50 docs)
- [ ] Memory usage is reasonable
- [ ] No memory leaks (temp files cleaned up)
- [ ] Error messages are user-friendly

## Deployment Ready

- [ ] GitHub repository is public or accessible to Render
- [ ] Anthropic API key is ready
- [ ] Render account is set up
- [ ] Database will be created on Render
- [ ] Environment variables documented

## Post-Deployment Verification

After deploying to Render:

- [ ] Website loads at the Render URL
- [ ] Upload interface is visible
- [ ] Can upload a test .zip file
- [ ] Processing completes successfully
- [ ] Results display correctly
- [ ] Database contains the audit record
- [ ] Logs show no errors

## Known Limitations (MVP)

Document these for users:

- [ ] Max upload size: 50MB
- [ ] Supported file types: PDF, DOCX, XLSX, PPTX
- [ ] Processing time: 1-5 minutes for 50 docs
- [ ] Authentication exists but has not been load-tested for multi-instance deployment
- [ ] No data persistence beyond database
- [ ] Parsing throughput tuned for correctness over throughput

## Future Enhancements

Ideas for v2:

- [ ] SSO / enterprise identity providers
- [ ] Save/export results (PDF, Excel)
- [ ] Re-run analysis on existing audits
- [ ] Support for additional file types
- [ ] Batch processing multiple zips
- [ ] Email notifications when complete
- [ ] Advanced filtering and search in results
- [ ] API endpoints for programmatic access
- [ ] Webhook integrations
- [ ] Custom prompt templates per user

---

## Sign-Off

**Developer**: ___________________  **Date**: ___________

**Tested By**: ___________________  **Date**: ___________

**Deployed By**: __________________  **Date**: ___________

**Production URL**: _________________________________________
