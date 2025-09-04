import axios from 'axios';

// Backend läuft auf Port 8001!
const API_URL = 'https://192.168.178.87:8001/api/v1';

// Axios-Instanz mit Basis-Config
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token automatisch mitsenden
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// API-Funktionen
export const authService = {
  login: async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    if (response.data.access_token) {
      localStorage.setItem('token', response.data.access_token);
      localStorage.setItem('user_email', email);

// NEUE ZEILEN HIER EINFÜGEN:
if (email === 'admin@seda24.de') {
  localStorage.setItem('userRole', 'admin');
} else {
  localStorage.setItem('userRole', 'mitarbeiter');
}
    }
    return response.data;
  },
  
  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user_email');
    window.location.href = '/login';
  },
  
  isAuthenticated: () => {
    return !!localStorage.getItem('token');
  }
};

export const timeService = {
  checkIn: async (objectId, notes = '') => {
    return await api.post('/time-entries/check-in', {
      object_id: objectId,
      notes: notes
    });
  },
  
  checkOut: async () => {
    return await api.post('/time-entries/check-out', {});
  },
  
  getCurrentStatus: async () => {
    return await api.get('/time-entries/current');
  },
  
  switchObject: async (objectId, notes = '') => {
    return await api.post('/time-entries/switch-object', {
      object_id: objectId,
      notes: notes
    });
  }
};

export const reportService = {
  getToday: async () => {
    return await api.get('/reports/my/today');
  },
  
  getWeek: async () => {
    return await api.get('/reports/my/week');
  },
  
  getMonth: async () => {
    return await api.get('/reports/my/month');
  }
};

export default api;
