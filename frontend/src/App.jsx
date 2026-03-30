import { useLayoutEffect } from "react";
import { Navigate, Route, BrowserRouter, Routes, useParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AppLayout from "./components/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import StudentDetail from "./pages/StudentDetail";
import Students from "./pages/Students";
import Attendance from "./pages/Attendance";
import Results from "./pages/Results";
import Analytics from "./pages/Analytics";
import ExportPage from "./pages/Export";
import UploadPage from "./pages/UploadPage";
import Settings from "./pages/Settings";
import Issues from "./pages/Issues";
import Subjects from "./pages/Subjects";

function StudentDetailRoute() {
  const { studentId } = useParams();
  return <StudentDetail key={studentId} />;
}

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/students" element={<Students />} />
        <Route path="/students/:studentId" element={<StudentDetailRoute />} />
        <Route path="/attendance" element={<Attendance />} />
        <Route path="/results" element={<Results />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/export" element={<ExportPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/issues" element={<Issues />} />
        <Route path="/subjects" element={<Subjects />} />
      </Route>
      <Route
        path="*"
        element={
          <Navigate to="/dashboard" replace />
        }
      />
    </Routes>
  );
}

export default function App() {
  useLayoutEffect(() => {
    const savedTheme = localStorage.getItem("theme") || "light";
    document.documentElement.classList.toggle("dark", savedTheme === "dark");
  }, []);

  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
