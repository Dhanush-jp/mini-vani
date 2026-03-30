/**
 * SemesterHistory.jsx
 *
 * Full semester-by-semester performance viewer with:
 *  - Clickable semester tabs (colour-coded: current = accent)
 *  - Per-subject table: marks, attendance, grade, pass/fail badge
 *  - Summary stat bar for the selected semester
 *  - Radar/Bar chart comparing selected semester vs another
 *  - Side-by-side comparison mode: pick sem A and sem B
 *
 * Props:
 *   role       {string}  - "ADMIN" | "TEACHER" | "STUDENT"
 *   studentId  {number|null} - required for ADMIN/TEACHER; null for STUDENT
 */
import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState, useCallback } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Legend, ReferenceLine,
} from "recharts";
import { fetchSemesterHistory, fetchSemesterComparison } from "../services/portal";
import Card from "./ui/Card";
import ChartCard from "./ui/ChartCard";

// ─── helpers ────────────────────────────────────────────────────────────────

const tooltipStyle = {
  background: "var(--surface-alt)",
  border: "1px solid var(--border)",
  borderRadius: "14px",
  color: "var(--text)",
  boxShadow: "var(--shadow)",
  backdropFilter: "blur(8px)",
  fontSize: "13px",
};

function DeltaBadge({ value, inverse = false }) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>;
  const good = inverse ? value < 0 : value > 0;
  const zero = value === 0;
  const cls = zero
    ? "text-slate-500"
    : good
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-rose-500 dark:text-rose-400";
  const sign = value > 0 ? "+" : "";
  return <span className={`font-semibold tabular-nums ${cls}`}>{sign}{value}</span>;
}

function PassBadge({ isPass }) {
  return isPass
    ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">Pass</span>
    : <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">Fail</span>;
}

function AttBar({ pct }) {
  const pctNum = Number(pct ?? 0);
  const color = pctNum >= 75 ? "#10b981" : pctNum >= 60 ? "#f59e0b" : "#f43f5e";
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 w-20 rounded-full bg-slate-200 dark:bg-slate-700">
        <div
          className="absolute left-0 top-0 h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(pctNum, 100)}%`, background: color }}
        />
      </div>
      <span className="tabular-nums text-xs font-medium" style={{ color }}>{pctNum}%</span>
    </div>
  );
}

