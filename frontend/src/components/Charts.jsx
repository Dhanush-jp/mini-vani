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
  background: "var(--surface-alt)",
  border: "1px solid var(--border)",
  borderRadius: "14px",
  color: "var(--text)",
  boxShadow: "var(--shadow)",
  backdropFilter: "blur(8px)",
};

const axisProps = { 
  stroke: "var(--chart-text)", 
  tick: { fill: "var(--chart-text)", fontSize: 11 } 
};

function ChartEmpty({ title, message }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-alt)] p-4 text-center text-sm">
      <div>
        <p className="font-semibold opacity-80">{title}</p>
        <p className="mt-1 opacity-50">{message}</p>
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
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="semester" {...axisProps} axisLine={false} tickLine={false} />
          <YAxis {...axisProps} domain={[0, 10]} axisLine={false} tickLine={false} />
          <Tooltip 
            contentStyle={tooltipStyle} 
            itemStyle={{ fontSize: '13px', fontWeight: 600 }}
            cursor={{ stroke: 'var(--chart-grid)', strokeWidth: 2 }}
          />
          <Legend iconType="circle" wrapperStyle={{ paddingTop: '10px', fontSize: '12px' }} />
          <Line type="monotone" dataKey="sgpa" stroke="#0ea5e9" strokeWidth={3} dot={{ r: 4, fill: '#0ea5e9', strokeWidth: 0 }} activeDot={{ r: 6 }} />
          <Line type="monotone" dataKey="cgpa" stroke="#6366f1" strokeWidth={3} dot={{ r: 4, fill: '#6366f1', strokeWidth: 0 }} activeDot={{ r: 6 }} />
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
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="subject"
            {...axisProps}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 10 }}
            interval={0}
            angle={-18}
            textAnchor="end"
            height={56}
          />
          <YAxis {...axisProps} domain={[0, 100]} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--chart-grid)', opacity: 0.4 }} />
          <Bar dataKey="marks" fill="#10b981" radius={[6, 6, 0, 0]} barSize={32} />
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
          <Pie data={chartData} cx="50%" cy="50%" dataKey="value" nameKey="name" outerRadius={80} innerRadius={60} paddingAngle={5} label>
            {chartData.map((entry, i) => (
              <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="none" />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} />
          <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
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
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="subject" {...axisProps} axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
          <YAxis {...axisProps} domain={[0, 100]} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--chart-grid)', opacity: 0.4 }} />
          <Bar dataKey="attendance_pct" fill="#3b82f6" name="Attendance %" radius={[6, 6, 0, 0]} barSize={32} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AttendanceTrendLine({ data }) {
  if (!data?.length) {
    return <ChartEmpty title="Attendance trend" message="No dated attendance yet." />;
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="label" {...axisProps} axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
          <YAxis {...axisProps} domain={[0, 100]} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} />
          <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
          <Line
            type="monotone"
            dataKey="attendance_pct"
            stroke="#3b82f6"
            strokeWidth={3}
            name="Cumulative %"
            dot={{ r: 3, fill: '#3b82f6', strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
