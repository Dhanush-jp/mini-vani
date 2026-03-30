import { AnimatePresence, motion } from "framer-motion";

export default function Modal({ open, title, children, onClose, width = "max-w-2xl" }) {
  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm"
        >
          <motion.div
            initial={{ y: 20, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 20, opacity: 0 }}
            className={`glass-panel ${width} w-full rounded-2xl border border-slate-200/90 bg-white p-6 text-slate-900 shadow-2xl shadow-slate-900/10`}
          >
            <div className="mb-5 flex items-center justify-between gap-4">
              <h3 className="font-display text-2xl font-semibold">{title}</h3>
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
              >
                Close
              </button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