function SemTab({ num, isCurrent, isSelected, isCompareA, isCompareB, compareMode, onClick }) {
  let bg = "bg-[var(--surface-alt)] text-[var(--text-muted)]";
  if (isSelected && !compareMode) bg = "bg-indigo-600 text-white shadow-lg shadow-indigo-500/30";
  if (compareMode && isCompareA)  bg = "bg-sky-500 text-white shadow-md shadow-sky-500/30";
  if (compareMode && isCompareB)  bg = "bg-amber-500 text-white shadow-md shadow-amber-500/30";

  return (
    <button
      onClick={() => onClick(num)}
      className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-sm font-bold transition-all duration-200 hover:scale-105 ${bg}`}
    >
      S{num}
      {isCurrent && (
        <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-white dark:ring-[var(--surface)]" title="Current semester" />
      )}
    </button>
  );
}

// ─── main component ──────────────────────────────────────────────────────────

export default function SemesterHistory({ role, studentId }) {
  const [history, setHistory]           = useState(null);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState("");
  const [selectedSem, setSelectedSem]   = useState(null);
  const [compareMode, setCompareMode]   = useState(false);
  const [compareA, setCompareA]         = useState(null);
  const [compareB, setCompareB]         = useState(null);
  const [comparison, setComparison]     = useState(null);
  const [cmpLoading, setCmpLoading]     = useState(false);

  // ── Load full history once ───────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchSemesterHistory(role, studentId)
      .then((data) => {
        if (cancelled) return;
        console.log("[SemesterHistory] History loaded:", data);
        setHistory(data);
        if (data.current_semester) setSelectedSem(data.current_semester);
      })
      .catch((err) => {
        console.error("[SemesterHistory] History failed:", err);
        if (!cancelled) setError(err?.response?.data?.detail || "Failed to load semester history.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [role, studentId]);

  // ── Load comparison when both semesters chosen ───────────────────────────
  useEffect(() => {
    if (!compareMode || !compareA || !compareB || compareA === compareB) {
      setComparison(null);
      return;
    }
    let cancelled = false;
    setCmpLoading(true);
    fetchSemesterComparison(role, studentId, compareA, compareB)
      .then((data) => { if (!cancelled) setComparison(data); })
      .catch(() => { if (!cancelled) setComparison(null); })
      .finally(() => { if (!cancelled) setCmpLoading(false); });
    return () => { cancelled = true; };
  }, [compareMode, compareA, compareB, role, studentId]);

  // ── Tab click handler ────────────────────────────────────────────────────
  const handleTabClick = useCallback((num) => {
    if (!compareMode) {
      setSelectedSem(num);
      return;
    }
    // In compare mode: first click = A, second different = B, third resets A
    if (compareA === null || (compareA !== null && compareB !== null)) {
      setCompareA(num); setCompareB(null); setComparison(null);
    } else if (num !== compareA) {
      setCompareB(num);
    } else {
      setCompareA(null);
    }
  }, [compareMode, compareA, compareB]);

  const toggleCompare = () => {
    setCompareMode((v) => !v);
    setCompareA(null); setCompareB(null); setComparison(null);
  };

  // ── Render guards ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-alt)]">
        <p className="animate-pulse text-sm opacity-60">Loading semester history…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300">
        {error}
      </div>
    );
  }
  if (!history || !history.semesters?.length) {
    return (
      <div className="flex h-40 items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-alt)] text-sm opacity-50">
        No data available for semester history.
      </div>
    );
  }

  const { semesters, all_semester_numbers, current_semester } = history;
  const semMap = Object.fromEntries(semesters.map((s) => [s.semester, s]));
  const activeSem = semMap[selectedSem] || semesters[semesters.length - 1];

  // Build radar data for selected semester
  const radarData = (activeSem?.subjects || []).map((s) => ({
    subject: s.subject_code || s.subject_name?.slice(0, 8),
    Marks: s.marks,
    Attendance: s.attendance_pct,
  }));

  // Build bar data for SGPA/CGPA across all semesters
  const trendBarData = semesters.map((s) => ({
    name: `S${s.semester}`,
    SGPA: s.sgpa ?? 0,
    CGPA: s.cgpa ?? 0,
    isCurrent: s.is_current,
  }));

  return (
    <div className="space-y-6">
      {/* ── Header row ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-display text-xl font-semibold">Semester Performance History</h3>
          <p className="mt-0.5 text-sm opacity-60">
            {semesters.length} semester{semesters.length !== 1 ? "s" : ""} recorded ·
            {" "}Current: <span className="font-semibold">Semester {current_semester}</span>
          </p>
        </div>
        <button
          onClick={toggleCompare}
          className={`rounded-xl px-4 py-2 text-sm font-semibold transition-all duration-200 ${
            compareMode
              ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/30"
              : "border border-[var(--border)] bg-[var(--surface-alt)] hover:border-indigo-300"
          }`}
        >
          {compareMode ? "✕ Exit Compare" : "⇄ Compare Semesters"}
        </button>
      </div>

      {/* ── Semester tabs ───────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2">
        {all_semester_numbers.map((num) => (
          <SemTab
            key={num}
            num={num}
            isCurrent={num === current_semester}
            isSelected={!compareMode && num === selectedSem}
            isCompareA={compareMode && num === compareA}
            isCompareB={compareMode && num === compareB}
            compareMode={compareMode}
            onClick={handleTabClick}
          />
        ))}
        {compareMode && (
          <span className="flex items-center px-2 text-xs opacity-60">
            {compareA === null
              ? "← Click a semester to set A"
              : compareB === null
                ? "← Now click semester B"
                : `Comparing S${compareA} vs S${compareB}`}
          </span>
        )}
      </div>

      {/* ── COMPARE MODE ────────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        {compareMode && comparison && !cmpLoading && (
          <motion.div
            key="compare"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="space-y-5"
          >
            {/* Delta stats row */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "SGPA change",       val: comparison.sgpa_delta,      inv: false },
                { label: "CGPA change",       val: comparison.cgpa_delta,      inv: false },
                { label: "Avg marks change",  val: comparison.avg_marks_delta, inv: false },
                { label: "Backlogs change",   val: comparison.backlogs_delta,  inv: true  },
              ].map((item) => (
                <Card key={item.label} className="p-4">
                  <p className="text-xs font-medium opacity-60">{item.label}</p>
                  <p className="mt-1 text-2xl font-bold">
                    <DeltaBadge value={item.val} inverse={item.inv} />
                  </p>
                  <p className="mt-0.5 text-xs opacity-50">
                    S{comparison.sem_a} → S{comparison.sem_b}
                  </p>
                </Card>
              ))}
            </div>

            {/* Side-by-side SGPA/CGPA */}
            <div className="grid gap-4 sm:grid-cols-2">
              {[
                { label: "SGPA", a: comparison.sem_a_data?.sgpa, b: comparison.sem_b_data?.sgpa },
                { label: "CGPA", a: comparison.sem_a_data?.cgpa, b: comparison.sem_b_data?.cgpa },
              ].map((m) => (
                <Card key={m.label} className="p-4">
                  <p className="mb-3 text-sm font-semibold opacity-70">{m.label}</p>
                  <div className="flex items-end gap-4">
                    <div className="flex-1 text-center">
                      <p className="text-xs font-medium text-sky-500">S{comparison.sem_a}</p>
                      <p className="mt-1 font-display text-3xl font-bold text-sky-600 dark:text-sky-400">{m.a ?? "—"}</p>
                    </div>
                    <div className="pb-1 text-lg font-light opacity-40">→</div>
                    <div className="flex-1 text-center">
                      <p className="text-xs font-medium text-amber-500">S{comparison.sem_b}</p>
                      <p className="mt-1 font-display text-3xl font-bold text-amber-600 dark:text-amber-400">{m.b ?? "—"}</p>
                    </div>
                  </div>
                </Card>
              ))}
            </div>

            {/* Subject-level diff table */}
            <Card className="overflow-hidden p-0">
              <div className="border-b border-[var(--border)] px-5 py-4">
                <h4 className="font-display font-semibold">Subject-level comparison</h4>
                <p className="mt-0.5 text-xs opacity-60">
                  <span className="font-medium text-sky-500">Blue = S{comparison.sem_a}</span>
                  {" · "}
                  <span className="font-medium text-amber-500">Amber = S{comparison.sem_b}</span>
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border)] bg-[var(--surface-alt)] text-xs uppercase tracking-wide opacity-60">
                      <th className="px-5 py-3 text-left font-semibold">Subject</th>
                      <th className="px-4 py-3 text-center font-semibold">S{comparison.sem_a} Marks</th>
                      <th className="px-4 py-3 text-center font-semibold">S{comparison.sem_b} Marks</th>
                      <th className="px-4 py-3 text-center font-semibold">Δ Marks</th>
                      <th className="px-4 py-3 text-center font-semibold">S{comparison.sem_a} Att%</th>
                      <th className="px-4 py-3 text-center font-semibold">S{comparison.sem_b} Att%</th>
                      <th className="px-4 py-3 text-center font-semibold">Δ Att%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(comparison.subject_diff || []).map((row, i) => (
                      <tr
                        key={row.subject_name}
                        className={`border-b border-[var(--border)] transition-colors hover:bg-[var(--surface-alt)] ${i % 2 === 0 ? "" : "bg-[var(--surface-alt)]/30"}`}
                      >
                        <td className="px-5 py-3 font-medium">{row.subject_name}</td>
                        <td className="px-4 py-3 text-center tabular-nums text-sky-600 dark:text-sky-400">{row.sem_a_marks ?? "—"}</td>
                        <td className="px-4 py-3 text-center tabular-nums text-amber-600 dark:text-amber-400">{row.sem_b_marks ?? "—"}</td>
                        <td className="px-4 py-3 text-center"><DeltaBadge value={row.marks_delta} /></td>
                        <td className="px-4 py-3 text-center tabular-nums text-sky-600 dark:text-sky-400">{row.sem_a_attendance ?? "—"}</td>
                        <td className="px-4 py-3 text-center tabular-nums text-amber-600 dark:text-amber-400">{row.sem_b_attendance ?? "—"}</td>
                        <td className="px-4 py-3 text-center"><DeltaBadge value={row.attendance_delta} /></td>
                      </tr>
                    ))}
                    {!comparison.subject_diff?.length && (
                      <tr><td colSpan={7} className="py-6 text-center opacity-50">No shared subjects between the two semesters.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>

            {/* Comparison bar chart for marks */}
            {comparison.subject_diff?.length > 0 && (
              <ChartCard title="Marks comparison" description="Side-by-side per subject">
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={comparison.subject_diff.map((r) => ({
                      name: (r.subject_name || "").slice(0, 10),
                      [`S${comparison.sem_a}`]: r.sem_a_marks,
                      [`S${comparison.sem_b}`]: r.sem_b_marks,
                    }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--chart-text)" }} axisLine={false} tickLine={false} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "var(--chart-text)" }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: "12px" }} />
                      <Bar dataKey={`S${comparison.sem_a}`} fill="#0ea5e9" radius={[5, 5, 0, 0]} barSize={20} />
                      <Bar dataKey={`S${comparison.sem_b}`} fill="#f59e0b" radius={[5, 5, 0, 0]} barSize={20} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>
            )}
          </motion.div>
        )}

        {compareMode && cmpLoading && (
          <motion.div key="cmp-loading" className="flex h-32 items-center justify-center">
            <p className="animate-pulse text-sm opacity-60">Comparing semesters…</p>
          </motion.div>
        )}

        {/* ── SINGLE SEMESTER VIEW ─────────────────────────────────────── */}
        {!compareMode && activeSem && (
          <motion.div
            key={`sem-${activeSem.semester}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="space-y-5"
          >
            {/* Summary stats */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "SGPA",            val: activeSem.sgpa ?? "—",                             accent: "from-sky-500 to-blue-500" },
                { label: "CGPA",            val: activeSem.cgpa ?? "—",                             accent: "from-indigo-500 to-violet-500" },
                { label: "Avg Marks",       val: activeSem.summary?.avg_marks != null
                    ? `${activeSem.summary.avg_marks}%` : "—",                                       accent: "from-emerald-500 to-teal-500" },
                { label: "Avg Attendance",  val: activeSem.summary?.avg_attendance != null
                    ? `${activeSem.summary.avg_attendance}%` : "—",                                  accent: "from-amber-500 to-orange-500" },
              ].map((item, i) => (
                <motion.div key={item.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
                  <Card className={`relative overflow-hidden p-4`}>
                    <div className={`absolute inset-0 bg-linear-to-br ${item.accent} opacity-10 dark:opacity-15`} />
                    <div className="relative">
                      <p className="text-xs font-medium opacity-60">{item.label}</p>
                      <p className="mt-1 font-display text-2xl font-bold">{item.val}</p>
                    </div>
                  </Card>
                </motion.div>
              ))}
            </div>

            {/* Pass/fail + backlogs badges */}
            <div className="flex flex-wrap gap-3">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-sm font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                ✓ {activeSem.summary?.pass_count ?? 0} Passed
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-100 px-3 py-1 text-sm font-semibold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                ✗ {activeSem.summary?.fail_count ?? 0} Failed
              </span>
              {activeSem.backlogs != null && (
                <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold ${
                  activeSem.backlogs > 0
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                    : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                }`}>
                  {activeSem.backlogs} Backlog{activeSem.backlogs !== 1 ? "s" : ""}
                </span>
              )}
              {activeSem.is_current && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-100 px-3 py-1 text-sm font-semibold text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                  ● Current Semester
                </span>
              )}
            </div>

            {/* Subject table */}
            <Card className="overflow-hidden p-0">
              <div className="border-b border-[var(--border)] px-5 py-4">
                <h4 className="font-display font-semibold">
                  Semester {activeSem.semester} — Subjects
                </h4>
                <p className="mt-0.5 text-xs opacity-60">
                  {activeSem.subjects?.length ?? 0} subject{activeSem.subjects?.length !== 1 ? "s" : ""}
                </p>
              </div>
              {activeSem.subjects?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[var(--border)] bg-[var(--surface-alt)] text-xs uppercase tracking-wide opacity-60">
                        <th className="px-5 py-3 text-left font-semibold">Subject</th>
                        <th className="px-5 py-3 text-left font-semibold hidden sm:table-cell">Code</th>
                        <th className="px-4 py-3 text-center font-semibold">Marks</th>
                        <th className="px-4 py-3 text-center font-semibold">Grade</th>
                        <th className="px-4 py-3 text-left font-semibold">Attendance</th>
                        <th className="px-4 py-3 text-center font-semibold">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeSem.subjects.map((s, i) => (
                        <motion.tr
                          key={s.subject_name}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.04 }}
                          className={`border-b border-[var(--border)] last:border-0 transition-colors hover:bg-[var(--surface-alt)] ${i % 2 === 0 ? "" : "bg-[var(--surface-alt)]/20"}`}
                        >
                          <td className="px-5 py-3 font-medium">{s.subject_name}</td>
                          <td className="px-5 py-3 hidden font-mono text-xs opacity-60 sm:table-cell">{s.subject_code ?? "—"}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={`tabular-nums font-bold ${
                              s.marks >= 70 ? "text-emerald-600 dark:text-emerald-400"
                              : s.marks >= 50 ? "text-amber-600 dark:text-amber-400"
                              : "text-rose-600 dark:text-rose-400"
                            }`}>{s.marks ?? "—"}</span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className="rounded-lg bg-[var(--surface-alt)] px-2 py-0.5 font-mono text-xs font-bold">
                              {s.grade ?? "—"}
                            </span>
                          </td>
                          <td className="px-4 py-3"><AttBar pct={s.attendance_pct} /></td>
                          <td className="px-4 py-3 text-center"><PassBadge isPass={s.is_pass} /></td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="px-5 py-8 text-center text-sm opacity-50">No subject records for this semester.</p>
              )}
            </Card>

            {/* Charts — radar + overall SGPA/CGPA trend */}
            <div className="grid gap-5 xl:grid-cols-2">
              {radarData.length > 2 && (
                <ChartCard title={`Semester ${activeSem.semester} — Subject radar`} description="Marks vs attendance by subject">
                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <RadarChart data={radarData}>
                        <PolarGrid stroke="var(--chart-grid)" />
                        <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: "var(--chart-text)" }} />
                        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9, fill: "var(--chart-text)" }} />
                        <Radar name="Marks" dataKey="Marks" stroke="#6366f1" fill="#6366f1" fillOpacity={0.35} />
                        <Radar name="Attendance %" dataKey="Attendance" stroke="#10b981" fill="#10b981" fillOpacity={0.25} />
                        <Legend iconType="circle" wrapperStyle={{ fontSize: "12px" }} />
                        <Tooltip contentStyle={tooltipStyle} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartCard>
              )}

              {/* SGPA/CGPA across all semesters with current highlighted */}
              <ChartCard title="SGPA / CGPA across all semesters" description="Your academic trajectory" className={radarData.length <= 2 ? "xl:col-span-2" : ""}>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={trendBarData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--chart-text)" }} axisLine={false} tickLine={false} />
                      <YAxis domain={[0, 10]} tick={{ fontSize: 11, fill: "var(--chart-text)" }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: "12px" }} />
                      <ReferenceLine
                        x={`S${activeSem.semester}`}
                        stroke="#6366f1"
                        strokeDasharray="4 3"
                        strokeWidth={2}
                        label={{ value: "Selected", position: "top", fontSize: 10, fill: "#6366f1" }}
                      />
                      <Bar dataKey="SGPA" fill="#0ea5e9" radius={[5, 5, 0, 0]} barSize={22} />
                      <Bar dataKey="CGPA" fill="#6366f1" radius={[5, 5, 0, 0]} barSize={22} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
