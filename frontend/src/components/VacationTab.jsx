import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Calendar, Send, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

const VacationTab = ({ token }) => {
  const [vacationData, setVacationData] = useState(null);
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState(null);

  const currentYear = new Date().getFullYear();

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (startDate && endDate && endDate >= startDate) {
      calcPreview();
    } else {
      setPreview(null);
    }
  }, [startDate, endDate]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [vacRes, reqRes] = await Promise.all([
        api.get('/vacation/my-vacation'),
        api.get('/vacation/my-requests'),
      ]);
      setVacationData(vacRes.data);
      setRequests(reqRes.data);
    } catch (error) {
      console.error('Fehler beim Laden:', error);
    } finally {
      setLoading(false);
    }
  };

  const calcPreview = async () => {
    setPreviewLoading(true);
    try {
      const res = await api.get(`/vacation/calc-working-days?start_date=${startDate}&end_date=${endDate}`);
      setPreview(res.data);
    } catch (error) {
      console.error('Preview-Fehler:', error);
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!startDate || !endDate) {
      showToast('Bitte Start- und Enddatum angeben', 'error');
      return;
    }
    if (endDate < startDate) {
      showToast('Enddatum muss nach Startdatum liegen', 'error');
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.post('/vacation/request', {
        start_date: startDate,
        end_date: endDate,
      });
      showToast(res.data.message || 'Urlaubsantrag gesendet!', 'success');
      setStartDate('');
      setEndDate('');
      setPreview(null);
      loadData();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Fehler beim Absenden';
      showToast(msg, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending':
        return { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Offen', icon: Clock };
      case 'approved':
        return { bg: 'bg-green-100', text: 'text-green-800', label: 'Genehmigt', icon: CheckCircle };
      case 'rejected':
        return { bg: 'bg-red-100', text: 'text-red-800', label: 'Abgelehnt', icon: XCircle };
      default:
        return { bg: 'bg-gray-100', text: 'text-gray-800', label: status, icon: AlertCircle };
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        <span className="ml-3 text-gray-600">Lade Urlaubsdaten...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4">
      {/* Urlaubskontostand */}
      <div className="bg-white rounded-xl shadow-sm border p-5">
        <h2 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
          <Calendar className="text-blue-500" size={22} />
          Mein Urlaub {currentYear}
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <p className="text-xs text-blue-600 font-medium">Anspruch</p>
            <p className="text-2xl font-bold text-blue-700">{vacationData?.days_entitled || 0}</p>
            <p className="text-xs text-blue-500">Tage</p>
          </div>
          <div className="bg-orange-50 rounded-lg p-3 text-center">
            <p className="text-xs text-orange-600 font-medium">Genommen</p>
            <p className="text-2xl font-bold text-orange-700">{vacationData?.days_taken || 0}</p>
            <p className="text-xs text-orange-500">Tage</p>
          </div>
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <p className="text-xs text-green-600 font-medium">Resturlaub</p>
            <p className="text-2xl font-bold text-green-700">{vacationData?.days_remaining || 0}</p>
            <p className="text-xs text-green-500">Tage</p>
          </div>
          <div className="bg-purple-50 rounded-lg p-3 text-center">
            <p className="text-xs text-purple-600 font-medium">Urlaubssatz</p>
            <p className="text-2xl font-bold text-purple-700">{(vacationData?.vacation_rate || 0).toFixed(0)}</p>
            <p className="text-xs text-purple-500">{'\u20AC'}/Tag</p>
          </div>
        </div>
      </div>

      {/* Urlaubsantrag Formular */}
      <div className="bg-white rounded-xl shadow-sm border p-5">
        <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
          <Send className="text-green-500" size={20} />
          Neuer Urlaubsantrag
        </h3>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Von</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              className="w-full p-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              min={startDate || new Date().toISOString().split('T')[0]}
              className="w-full p-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>

        {/* Vorschau */}
        {previewLoading && (
          <div className="text-sm text-gray-500 mb-3">Berechne...</div>
        )}
        {preview && !previewLoading && (
          <div className={`rounded-lg p-3 mb-4 ${preview.remaining_after >= 0 ? 'bg-blue-50 border border-blue-200' : 'bg-red-50 border border-red-200'}`}>
            <div className="grid grid-cols-3 gap-2 text-center text-sm">
              <div>
                <p className="text-gray-600">Arbeitstage</p>
                <p className="text-lg font-bold">{preview.working_days}</p>
              </div>
              <div>
                <p className="text-gray-600">Resturlaub</p>
                <p className="text-lg font-bold">{preview.remaining}</p>
              </div>
              <div>
                <p className="text-gray-600">Danach</p>
                <p className={`text-lg font-bold ${preview.remaining_after >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {preview.remaining_after}
                </p>
              </div>
            </div>
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={submitting || !startDate || !endDate || (preview && preview.remaining_after < 0)}
          className="w-full py-3 bg-green-500 text-white rounded-lg font-bold hover:bg-green-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
        >
          {submitting ? (
            <>
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              Wird gesendet...
            </>
          ) : (
            <>
              <Send size={18} />
              Urlaubsantrag absenden
            </>
          )}
        </button>
      </div>

      {/* Meine Antraege */}
      <div className="bg-white rounded-xl shadow-sm border p-5">
        <h3 className="text-lg font-bold text-gray-800 mb-4">Meine Antr{'\u00E4'}ge</h3>
        {requests.length === 0 ? (
          <p className="text-gray-500 text-center py-4">Noch keine Urlaubsantr{'\u00E4'}ge</p>
        ) : (
          <div className="space-y-3">
            {requests.map((req) => {
              const badge = getStatusBadge(req.status);
              const Icon = badge.icon;
              return (
                <div key={req.id} className="flex items-center justify-between border rounded-lg p-3">
                  <div className="flex-1">
                    <div className="font-medium text-sm">
                      {formatDate(req.start_date)} - {formatDate(req.end_date)}
                    </div>
                    <div className="text-xs text-gray-500">
                      {req.working_days} Arbeitstage
                    </div>
                  </div>
                  <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${badge.bg} ${badge.text}`}>
                    <Icon size={14} />
                    {badge.label}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-20 left-4 right-4 px-4 py-3 rounded-lg shadow-lg z-50 text-white text-sm font-medium
          ${toast.type === 'success' ? 'bg-green-500' : ''}
          ${toast.type === 'error' ? 'bg-red-500' : ''}
          ${toast.type === 'info' ? 'bg-blue-500' : ''}
        `}>
          {toast.message}
        </div>
      )}
    </div>
  );
};

export default VacationTab;
