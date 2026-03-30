import { AttendanceBars, MarksChart, PassFailPie, TrendChart } from "../components/Charts";
import ChartCard from "../components/ui/ChartCard";
import MetricCard from "../components/MetricCard";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { usePortalData } from "../hooks/usePortalData";

export default function Analytics() {
  const { role } = useAuth();
  const { data } = usePortalData(role);

  if (role === "STUDENT") {
    const dashboard = data.studentDashboard;
    return (
      <div className="space-y-6">
        <section className="grid gap-4 md:grid-cols-3">
          <MetricCard title="CGPA" value={data.studentSummary?.cgpa ?? 0} hint="Cumulative grade point average" />
          <MetricCard
            title="Attendance"
            value={`${data.studentSummary?.attendance_pct ?? 0}%`}
            hint="Attendance ratio"
            accent="from-amber-400/20 to-orange-500/10"
          />
          <MetricCard
            title="Backlogs"
            value={data.studentSummary?.backlogs ?? 0}
            hint="Current arrears"
            accent="from-rose-400/20 to-fuchsia-500/10"
          />
        </section>
        <section className="grid gap-6 xl:grid-cols-2">
          <ChartCard title="SGPA / CGPA trend" description="Semester curve">
            <TrendChart data={dashboard?.trends || []} />
          </ChartCard>
          <ChartCard title="Subject marks" description="Graded performance">
            <MarksChart data={(dashboard?.marks || []).map((row) => ({ ...row, subject: row.subject_name }))} />
          </ChartCard>
          <ChartCard title="Pass / fail" description="Subject outcomes">
            <PassFailPie pass={dashboard?.pass_fail_ratio?.pass} fail={dashboard?.pass_fail_ratio?.fail} />
          </ChartCard>
          <ChartCard title="Attendance by subject" description="Share per course">
            <AttendanceBars data={dashboard?.attendance || []} />
          </ChartCard>
        </section>
      </div>
    );
  }

  const students = data.students?.items || [];
  const highRisk = students.filter((student) => student.risk_level === "HIGH");
  const lowAttendance = students.filter((student) => Number(student.attendance_pct) < 75);

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-2xl p-6 md:p-8">
        <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">Analytics</h2>
        <p className="mt-2 text-sm text-slate-600">
          Computed SGPA, CGPA, backlogs, attendance weakness, and risk segmentation.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard title="Students" value={students.length} hint="Records in current scope" />
        <MetricCard
          title="High risk"
          value={highRisk.length}
          hint="Immediate intervention candidates"
          accent="from-rose-400/20 to-fuchsia-500/10"
        />
        <MetricCard
          title="Low attendance"
          value={lowAttendance.length}
          hint="Below 75% attendance"
          accent="from-amber-400/20 to-orange-500/10"
        />
      </section>

      <section className="glass-panel rounded-2xl p-6">
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="font-display text-xl font-semibold text-slate-900">High risk students</h3>
            <div className="mt-4 space-y-3">
              {highRisk.slice(0, 8).map((student) => (
                <Card key={student.id} className="px-4 py-3 text-sm text-slate-700">
                  {student.name} · CGPA {student.cgpa ?? 0} · Attendance {student.attendance_pct}%
                </Card>
              ))}
            </div>
          </div>
          <div>
            <h3 className="font-display text-xl font-semibold text-slate-900">Backlog snapshot</h3>
            <div className="mt-4 space-y-3">
              {students
                .filter((student) => student.backlogs > 0)
                .slice(0, 8)
                .map((student) => (
                  <Card key={student.id} className="px-4 py-3 text-sm text-slate-700">
                    {student.name} · {student.backlogs} backlog(s)
                  </Card>
                ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
