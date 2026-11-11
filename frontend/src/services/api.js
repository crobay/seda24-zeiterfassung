import axios from 'axios';
import { API_URL } from '../config.js';

// Axios-Instanz mit Basis-Config
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token automatisch mitsenden (localStorage oder sessionStorage)
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
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

      localStorage.setItem('userRole', response.data.role || 'mitarbeiter');
    }
    return response.data;
  },
  
  logout: () => {
    localStorage.removeItem('token');
    sessionStorage.removeItem('token');
    localStorage.removeItem('user_email');
    window.location.href = '/login';
  },

  isAuthenticated: () => {
    return !!(localStorage.getItem('token') || sessionStorage.getItem('token'));
  },

  // Token online verlaengern (max. 1x in 12 Std), damit man eingeloggt bleibt.
  // Ohne Netz oder bei Fehler passiert nichts: der vorhandene Token wird NIE verworfen.
  refreshIfDue: async () => {
    const inLocal = !!localStorage.getItem('token');
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    if (!token || !navigator.onLine) return;
    const last = Number(localStorage.getItem('token_refreshed_at') || 0);
    if (Date.now() - last < 12 * 3600 * 1000) return;
    try {
      const res = await api.post('/auth/refresh', {}, { timeout: 10000 });
      if (res.data && res.data.access_token) {
        (inLocal ? localStorage : sessionStorage).setItem('token', res.data.access_token);
        localStorage.setItem('token_refreshed_at', String(Date.now()));
      }
    } catch (e) { /* offline/Timeout/401: Token behalten */ }
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
