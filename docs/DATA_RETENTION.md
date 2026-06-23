# Data Retention & Encryption Guidance

This document describes what data accumulates during Brain Alpha Ops usage,
recommended retention policies, encryption guidance, and backup strategies.

## Data Inventory

### `data/` — Official Context & Catalogs

| Artifact | Contents | Growth Rate |
|---|---|---|
| `official_fields.json` | Field catalog from BRAIN API | Static until refreshed |
| `official_operators.json` | Operator catalog from BRAIN API | Static until refreshed |
| `official_datasets.json` | Dataset catalog from BRAIN API | Static until refreshed |
| `official_context_refresh_status.json` | Timestamp of last refresh | Single file, ~1 KB |

**Retention**: These files are regenerated on each context refresh. Old copies
are safe to delete; the next sync recreates them. Keep the latest copy at all
times. Archive before refresh if you need historical field/operator catalogs.

### `api_cache/` — HTTP Response Cache

Caches raw BRAIN API responses to avoid redundant calls. Files are keyed by
endpoint and parameters.

**Retention**: The cache is TTL-based (default 24 hours per `CloudDefaults`).
Entries older than 48 hours can be safely pruned. The cache regenerates on
next API interaction.

### `artifacts/evidence/` — Scoring & Backtest Evidence

Contains JSONL evidence files produced by scoring, backtest, and quality gate
pipelines. Files include:

- `candidates.jsonl` — generated candidate expressions
- `lifecycle.jsonl` — lifecycle status transitions per alpha
- `checks.jsonl` — quality gate check results
- `backtests.jsonl` — local backtest run records
- `submissions.jsonl` — submission audit trail
- `cloud_alphas.jsonl` — cloud-synced alpha records

**Retention**: Subject to the archive policy defined in `JournalArchiveDefaults`
(`runtime_constants.py`):

| Setting | Value | Description |
|---|---|---|
| `MAX_SIZE_MB` | 50 MB | Per-file size before archival rotation |
| `MAX_AGE_DAYS` | 30 days | Archives older than this are deleted |
| `ARCHIVE_CHECK_INTERVAL` | 3600s | How often staleness is checked |

Files are rotated to `storage/archive/` when they exceed 50 MB. Archives older
than 30 days are automatically removed.

**Recommendation**: For long-running research sessions, export critical evidence
to external storage before the 30-day cleanup window.

### `storage/` — JSONL Storage & SQLite Indexes

Contains the JSONL journals, SQLite expression/record indexes, and archived
rotations. SQLite databases are rebuilt from JSONL on demand.

**Retention**: SQLite indexes are ephemeral — they can be rebuilt from JSONL
source files. JSONL files follow the same archive policy as `artifacts/evidence/`.

### Other Runtime Artifacts

| Path | Contents | Retention |
|---|---|---|
| `.pytest_cache_runtime/` | Pytest cache | Safe to delete anytime |
| `data/official_context_refresh_status.json` | Refresh metadata | Regenerated on next refresh |
| Checkpoint files | Session resume state | Keep while session is active; archive after completion |

## Recommended Retention Policies

| Data Category | Retention Period | Action |
|---|---|---|
| Official context JSON (`data/official_*.json`) | Until next refresh | Overwrite on sync |
| API cache (`api_cache/`) | 48 hours | Prune stale entries |
| Evidence JSONL (`artifacts/evidence/`) | 30 days | Archive, then auto-delete |
| Archived rotations (`storage/archive/`) | 30 days from archival | Auto-deleted by archive policy |
| SQLite indexes | Ephemeral | Rebuild from JSONL |
| Checkpoint files | Until session done | Manual archive or delete |

## Encryption Recommendations

### At Rest

- **Research expressions and alpha candidates**: These are your intellectual
  property. If stored on shared or networked drives, use full-disk encryption
  (e.g., LUKS on Linux, FileVault on macOS, BitLocker on Windows).
- **API tokens and credentials**: Never stored by Brain Alpha Ops in plaintext.
  The system uses environment variables or secure credential stores. Verify
  your deployment does not log tokens.
- **Local JSONL files**: Contain expression text and scoring results. Treat
  these as sensitive if they contain proprietary alpha strategies.

### In Transit

- All BRAIN API communication uses HTTPS (enforced by the `requests` library).
- The local web console binds to `127.0.0.1` by default — no network exposure.
- If you expose the web console to a network (not recommended), add TLS
  termination via a reverse proxy.

### Recommendations

1. Enable full-disk encryption on the machine storing research artifacts.
2. Do not commit `data/`, `api_cache/`, or `artifacts/` to version control.
3. If sharing research results externally, redact proprietary expressions.
4. Rotate BRAIN API credentials periodically; the system does not persist them.

## Backup Strategies

### Automated (Recommended)

```bash
# Example: daily backup of research state (adjust path as needed)
BACKUP_DIR="$HOME/brain-alpha-backups/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

# Backup evidence and storage (JSONL journals, SQLite indexes)
cp -r artifacts/evidence/ "$BACKUP_DIR/evidence/"
cp -r storage/ "$BACKUP_DIR/storage/"

# Backup official context (for reproducibility)
cp -r data/ "$BACKUP_DIR/data/"

# Keep only last 14 days of backups
find "$HOME/brain-alpha-backups/" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
```

### Manual Checkpoint Export

Before major research milestones, manually export:

1. `artifacts/evidence/candidates.jsonl` — your candidate expressions
2. `artifacts/evidence/submissions.jsonl` — submission audit trail
3. `storage/expression_index.db` — expression deduplication state
4. Checkpoint files for session continuity

### What NOT to Back Up

- `.pytest_cache_runtime/` — ephemeral test cache
- `api_cache/` — regenerates automatically
- `dist/`, `build/` — build artifacts
- `node_modules/` — reinstallable
- `.git/` — use git for code, not data
