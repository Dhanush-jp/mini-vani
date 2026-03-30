import StatCard from "./ui/StatCard";

const ACCENT_MAP = {
  "from-cyan-400/20 to-sky-500/10": "from-sky-50 to-sky-100/80",
  "from-emerald-400/20 to-teal-500/10": "from-emerald-50 to-teal-50/90",
  "from-amber-400/20 to-orange-500/10": "from-amber-50 to-orange-50/90",
  "from-rose-400/20 to-fuchsia-500/10": "from-rose-50 to-fuchsia-50/80",
};

export default function MetricCard({ title, value, hint, accent = "from-cyan-400/20 to-sky-500/10" }) {
  const mapped = ACCENT_MAP[accent] || "from-slate-50 to-slate-100/90";
  return <StatCard title={title} value={value} hint={hint} accent={mapped} />;
}
