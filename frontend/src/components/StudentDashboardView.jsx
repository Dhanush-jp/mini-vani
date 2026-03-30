import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AttendanceBars, MarksChart, PassFailPie, TrendChart } from "./Charts";
import ChartCard from "./ui/ChartCard";
import StatCard from "./ui/StatCard";
import Card from "./ui/Card";
import SemesterHistory from "./SemesterHistory";

function mergeSubjectRows(marks, attendance) {
  const bySubject = new Map();
  (marks || []).forEach((m) => {
    const key = m.subject_name || m.subject;
    bySubject.set(key, {
      subject: key,
      marks: m.marks,
      attendance_pct: null,
    });
  });
  (attendance || []).forEach((a) => {
    const row = bySubject.get(a.subject);
    if (row) row.attendance_pct = a.attendance_pct;
    else
      bySubject.set(a.subject, {
        subject: a.subject,
        marks: null,
        attendance_pct: a.attendance_pct,
      });
  });
  return [...bySubject.values()];
}

const TABS = [
  { id: "overview",  label: "Overview" },
  { id: "history",   label: "Semester History" },
];

export default function StudentDashboardView({ summary, dashboard, loading, error }) {
  const [activeTab, setActiveTab] = useState("overview");

  const marks = dashboard?.marks || [];
  const attendance = dashboard?.attendance || [];
  const avgMarks =
    marks.length > 0 ? (marks.reduce((s, m) => s + Number(m.marks || 0), 0) / marks.length).toFixed(1) : "—";
  const attPct = summary?.attendance_pct ?? 0;
  const riskScore = dashboard?.risk?.risk_score;
  const riskLabel =
    riskScore == null
      ? "—"
      : Number(riskScore) < 4
        ? "Low"
        : Number(riskScore) <= 7
          ? "Medium"
          : "High";

  const warnings = [];
  if (Number(attPct) < 75) warnings.push({ text: "Low attendance", detail: `Overall attendance is ${attPct}%.` });
  if (marks.length && Number(avgMarks) < 50) warnings.push({ text: "Low marks", detail: "Average across subjects is below 50." });
  if (riskLabel === "High") warnings.push({ text: "Elevated risk", detail: dashboard?.risk?.suggestions || "Review academic plan with your advisor." });

  const subjectRows = mergeSubjectRows(marks, attendance);

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel rounded-2xl p-6 md:p-8"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.2em] opacity-50">Your overview</p>
        <h2 className="mt-2 font-display text-3xl font-semibold tracking-tight md:text-4xl">
          Learning Analytics Dashboard
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed opacity-70">
          {loading
            ? "Loading your metrics…"
            : error || "View-only access: attendance, performance, and risk signals in one place."}
        </p>
      </motion.section>

      {/* ── Top stat cards ──────────────────────────────────────────────── */}
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard title="Attendance" value={`${attPct}%`} hint="Across recorded sessions" accent="from-sky-500 to-blue-500" delay={0.05} />
        <StatCard title="Average marks" value={avgMarks} hint="Mean of graded subjects" accent="from-emerald-500 to-teal-500" delay={0.1} />
        <StatCard title="Risk level" value={riskLabel} hint="From analytics model" accent="from-violet-500 to-fuchsia-500" delay={0.15} />
      </section>

      {/* ── Tab switcher ────────────────────────────────────────────────── */}
      <div className="flex gap-1 rounded-xl bg-[var(--surface-alt)] p-1 w-fit border border-[var(--border)]">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative rounded-lg px-5 py-2 text-sm font-semibold transition-all duration-200 ${
              activeTab === tab.id
                ? "bg-white text-indigo-700 shadow-sm dark:bg-[var(--surface)] dark:text-indigo-400"
                : "text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {tab.label}
            {tab.id === "history" && (
              <span className="ml-1.5 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-bold text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
                NEW
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tab content ─────────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        {activeTab === "overview" && (
          <motion.div
            key="overview"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="space-y-6"
          >
            {/* Risk warnings */}
            {warnings.length > 0 ? (
              <motion.section initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="space-y-3">
                <h3 className="font-display text-lg font-semibold">Risk analysis</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  {warnings.map((w) => (
                    <Card key={w.text} className="border-amber-500/30 bg-amber-500/10 p-4">
                      <p className="font-semibold text-amber-600 dark:text-amber-400">{w.text}</p>
                      <p className="mt-1 text-sm text-amber-700 dark:text-amber-300 opacity-90">{w.detail}</p>
                    </Card>
                  ))}
                </div>
              </motion.section>
            ) : null}

            {/* Subject cards grid */}
            <section>
              <h3 className="mb-4 font-display text-lg font-semibold">Subjects</h3>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {subjectRows.length ? (
                  subjectRows.map((row, i) => (
                    <motion.div
                      key={row.subject}
                      initial={{ opacity: 0, y: 10 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: i * 0.04 }}
                    >
                      <Card hover className="p-5">
                        <p className="font-display text-base font-semibold">{row.subject}</p>
                        <div className="mt-3 flex flex-wrap gap-4 text-sm">
                          <span className="opacity-60">
                            Marks:{" "}
                            <span className={`font-semibold opacity-100 ${
                              row.marks != null
                                ? Number(row.marks) >= 70 ? "text-emerald-600 dark:text-emerald-400"
                                  : Number(row.marks) >= 50 ? "text-amber-600 dark:text-amber-400"
                                  : "text-rose-600 dark:text-rose-400"
                                : ""
                            }`}>
                              {row.marks != null ? row.marks : "—"}
                            </span>
                          </span>
                          <span className="opacity-60">
                            Attendance:{" "}
                            <span className={`font-semibold opacity-100 ${
                              row.attendance_pct != null
                                ? Number(row.attendance_pct) >= 75 ? "text-emerald-600 dark:text-emerald-400"
                                  : "text-rose-600 dark:text-rose-400"
                                : ""
                            }`}>
                              {row.attendance_pct != null ? `${row.attendance_pct}%` : "—"}
                            </span>
                          </span>
                        </div>
                      </Card>
                    </motion.div>
                  ))
                ) : (
                  <p className="text-sm text-slate-500">No subject breakdown yet.</p>
                )}
              </div>
            </section>

            {/* Charts */}
            <section className="grid gap-6 xl:grid-cols-2">
              <ChartCard title="Marks by subject" description="Bar chart — percentage marks" delay={0}>
                <MarksChart data={marks.map((row) => ({ ...row, subject: row.subject_name }))} />
              </ChartCard>
              <ChartCard title="Attendance by subject" description="Share of sessions attended" delay={0.05}>
                <AttendanceBars data={attendance} />
              </ChartCard>
              <ChartCard title="SGPA / CGPA trend" description="Semester performance curve" delay={0.1}>
                <TrendChart data={dashboard?.trends || []} />
              </ChartCard>
              <ChartCard title="Pass / fail mix" description="Graded subjects overview" delay={0.12}>
                <PassFailPie pass={dashboard?.pass_fail_ratio?.pass} fail={dashboard?.pass_fail_ratio?.fail} />
              </ChartCard>
            </section>
          </motion.div>
        )}

        {activeTab === "history" && (
          <motion.div
            key="history"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
          >
            <Card className="p-6">
              <SemesterHistory role="STUDENT" studentId={null} />
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
