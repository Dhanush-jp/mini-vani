import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const tooltipStyle = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: "12px",
  color: "#0f172a",
  boxShadow: "0 8px 24px -8px rgba(15,23,42,0.15)",
};

const axisProps = { stroke: "#94a3b8", tick: { fill: "#64748b", fontSize: 11 } };

function ChartEmpty({ title, message }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 p-4 text-center text-sm text-slate-500">
      <div>
        <p className="font-medium text-slate-800">{title}</p>
        <p className="mt-1">{message}</p>
      </div>
    </div>
  );
}

export function TrendChart({ data }) {
  if (!data?.length) {
    return <ChartEmpty title="SGPA / CGPA trend" message="No semester results yet." />;
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="semester" {...axisProps} />
          <YAxis {...axisProps} domain={[0, 10]} />
          <Tooltip contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ color: "#475569" }} />
          <Line type="monotone" dataKey="sgpa" stroke="#0ea5e9" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="cgpa" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MarksChart({ data }) {
  if (!data?.length) {
    return <ChartEmpty title="Subject marks" message="No grades recorded." />;
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="subject"
            {...axisProps}
            tick={{ fontSize: 10 }}
            interval={0}
            angle={-18}
            textAnchor="end"
            height={56}
          />
          <YAxis {...axisProps} domain={[0, 100]} />
          <Tooltip contentStyle={tooltipStyle} />
          <Bar dataKey="marks" fill="#10b981" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const PIE_COLORS = ["#10b981", "#f43f5e"];

export function PassFailPie({ pass, fail }) {
  const total = (pass || 0) + (fail || 0);
  if (!total) {
    return <ChartEmpty title="Pass / fail" message="No graded subjects yet." />;
  }
  const chartData = [
    { name: "Pass", value: pass || 0 },
    { name: "Fail", value: fail || 0 },
  ];
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={chartData} cx="50%" cy="50%" dataKey="value" nameKey="name" outerRadius={88} label>
            {chartData.map((entry, i) => (
              <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ color: "#475569" }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AttendanceBars({ data }) {
  if (!data?.length) {
    return <ChartEmpty title="Attendance by subject" message="No attendance records." />;
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="subject" {...axisProps} tick={{ fontSize: 10 }} />
          <YAxis {...axisProps} domain={[0, 100]} />
          <Tooltip contentStyle={tooltipStyle} />
          <Bar dataKey="attendance_pct" fill="#3b82f6" name="Attendance %" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Cumulative attendance % over dated sessions (from attendance history rows). */
export function AttendanceTrendLine({ data }) {
  if (!data?.length) {
    return <ChartEmpty title="Attendance trend" message="No dated attendance yet." />;
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="label" {...axisProps} tick={{ fontSize: 10 }} />
          <YAxis {...axisProps} domain={[0, 100]} />
          <Tooltip contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ color: "#475569" }} />
          <Line
            type="monotone"
            dataKey="attendance_pct"
            stroke="#3b82f6"
            strokeWidth={2}
            name="Cumulative %"
            dot={{ r: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
