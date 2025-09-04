import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import { authService } from './services/api';
import AdminDashboard from './pages/AdminDashboard';
import EmployeeManagement from './pages/EmployeeManagement';

// Protected Route Component
function ProtectedRoute({ children }) {
  const isAuth = authService.isAuthenticated();
  return isAuth ? children : <Navigate to="/login" />;
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route 
          path="/dashboard" 
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } 
        />
        <Route path="/" element={<Navigate to="/dashboard" />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/employees" element={<EmployeeManagement />} />
      </Routes>
    </Router>
  );
}

export default App;
