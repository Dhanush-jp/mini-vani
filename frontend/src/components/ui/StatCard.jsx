import { motion } from "framer-motion";
import Card from "./Card";

export default function StatCard({ title, value, hint, accent = "from-sky-50 to-indigo-50/80", delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      <Card className={`bg-linear-to-br ${accent} p-5`}>
        <p className="text-sm font-medium text-slate-500">{title}</p>
        <p className="mt-2 font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">{value}</p>
        {hint ? <p className="mt-2 text-sm text-slate-500">{hint}</p> : null}
      </Card>
    </motion.div>
  );
}
