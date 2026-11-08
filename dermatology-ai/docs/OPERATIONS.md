# Operations Runbook

## Overview

This document describes operational procedures for the Derma_AI system.

## System Architecture

- **Backend**: FastAPI server with PyTorch model inference
- **Frontend**: HTML/JavaScript dashboard (dashboard.html)
- **Model**: Concept Bottleneck Model (HRNet-W18 backbone)
- **Storage**: SQLite database for case tracking and metrics

## Deployment

### Prerequisites

- Python 3.11+
- PyTorch 2.1+ (CPU)
- Dependencies: see `requirements.txt`

### Local Development

```bash
cd dermatology-ai
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server.py
```

Server starts on `http://localhost:8000`

### Production Considerations

- Use reverse proxy (nginx) for TLS termination
- Set `DATA_DIR` environment variable for database location
- Configure authentication via `ADMIN_PASSWORD_HASH` and `CSRF_SECRET`
- Monitor disk space for database and uploaded images

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `DATA_DIR` | Data directory for SQLite DB | `./data` |
| `ADMIN_PASSWORD_HASH` | bcrypt hash for admin login | Required |
| `CSRF_SECRET` | Secret for CSRF tokens | Required |
| `MODEL_PATH` | Path to model checkpoint | `models/best_model.pth` |
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | Port number | `8000` |

## Database

### Schema

- `patients` — patient records
- `cases` — case records with triage results
- `overrides` — clinician overrides
- `notes` — case notes
- `metrics` — computed fairness metrics

### Backup

```bash
# Automated backup script
python scripts/backup_db.py --data-dir $DATA_DIR --output backups/db_$(date +%F).sqlite

# Verify backup
python scripts/backup_db.py --data-dir $DATA_DIR --verify backups/db_$(date +%F).sqlite
```

### Restore

```bash
# Stop server first
python scripts/backup_db.py --data-dir $DATA_DIR --restore backups/db_$(date +%F).sqlite
```

## Monitoring

### Health Checks

- `GET /api/health` — Returns 200 if server running
- `GET /api/ready` — Returns model readiness status

### Key Metrics

- Request latency (p50, p95, p99)
- Error rate by endpoint
- Model inference time
- Database query performance
- Override rate (clinician disagreement)

### Logs

- Application logs: stdout/stderr (configure via logging config)
- Access logs: reverse proxy
- Audit logs: `overrides` and `notes` tables

## Incident Response

### Model Not Ready

1. Check `GET /api/ready` for reason
2. Verify model checkpoint exists at `MODEL_PATH`
3. Check GPU/CPU memory availability
4. Restart server if needed

### High Override Rate

1. Check analytics: `GET /api/analytics`
2. Review recent overrides in admin panel
3. Consider model retraining or threshold adjustment

### Database Issues

1. Check disk space
2. Verify SQLite integrity: `sqlite3 $DATA_DIR/derma.db "PRAGMA integrity_check;"`
3. Restore from backup if corrupted

## Security

See [SECURITY.md](SECURITY.md) for security policy.

## Maintenance

### Weekly

- Verify backups complete and restorable
- Check disk usage
- Review override trends

### Monthly

- Rotate logs
- Update dependencies (security patches)
- Review fairness metrics on new data

### Quarterly

- Full disaster recovery test
- Security audit
- Model performance review

## Contacts

- **Primary Maintainer**: jamesmutegeki
- **Repository**: https://github.com/jamesmutegeki/Derma_AI