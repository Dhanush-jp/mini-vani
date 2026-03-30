import { createContext, useContext, useMemo, useState } from "react";
import { normalizeRole } from "../utils/role";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [role, setRole] = useState(() => normalizeRole(localStorage.getItem("role")));
  const [userId, setUserId] = useState(localStorage.getItem("userId"));

  const login = (nextToken, nextRole, nextUserId) => {
    const r = normalizeRole(nextRole);
    localStorage.setItem("token", nextToken);
    localStorage.setItem("role", r);
    localStorage.setItem("userId", String(nextUserId));
    setToken(nextToken);
    setRole(r);
    setUserId(String(nextUserId));
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("userId");
    setToken(null);
    setRole(null);
    setUserId(null);
  };

  const value = useMemo(() => ({ token, role, userId, login, logout, isAuthenticated: !!token }), [token, role, userId]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
