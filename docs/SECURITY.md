# Security Model — BRAIN Alpha Ops

> Single-user local workstation. **Never auto-submits** alphas — all submissions
> require explicit human approval.

## Credential Management

Credentials are resolved at runtime via environment variables. **No credentials are
stored on disk, in logs, or in screenshots.**

### Resolution order

1. Explicit function arguments (for programmatic use only)
2. Environment variables (production default)
3. Empty string (no credentials)

### Required environment variables

| Variable | Purpose |
|---|---|
| `BRAIN_USERNAME` | BRAIN account username |
| `BRAIN_PASSWORD` | BRAIN account password |
| `BRAIN_TOKEN` | Alternative: bearer token (mutually exclusive with user/pass) |

### Credential bundle

`brain_alpha_ops/secure_credentials.py` defines `CredentialBundle` — a runtime-only
dataclass that:
- Holds resolved credentials in memory only
- Masks `__repr__` output (`us***`)
- Logs only boolean presence flags, never raw values
- Records a `ResolutionTrace` audit trail for each credential source

### Web session credential storage

Credentials entered via the web UI are stored **in-memory only** inside the server-side
session row (`BRAIN_CREDENTIALS_KEY`). They are:
- Never returned to the browser as part of metadata
- Removed when the session expires or is explicitly cleared
- Not persisted to disk

For production deployments, consider integrating with the system keychain (macOS
Keychain, `keyring`) instead of in-memory storage.

## Submit Guard — `REAL_SUBMIT_DISABLED_WEB_FLOW`

The web console has a **hard kill-switch** that prevents real alpha submissions:

```python
# brain_alpha_ops/runtime_constants.py
REAL_SUBMIT_DISABLED_WEB_FLOW: Final[bool] = True
```

- Annotated as `Final[bool]` — type checkers flag any reassignment.
- Runtime sentinel `_SUBMIT_GUARD_SENTINEL` detects tampering at the API layer.
- The guard is enforced at every web submission endpoint and at
  `brain_api/official_simulation.py`.

### Test override

Tests can bypass the guard only when **all three** conditions are met:

| Environment variable | Required value |
|---|---|
| `BRAIN_ALPHA_FORCE_REAL_SUBMIT` | `1` |
| `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS` | `1` |
| `PYTEST_CURRENT_TEST` | set (pytest auto-sets this) |

This triple-gate prevents accidental or unauthorized real submissions.

## CSRF and Session Protection

### Session management

- Cookie name: `brain_alpha_ops_session`
- Cookie flags: `HttpOnly`, `SameSite=Strict`
- TTL: 12 hours (default), absolute maximum 24 hours
- Session IDs and CSRF tokens generated via `secrets.token_urlsafe(32)` (192-bit entropy)

### CSRF validation

Every mutating request (`POST`, `PUT`, `DELETE`) requires:
1. A valid session cookie
2. An `X-CSRF-Token` (or `X-Brain-Alpha-CSRF`) header matching the session's CSRF token

CSRF tokens are validated using `secrets.compare_digest()` (constant-time comparison).

### Request replay protection

Each request carries a unique `request_id` and `request_timestamp`. The server rejects
duplicate request IDs within a 5-minute TTL window. A hard cap of 10,000 entries per
session prevents memory exhaustion from replay cache DoS.

### Origin/Referer validation

`is_allowed_local_request()` verifies that `Origin`, `Referer`, and `Host` headers
resolve to local addresses (`127.0.0.1`, `localhost`, `::1`). Remote requests are
blocked unless `allow_remote=true` is explicitly configured.

## Network Binding

| Setting | Default | Purpose |
|---|---|---|
| `web.host` | `127.0.0.1` | Localhost-only binding |
| `web.allow_remote` | `false` | Blocks non-local requests |
| `web.admin_token_env` | `BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN` | Required for remote access |

