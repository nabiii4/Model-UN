// Talks to our Flask server. Every non-GET request sends the CSRF token (section 14).
// The browser never sees an AI key: all AI calls go through the server.

const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

export class ApiError extends Error {
  constructor(status, data) {
    super((data && data.message) || "Something went wrong. Try again?");
    this.status = status;
    this.data = data || {};
    this.code = (data && data.error) || "error";
  }
}

const FRIENDLY_OFFLINE = "Can't reach the server. Check the Wi-Fi and try again.";

export async function api(path, { method = "GET", body, form, timeout = 60000, signal } = {}) {
  const headers = { "Accept": "application/json" };
  let payload;
  if (form) {
    payload = form; // FormData: the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  if (signal) signal.addEventListener("abort", () => ctrl.abort(), { once: true });
  let res;
  try {
    res = await fetch(path, { method, headers, body: payload, credentials: "same-origin", signal: ctrl.signal });
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") throw new ApiError(0, { error: "timeout", message: "That took too long. Try again?" });
    throw new ApiError(0, { error: "offline", message: FRIENDLY_OFFLINE });
  }
  clearTimeout(timer);
  let data = null;
  const type = res.headers.get("Content-Type") || "";
  if (type.includes("application/json")) {
    try { data = await res.json(); } catch { data = null; }
  }
  if (!res.ok) {
    if (!data) data = { error: "http_" + res.status, message: res.status === 413 ? "That file is too big." : "Something went wrong. Try again?" };
    throw new ApiError(res.status, data);
  }
  return data;
}

export const get = (path, opts) => api(path, { ...opts, method: "GET" });
export const post = (path, body, opts) => api(path, { ...opts, method: "POST", body });
export const patch = (path, body, opts) => api(path, { ...opts, method: "PATCH", body });
export const del = (path, body, opts) => api(path, { ...opts, method: "DELETE", body });
