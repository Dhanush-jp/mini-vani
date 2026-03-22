/**
 * Build cumulative attendance % series for line chart from API attendance rows.
 * Each row: { date, status } where status is PRESENT or other.
 */
export function buildCumulativeAttendanceSeries(items) {
  if (!items?.length) return [];
  const sorted = [...items].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  let present = 0;
  return sorted.map((row, index) => {
    const total = index + 1;
    const st = String(row.status ?? "").toUpperCase();
    if (st === "PRESENT" || (st.includes("PRESENT") && !st.includes("ABSENT"))) present += 1;
    const attendance_pct = Math.round((present * 1000) / total) / 10;
    const d = String(row.date || "").slice(0, 10);
    return {
      label: d || `Session ${total}`,
      attendance_pct,
    };
  });
}
