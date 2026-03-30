import { motion } from "framer-motion";

/**
 * Standard card surface. Rounded-2xl by default with theme-aware background/border.
 */
export default function Card({ children, className = "", hover = false, ...props }) {
  const base = "glass-panel p-6 shadow-sm transition-all duration-300";
  const hoverCls = hover
    ? "hover:translate-y-[-2px] hover:shadow-md hover:border-[var(--accent)]"
    : "";
    
  return (
    <motion.div
      className={`${base} ${hoverCls} ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  );
}