The server binds to `127.0.0.1` by default, making it accessible only from the local
machine. Enabling remote access requires:
1. Setting `allow_remote: true` in `config/run_config.json`
2. Setting a strong admin token in the `BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN` environment
   variable
3. Validating the admin token via `Authorization: Bearer <token>` or
   `X-Brain-Alpha-Admin-Token` header

## Log Redaction

`brain_alpha_ops/redaction.py` provides a multi-layer redaction system:

### Automatic log filter

`CredentialRedactionFilter` is installed automatically on import of `secure_credentials.py`.
It redacts:
- **Key-value pairs** where the key matches 38 sensitive patterns (password, token,
  secret, api_key, csrf, session, email, etc.)
- **Authorization headers** (`Basic ...`, `Bearer ...`)
- **Email addresses** (replaced with `***@***`)
- **Secret fragments** containing sensitive substrings
- **Printf-style positional arguments** that follow sensitive key names

### Data redaction

`redact_data()` recursively walks dicts/lists/tuples:
- Replaces values of sensitive keys with `<redacted>`
- Handles nested structures up to depth 8
- Detects circular references
- Strips string values through `redact_text()`

### CI enforcement

The quality gate runs `check_log_redaction.py` to audit log output for unredacted
credentials. Findings fail the CI build.

## Browser Automation Security

When using the `browser` execution backend (Playwright):

- Chromium runs in a headless, sandboxed environment
- Evidence artifacts (screenshots, DOM snapshots) are written to a dedicated
  `/app/artifacts/evidence` directory
- HAR files capture network traffic for audit purposes
- The browser never stores BRAIN credentials in browser storage — credentials are
  injected via Playwright context

### Docker considerations

- The Dockerfile creates `/app/artifacts/evidence` with `chmod 777` for container
  isolation
- Playwright Chromium is installed with `--with-deps` to ensure all system libraries
  are present
- The container runs as a single service with no privilege escalation

## MCP Security Considerations

The web console uses the Model Context Protocol (MCP) for agent-tool communication.
Key security properties:

- All MCP tool calls are authenticated via session + CSRF tokens
- Tool output is redacted through the standard redaction pipeline before returning
  to the browser
- Rate limiting applies to MCP-initiated BRAIN API calls (max 3 concurrent simulations)
- Tool surface limits are enforced via `AgentLimits` constants in `runtime_constants.py`

## Additional Security Measures

| Measure | Implementation |
|---|---|
| **Content-Security-Policy** | Auto-generated with SHA-256 hashes; `default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'` |
| **Rate limiting** | Max 3 concurrent simulations, 60s minimum retry pause, exponential backoff up to 3600s |
| **Compliance checks** | 8 redline check types (alignment, coverage, datasets, thresholds, etc.) |
| **CI secret scan** | `scan_sensitive_artifacts.py --fail-on-findings` runs in the quality gate |
| **Hard gates** | 8 official hard gates with a constrained whitelist (`OFFICIAL_HARD_GATE_NAMES`) |
| **No external DB** | JSONL + SQLite persistence — no network database to secure |
| **Stdlib HTTP** | No third-party HTTP framework — stdlib `http.server` reduces attack surface |

## Threat Model Summary

| Threat | Mitigation |
|---|---|
| Credential leak via logs | `CredentialRedactionFilter` auto-installed; CI audit |
| Unauthorized alpha submission | `REAL_SUBMIT_DISABLED_WEB_FLOW` kill-switch; triple-gate test override |
| CSRF attacks | Per-session CSRF token + constant-time validation |
| Session hijacking | `HttpOnly` + `SameSite=Strict` cookies; TTL limits; replay protection |
| Remote access abuse | Localhost-only default; admin token required for remote |
| Memory exhaustion | Replay cache hard cap (10K entries); session pruning |
| Supply chain | Stdlib-only HTTP; pinned `requirements.lock`; dependency policy CI gate |
| Browser evidence tampering | Isolated container directory; HAR audit trail |
