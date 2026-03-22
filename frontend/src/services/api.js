import axios from "axios";

/**
 * Backend origin (no path) — default matches local FastAPI: http://localhost:8000
 * JSON API lives at: `${API_ORIGIN}/api/v1`
 */
const API_ORIGIN = String(import.meta.env.VITE_API_ORIGIN || "http://localhost:8000").replace(/\/$/, "");

/** e.g. http://localhost:8000/api/v1 — use VITE_API_URL to override the full base in one shot */
const API_V1_BASE =
  import.meta.env.VITE_API_URL || `${API_ORIGIN}/api/v1`;

const api = axios.create({
  baseURL: API_V1_BASE,
  timeout: 20000,
  headers: {
    Accept: "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("role");
      localStorage.removeItem("userId");
      const path = window.location.pathname || "";
      if (!path.startsWith("/login") && !path.startsWith("/register")) {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

export default api;
export { API_ORIGIN, API_V1_BASE };
