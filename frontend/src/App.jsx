import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import ChangePassword from './pages/ChangePassword';
import Dashboard from './pages/Dashboard';
import { authService } from './services/api';
import AdminDashboard from './pages/AdminDashboard';
import EmployeeManagement from './pages/EmployeeManagement';
import MonthlyConfirmation from './pages/MonthlyConfirmation';
import SommerfestPage from './pages/SommerfestPage';
import ResetPasswordPage from './pages/ResetPasswordPage';

// Protected Route Component
function ProtectedRoute({ children }) {
  const isAuth = authService.isAuthenticated();
  return isAuth ? children : <Navigate to="/login" />;
}

// Protected Admin Route (admin + objektleiter)
function ProtectedAdminRoute({ children }) {
  const isAuth = authService.isAuthenticated();
  const role = localStorage.getItem('userRole');
  if (!isAuth) return <Navigate to="/login" />;
  if (role !== 'admin' && role !== 'objektleiter') return <Navigate to="/dashboard" />;
  return children;
}

function App() {
  // Login-Token online verlaengern: beim Start, wenn Netz zurueckkommt und beim Zurueckholen der App
  useEffect(() => {
    const refresh = () => { authService.refreshIfDue(); };
    const onVisible = () => { if (document.visibilityState === 'visible') refresh(); };
    refresh();
    window.addEventListener('online', refresh);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('online', refresh);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />

        {/* ================================================ */}
        {/* FÜGE DIESEN NEUEN BLOCK GENAU HIER EIN           */}
        {/* ================================================ */}
        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <ChangePassword />
            </ProtectedRoute>
          }
        />
        {/* ================================================ */}

        <Route
          path="/monthly-confirmation/:year/:month"
          element={
            <ProtectedRoute>
              <MonthlyConfirmation />
            </ProtectedRoute>
          }
        />
        <Route path="/fest" element={<SommerfestPage />} />
        <Route path="/" element={<Navigate to="/dashboard" />} />
        <Route path="/admin" element={<ProtectedAdminRoute><AdminDashboard /></ProtectedAdminRoute>} />
        <Route path="/employees" element={<EmployeeManagement />} />
      </Routes>
    </Router>
  );
}

export default App;
