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
        <Route path="/export" element={<ExportPage />} />
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
