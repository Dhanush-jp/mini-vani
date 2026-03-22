/**
 * Build a JSON body for StudentFilter: omit empty/invalid numbers (avoids NaN → 422).
 */
export function buildStudentFilterPayload(raw) {
  const out = {};

  const intFields = ["semester", "subject_id", "student_id"];
  for (const key of intFields) {
    const v = raw[key];
    if (v === "" || v === null || v === undefined) continue;
    const n = Number(v);
    if (!Number.isInteger(n) || n <= 0) continue;
    out[key] = n;
  }

  const floatFields = ["attendance_min", "attendance_max", "cgpa_min", "cgpa_max"];
  for (const key of floatFields) {
    const v = raw[key];
    if (v === "" || v === null || v === undefined) continue;
    const n = Number(v);
    if (!Number.isFinite(n)) continue;
    out[key] = n;
  }

  if (raw.risk_level && ["LOW", "MEDIUM", "HIGH"].includes(raw.risk_level)) {
    out.risk_level = raw.risk_level;
  }

  if (raw.is_pass === "true" || raw.is_pass === true) out.is_pass = true;
  if (raw.is_pass === "false" || raw.is_pass === false) out.is_pass = false;

  return out;
}
