import api from './api';

// Mitarbeiter mit Kategorien holen
export const getEmployeesWithCategories = async () => {
  const response = await api.get('/admin/employees-with-categories');
  return response.data;
};

// Kategorie updaten
export const updateCategory = async (employeeId, trackingMode, gpsRequired) => {
  const response = await api.put('/admin/update-category', {
    employee_id: employeeId,
    tracking_mode: trackingMode,
    gps_required: gpsRequired
  });
  return response.data;
};

// Dashboard Stats
export const getDashboardStats = async () => {
  const response = await api.get('/admin/dashboard/stats');
  return response.data;
};