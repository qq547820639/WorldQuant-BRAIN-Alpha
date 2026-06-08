/** Shared CSRF token and request-ID helpers. */

/** Read CSRF token from <meta> tag injected by the server. */
export function csrfToken(): string {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-csrf"]');
  const token = (meta?.content || "").trim();
  // Server replaces the __BRAIN_ALPHA_OPS_CSRF_TOKEN__ placeholder at serve time;
  // if the placeholder is still present the token was not properly injected.
  return token && !token.startsWith("__BRAIN_ALPHA_OPS") ? token : "";
}

/** Read SSE stream token from <meta> tag injected by the server. */
export function streamToken(): string {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-stream"]');
  const token = (meta?.content || "").trim();
  return token && !token.startsWith("__BRAIN_ALPHA_OPS") ? token : "";
}

/** Generate a unique request ID (crypto-based UUID if available). */
export function createRequestId(): string {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

/** Build CSRF + request-ID headers for POST/PUT/PATCH/DELETE requests. */
export function csrfHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Brain-Alpha-Request-ID": createRequestId(),
    "X-Brain-Alpha-Request-Timestamp": String(Date.now()),
  };
  const token = csrfToken();
  if (token) headers["X-Brain-Alpha-CSRF"] = token;
  return headers;
}
