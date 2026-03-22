import { motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  AttendanceBars,
  AttendanceTrendLine,
  MarksChart,
  PassFailPie,
  TrendChart,
} from "../components/Charts";
import ChartCard from "../components/ui/ChartCard";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { fetchAttendanceHistory, fetchStudentDetail } from "../services/portal";
import { buildCumulativeAttendanceSeries } from "../utils/attendanceTrend";
import { formatApiError } from "../utils/apiError";

function initials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
}

export default function StudentDetail() {
  const { studentId } = useParams();
  const { role } = useAuth();
  const [detail, setDetail] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const chartsRef = useRef(null);
  const { scrollYProgress } = useScroll({
    target: chartsRef,
    offset: ["start end", "end start"],
  });
  const parallaxY = useTransform(scrollYProgress, [0, 1], [48, -48]);

  useEffect(() => {
    if (role === "STUDENT" || !studentId) return;
    setDetail(null);
    setHistory([]);
    setError("");
    setLoading(true);
    let cancelled = false;
    async function load() {
      try {
        const [d, h] = await Promise.all([
          fetchStudentDetail(role, studentId),
          fetchAttendanceHistory(studentId).catch(() => ({ items: [] })),
        ]);
        if (!cancelled) {
          setDetail(d);
          setHistory(h.items || []);
        }
      } catch (err) {
        if (!cancelled) setError(formatApiError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [role, studentId]);

  const trendData = useMemo(() => buildCumulativeAttendanceSeries(history), [history]);

  if (role === "STUDENT") {
    return <Navigate to="/dashboard" replace />;
  }

  if (loading && !detail) {
    return (
      <div className="glass-panel rounded-2xl p-10 text-center text-slate-600">
        Loading student profile…
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="space-y-4">
        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
        <Link to="/students" className="text-sm font-medium text-sky-600 hover:underline">
          ← Back to students
        </Link>
      </div>
    );
  }

  const student = detail?.student;
  const dashboard = {
    trends: detail?.trends,
    marks: detail?.marks,
    attendance: detail?.attendance,
    pass_fail_ratio: detail?.pass_fail_ratio,
    risk: detail?.risk,
  };

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className="glass-panel overflow-hidden rounded-2xl p-6 md:p-8"
      >
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-5">
            <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-linear-to-br from-sky-400 to-indigo-500 font-display text-2xl font-bold text-white shadow-lg shadow-sky-500/30">
              {initials(student?.name)}
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Student profile</p>
              <h1 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">{student?.name}</h1>
              <p className="mt-1 text-slate-600">{student?.email}</p>
              <p className="mt-2 text-sm text-slate-500">
                {student?.department} · Year {student?.year} · Section {student?.section} · {student?.roll_number}
              </p>
            </div>
          </div>
          <Link
            to="/students"
            className="inline-flex items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
          >
            ← All students
          </Link>
        </div>
      </motion.div>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          {
            label: "Latest CGPA",
            value: detail?.trends?.at(-1)?.cgpa ?? "—",
            sub: "From recorded semesters",
          },
          {
            label: "Latest SGPA",
            value: detail?.trends?.at(-1)?.sgpa ?? "—",
            sub: "Most recent term",
          },
          {
            label: "Risk score",
            value: detail?.risk?.risk_score != null ? Number(detail.risk.risk_score).toFixed(1) : "—",
            sub: "Model estimate",
          },
        ].map((item, i) => (
          <motion.div
            key={item.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 * i }}
          >
            <Card className="p-5">
              <p className="text-sm font-medium text-slate-500">{item.label}</p>
              <p className="mt-2 font-display text-3xl font-semibold text-slate-900">{item.value}</p>
              <p className="mt-1 text-xs text-slate-400">{item.sub}</p>
            </Card>
          </motion.div>
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="p-6 lg:col-span-1">
          <h2 className="font-display text-lg font-semibold text-slate-900">Attendance</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            Subject-level attendance from enrollments. Use the trend chart for session-by-session cumulative progress.
          </p>
        </Card>
        <Card className="p-6 lg:col-span-1">
          <h2 className="font-display text-lg font-semibold text-slate-900">Marks</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            Grades linked to assigned subjects. Bar chart shows comparative performance across courses.
          </p>
        </Card>
        <Card className="p-6 lg:col-span-1">
          <h2 className="font-display text-lg font-semibold text-slate-900">Performance</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            SGPA/CGPA curves and pass mix summarize long-term trajectory and outcomes.
          </p>
        </Card>
      </div>

      <motion.div ref={chartsRef} style={{ y: parallaxY }} className="space-y-6 will-change-transform">
        <div className="grid gap-6 xl:grid-cols-2">
          <ChartCard title="Marks per subject" description="Percentage by course">
            <MarksChart data={(dashboard.marks || []).map((row) => ({ ...row, subject: row.subject_name }))} />
          </ChartCard>
          <ChartCard title="Attendance trend" description="Cumulative % over dated sessions">
            <AttendanceTrendLine data={trendData} />
          </ChartCard>
          <ChartCard title="SGPA / CGPA" description="Semester trends">
            <TrendChart data={dashboard.trends || []} />
          </ChartCard>
          <ChartCard title="Attendance by subject" description="Share per course">
            <AttendanceBars data={dashboard.attendance || []} />
          </ChartCard>
          <ChartCard title="Pass / fail" description="Graded subjects" className="xl:col-span-2">
            <div className="mx-auto max-w-md">
              <PassFailPie pass={dashboard.pass_fail_ratio?.pass} fail={dashboard.pass_fail_ratio?.fail} />
            </div>
          </ChartCard>
        </div>
      </motion.div>

      {detail?.risk?.suggestions ? (
        <Card className="border-sky-100 bg-sky-50/50 p-6">
          <h3 className="font-display text-lg font-semibold text-slate-900">Insights</h3>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{detail.risk.suggestions}</p>
        </Card>
      ) : null}
    </div>
  );
}
