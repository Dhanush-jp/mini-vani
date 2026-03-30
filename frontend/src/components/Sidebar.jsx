import { motion } from "framer-motion";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const ALL_NAV = [
  { to: "/dashboard", label: "Dashboard", roles: ["ADMIN", "TEACHER", "STUDENT"] },
  { to: "/students", label: "Students", roles: ["ADMIN", "TEACHER"] },
  { to: "/attendance", label: "Attendance", roles: ["ADMIN", "TEACHER"] },
  { to: "/results", label: "Results", roles: ["ADMIN", "TEACHER"] },
  { to: "/analytics", label: "Analytics", roles: ["ADMIN", "TEACHER", "STUDENT"] },
  { to: "/upload", label: "Upload", roles: ["ADMIN", "TEACHER"] },
  { to: "/export", label: "Export", roles: ["ADMIN", "TEACHER"] },
  { to: "/subjects", label: "Subjects", roles: ["ADMIN"] },
  { to: "/settings", label: "Settings", roles: ["ADMIN", "TEACHER", "STUDENT"] },
  { to: "/issues", label: "Issues", roles: ["ADMIN"] },
];

export default function Sidebar() {
  const { role, logout } = useAuth();
  const navigate = useNavigate();
  const navItems = ALL_NAV.filter((item) => item.roles.includes(role || ""));

  return (
    <motion.aside
      initial={{ x: -16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="glass-panel sticky top-6 flex h-fit w-full shrink-0 flex-col gap-6 rounded-2xl p-5 lg:w-72"
    >
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] opacity-50">Learning</p>
        <h1 className="mt-2 font-display text-2xl font-semibold tracking-tight">Student IQ</h1>
        <p className="mt-2 text-sm opacity-60">
          Role: <span className="font-semibold opacity-100">{role || "Guest"}</span>
        </p>
      </div>

      <nav className="space-y-1.5">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                "block rounded-2xl px-4 py-3 text-sm font-medium transition duration-200",
                isActive
                  ? "bg-[var(--accent)] text-white shadow-lg shadow-sky-500/20"
                  : "opacity-70 hover:bg-[var(--surface-alt)] hover:opacity-100",
              ].join(" ")
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <button
        type="button"
        onClick={() => {
          logout();
          navigate("/login", { replace: true });
        }}
        className="rounded-2xl bg-linear-to-r from-sky-500 to-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-sky-500/25 transition hover:brightness-105"
      >
        Logout
      </button>
    </motion.aside>
  );
}
