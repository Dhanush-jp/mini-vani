import { motion } from "framer-motion";
import MetricCard from "../components/MetricCard";
import StudentDashboardView from "../components/StudentDashboardView";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { usePortalData } from "../hooks/usePortalData";

export default function Dashboard() {
  const { role } = useAuth();
  const { data, loading, error } = usePortalData(role);

  const summary = data.summary;
  const studentDashboard = data.studentDashboard;
  const studentSummary = data.studentSummary;

  if (role === "STUDENT") {
    return (
      <StudentDashboardView
        summary={studentSummary}
        dashboard={studentDashboard}
        loading={loading}
        error={error}
      />
    );
  }

  return (
    <div className="space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel rounded-2xl p-6 md:p-8"
      >
        <div className="grid gap-8 lg:grid-cols-[1.35fr_1fr]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Operations overview</p>
            <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">
              Learning Analytics Dashboard
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600">
              {loading
                ? "Loading live metrics…"
                : error || "Track assigned students, attendance health, academic risk, and export-ready records from one workspace."}
            </p>
          </div>
          <Card className="p-5">
            <p className="text-sm font-medium text-slate-500">Workspace status</p>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between border-b border-slate-100 pb-2">
                <span className="text-slate-500">Role</span>
                <span className="font-medium text-slate-900">{role}</span>
              </div>
              <div className="flex justify-between border-b border-slate-100 pb-2">
                <span className="text-slate-500">Students in scope</span>
                <span className="font-medium text-slate-900">{summary.total_students}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">High risk</span>
                <span className="font-medium text-slate-900">{summary.high_risk_count}</span>
              </div>
            </div>
          </Card>
        </div>
      </motion.section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Students" value={summary.total_students} hint="Role-aware scoped roster" />
        <MetricCard
          title="Avg CGPA"
          value={summary.avg_cgpa}
          hint="Latest cumulative score"
          accent="from-emerald-400/20 to-teal-500/10"
        />
        <MetricCard
          title="Attendance"
          value={`${summary.avg_attendance}%`}
          hint="Average live attendance"
          accent="from-amber-400/20 to-orange-500/10"
        />
        <MetricCard
          title="Risk"
          value={summary.high_risk_count}
          hint="Students needing intervention"
          accent="from-rose-400/20 to-fuchsia-500/10"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card className="p-6">
          <h3 className="font-display text-xl font-semibold text-slate-900">Assigned Students Overview</h3>
          <p className="mt-3 text-sm leading-relaxed text-slate-600">
            Teachers work against the <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">teacher_students</code> mapping, so
            roster access, attendance writes, result updates, analytics, and exports operate on assigned students only.
          </p>
        </Card>
        <Card className="p-6">
          <h3 className="font-display text-xl font-semibold text-slate-900">Student Academic Journey</h3>
          <p className="mt-3 text-sm leading-relaxed text-slate-600">
            Use Students for search and drill-down, Attendance and Results for records, Analytics for review, and Export for workbooks.
          </p>
        </Card>
      </section>
    </div>
  );
}
