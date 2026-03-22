/** Normalize API / localStorage role strings (e.g. "admin" → "ADMIN"). */
export function normalizeRole(role) {
  return String(role ?? "")
    .trim()
    .toUpperCase();
}
