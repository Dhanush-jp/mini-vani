import { motion } from "framer-motion";

/**
 * Glass-style surface for light theme. rounded-2xl by default.
 */
export default function Card({ children, className = "", hover = false, ...props }) {
  const base =
    "rounded-2xl border border-slate-200/80 bg-white/70 shadow-[0_8px_40px_-12px_rgba(15,23,42,0.12)] backdrop-blur-xl";
  const hoverCls = hover
    ? "transition-shadow duration-300 hover:border-slate-300/90 hover:shadow-[0_16px_48px_-12px_rgba(15,23,42,0.18)]"
    : "";
  return (
    <motion.div
      whileHover={hover ? { y: -2 } : undefined}
      className={`${base} ${hoverCls} ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  );
}
