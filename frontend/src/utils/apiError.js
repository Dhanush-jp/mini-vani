/**
 * Normalize FastAPI / axios error payloads for display.
 */
export function formatApiError(error) {
  if (!error?.response) {
    if (error?.code === "ECONNABORTED") {
      return "Request timed out. Check that the backend is running.";
    }
    const msg = error?.message || "";
    if (/network error/i.test(msg) || error?.code === "ERR_NETWORK") {
      return (
        "Cannot reach the API (connection failed or blocked). " +
        "Start the backend (python main.py on port 8000), confirm VITE_API_ORIGIN matches it, " +
        "and check browser console — a missing CORS header usually means the server did not respond or crashed."
      );
    }
    if (msg) return msg;
    return "Network error. Is the API running at http://localhost:8000 ?";
  }

  const { data, status } = error.response;
  const detail = data?.detail;

  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return `Request failed (${status || "error"})`;
}

/**
 * If server returned JSON error body while responseType was "blob", extract message.
 */
export async function formatBlobError(error) {
  const data = error?.response?.data;
  if (data instanceof Blob) {
    try {
      const text = await data.text();
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") return parsed.detail;
      if (Array.isArray(parsed.detail)) {
        return parsed.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      }
    } catch {
      return "Export failed (invalid server response).";
    }
  }
  return formatApiError(error);
}
