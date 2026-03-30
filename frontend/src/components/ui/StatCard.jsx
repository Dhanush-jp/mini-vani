import { motion } from "framer-motion";
import Card from "./Card";

export default function StatCard({ title, value, hint, accent = "from-sky-500/10 to-blue-500/5", delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      <Card className={`relative overflow-hidden p-5`}>
        <div className={`absolute inset-0 bg-linear-to-br ${accent} opacity-40 dark:opacity-20`} />
        <div className="relative z-10">
          <p className="text-sm font-medium opacity-60">{title}</p>
          <p className="mt-2 font-display text-3xl font-bold tracking-tight md:text-4xl">{value}</p>
          {hint ? <p className="mt-2 text-sm opacity-50">{hint}</p> : null}
        </div>
      </Card>
    </motion.div>
  );
}
