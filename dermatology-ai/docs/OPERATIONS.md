# Operations runbook

Whoever is on call for the Derma-AI prototype follows this document. It assumes
the deployment described by `render.yaml` (single web service, persistent disk at
`/var/data`, SQLite).

**This system is a research prototype: not a medical device, no clinical
validation, no BAA.** If it is ever used with real patient data, section 6 must be
signed off first.

---

## 1. Daily checks

| Check | Command / endpoint | Healthy answer |
| --- | --- | --- |
| Process alive | `GET /api/health` | `200 {"status":"ok"}` -- liveness only, never touches the model |
| Model loaded | `GET /api/ready` | `model_ready: true` **or** a `reason` you understand |
| Counts and disk | `GET /api/admin/ops/summary` (admin token) | `db_bytes` growing slowly, `audit_rows` growing, `active_sessions` plausible |
| Backup exists | `ls -l $DATA_DIR/backups` | newest snapshot < 24 h old, sidecar present |
| Restore is proven | `python scripts/backup_db.py --verify` | `verify: ok` |

A 503 from `/api/ready` is **not** an outage: it is the honest answer when
`MODEL_CHECKPOINT_PATH` is unset. `/api/diagnose` returning 503 is the same fact.

## 2. Backup and restore

```bash
python scripts/backup_db.py --verify          # snapshot + prove it restores
python scripts/backup_db.py --keep 30         # daily job: keep 30 days
python scripts/backup_db.py --restore "$DATA_DIR/backups/derma-YYYYmmddTHHMMSSZ.db.gz" --target /tmp/restored
```

* Snapshots use SQLite's online backup API (safe while the server is running).
* Each snapshot is `0600` inside a `0700` directory, with a `.sha256` sidecar.
* **Encryption at rest is not built in.** Point `--output-dir` at an encrypted
  volume, or encrypt before shipping off-box.
* Copy snapshots off the machine. A snapshot on the same disk is not a backup.
* Restore drill quarterly; record the date and result in the incident log.

## 3. Retention

Policy and table: `SECURITY.md` §4. The only sanctioned deletion tool:

```bash
python scripts/purge_records.py                 # dry run: counts only
python scripts/purge_records.py --apply         # enforce
```

Defaults: patients older than 1825 days (5 years), audit rows older than 730
days. User accounts are never purged -- deactivate them so audit actors stay
resolvable. Every purge writes its own audit entry.

## 4. Monitoring and alerting

`X-Request-ID` is returned on every response and appears in every access log
line; ask a user for it when they report a problem. Log lines look like:

```
2026-10-30T10:12:33 | INFO | server | request id=9f2c... method=POST path=/api/diagnose status=503 duration_ms=41.7
```

Credentials are redacted by `logging_setup.RedactionFilter`. Alert on:

1. `/api/health` failing twice in a row (process down);
2. `/api/ready` flipping to `model_ready: false` after having been true (weights
   disappeared or the manifest changed);
3. a burst of `status=403` on `/api/admin/*` (privilege probing);
4. `429` rate on `/api/login` above normal (credential stuffing) -- check
   `GET /api/admin/activity` for `login_failed` rows;
5. `db_bytes` more than doubling in a day (runaway ingestion or a loop).

## 5. Security incidents

**Do not delete evidence.** Preserve the database and log output.

1. **Contain.** Revoke the affected account: `POST /api/admin/doctors/{id}` with
   `active: false` (kills all its sessions) or `POST /api/admin/sessions/{sid}/revoke`.
   For an admin compromise, rotate `ADMIN_BOOTSTRAP_PASSWORD`, restart the service
   so every in-memory session dies, then change the password from the UI.
2. **Assess.** `GET /api/admin/activity` and `GET /api/admin/ops/summary` give the
   timeline and blast radius. The audit log records actor, action, target,
   outcome.
3. **Notify.** Inform the project lead the same day. If patient data was involved,
   the IRB and the data controller decide on participant notification -- do not
   decide that alone.
4. **Recover.** Restore the last verified snapshot if integrity is in doubt
   (§2), then re-run `--verify`.
5. **Learn.** Write a short post-incident note: what happened, what detected it,
   what closed it, what changed.

Contact: the repository maintainer (see `CITATION.cff`). There is no 24/7 rota;
this is a research prototype.

## 6. Go-live checklist (before any real patient data)

All items must be **checked and dated** in the table below. Anything unchecked
means: synthetic or fully de-identified data only.

| # | Item | Evidence | Owner | Date |
| --- | --- | --- | --- | --- |
| 1 | **S1-1** frozen model manifest + model card, no placeholder | `model_manifest.json` `status: frozen`; `MODEL_CARD.md` | ML lead | |
| 2 | **S2-4** this runbook reviewed, incident path agreed | this document, signed | Eng lead | |
| 3 | **Retention and backup policy** approved | `SECURITY.md` §4, no longer marked "draft" | Data controller | |
| 4 | **IRB / ethics approval** for the cohort, including data-sharing | approval letter on file | PI | |
| 5 | Encryption at rest + tested restore | §2 drill recorded | Ops | |
| 6 | Penetration test of the API | report, findings closed | Security | |
| 7 | `python -m pytest` green on the deployed commit | CI run link | Eng | |
| 8 | `bash scripts/ci_grep.sh` clean | CI run link | Eng | |
| 9 | Named incident contact and escalation path | §5 | Eng lead | |
| 10 | Model limitations communicated to users | `MODEL_CARD.md` + in-app disclaimer | PI | |

## 7. Rollback

The service is stateless apart from `$DATA_DIR`, so a rollback is a code
rollback plus (only if the schema changed) a database restore:

1. Redeploy the previous commit (`git revert` or Render's rollback).
2. If the release changed the schema, restore the snapshot taken *before* the
   deploy and re-run `--verify`.
3. Confirm `/api/health`, `/api/ready` and one authenticated read.
4. Note the rollback in the incident log.

## 8. Routine maintenance

| Cadence | Task |
| --- | --- |
| Daily | §1 checks; backup with `--verify` |
| Weekly | Review `/api/admin/activity` for denied actions; check disk headroom |
| Monthly | `purge_records.py` dry run, then apply; rotate backups off-box |
| Quarterly | Restore drill; dependency upgrades; re-run the go-live checklist |
| Annually | Re-read `SECURITY.md` and `MODEL_CARD.md`; re-approve retention |
