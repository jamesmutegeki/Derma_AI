# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x (current) | Yes |

## Reporting a Vulnerability

Please report security vulnerabilities by opening a private GitHub security advisory or emailing the maintainer at the address in the repository metadata.

Do NOT open public issues for security vulnerabilities.

## Security Measures

### Authentication & Authorization

- Admin authentication via bcrypt-hashed password
- CSRF protection on all state-changing endpoints
- Session-based authentication with HttpOnly cookies
- Role-based access (admin vs clinician)

### Input Validation

- File upload: 10 MB size limit, magic bytes verification, PIL decompression bomb protection
- All API inputs validated via Pydantic models
- SQL injection prevention via parameterized queries (SQLAlchemy/asyncpg)

### Data Protection

- No PHI stored in logs
- Database encryption at rest (via filesystem/volume encryption)
- TLS in production (reverse proxy)
- Secure cookie flags (HttpOnly, Secure, SameSite)

### Dependencies

- Regular dependency updates via `pip-audit` / `safety`
- Pinned versions in `requirements.txt`
- No known vulnerable dependencies at release

### Model Security

- Model checkpoint integrity verification (SHA256 in manifest)
- No model deserialization from untrusted sources
- Input sanitization before inference

### Operational Security

- No hardcoded secrets (use environment variables)
- `.env` files gitignored
- Admin password hash generated at deployment time
- CSRF secret generated at deployment time

## Known Limitations

- **Development Mode**: Server runs without authentication when `ADMIN_PASSWORD_HASH` not set (for local testing only)
- **Model Checkpoint**: No signed/verified checkpoint in placeholder status
- **Rate Limiting**: Basic rate limiting via slowapi; tune for production

## Compliance

- **HIPAA**: Not validated for PHI handling; do not use with real patient data without compliance review
- **GDPR**: Data subject rights implementation pending
- **FDA**: Not a medical device; not cleared/approved

## Incident Response

1. Contain: Disable affected endpoints, rotate secrets
2. Assess: Determine scope and impact
3. Remediate: Patch vulnerability, redeploy
4. Verify: Test fix, monitor for regression
5. Document: Record in security log, notify stakeholders if required