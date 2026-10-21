import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { API_URL } from '../config.js';
import axios from 'axios';
import { ArrowLeftRight, XCircle, Clock, Send, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

const REQUEST_TYPES = [
  { value: 'swap', label: 'Schicht tauschen', icon: ArrowLeftRight, color: 'bg-blue-500' },
  { value: 'cancel', label: 'Schicht absagen', icon: XCircle, color: 'bg-red-500' },
  { value: 'change', label: 'Zeit aendern', icon: Clock, color: 'bg-orange-500' },
];

const STATUS_MAP = {
  pending: { label: 'Ausstehend', color: 'bg-yellow-100 text-yellow-700' },
  approved: { label: 'Genehmigt', color: 'bg-green-100 text-green-700' },
  rejected: { label: 'Abgelehnt', color: 'bg-red-100 text-red-700' },
};

const ShiftChangeForm = ({ onClose }) => {
  const [myRequests, setMyRequests] = useState([]);
  const [colleagues, setColleagues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const token = localStorage.getItem('token') || sessionStorage.getItem('token');

  const [form, setForm] = useState({
    request_type: '',
    requested_date: '',
    requested_start: '',
    requested_end: '',
    swap_employee_id: '',
    reason: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [reqRes, empRes] = await Promise.all([
        axios.get(`${API_URL}/time-entries/shift-requests/my`, {
          headers: { Authorization: `Bearer ${token}` }
        }),
        api.get('/admin/employees-with-categories').catch(() => ({ data: [] })),
      ]);
      setMyRequests(reqRes.data || []);
      setColleagues(empRes.data || []);
    } catch (e) {
      console.error('Laden fehlgeschlagen:', e);
    }
    setLoading(false);
  };

  const showMsg = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 4000);
  };

  const handleSubmit = async () => {
    if (!form.request_type) {
      showMsg('Bitte Typ auswaehlen', 'error');
      return;
    }
    if (!form.reason.trim()) {
      showMsg('Bitte Grund angeben', 'error');
      return;
    }

    setSubmitting(true);
    try {
      await axios.post(`${API_URL}/time-entries/shift-requests`, form, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        }
      });
      showMsg('Anfrage gesendet');
      setShowForm(false);
      setForm({
        request_type: '', requested_date: '', requested_start: '',
        requested_end: '', swap_employee_id: '', reason: '',
      });
      loadData();
    } catch (e) {
      showMsg('Fehler beim Senden', 'error');
    }
    setSubmitting(false);
  };

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-bold">Schichtaenderungen</h3>
        <button
          onClick={() => setShowForm(!showForm)}
          className={`px-4 py-2 rounded-lg text-white text-sm font-medium ${
            showForm ? 'bg-gray-500' : 'bg-blue-500 hover:bg-blue-600'
          }`}
        >
          {showForm ? 'Abbrechen' : 'Neue Anfrage'}
        </button>
      </div>

      {/* Meldung */}
      {message && (
        <div className={`p-3 rounded text-sm ${
          message.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
        }`}>
          {message.text}
        </div>
      )}

      {/* Formular */}
      {showForm && (
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-blue-500 space-y-3">
          {/* Typ-Auswahl */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Art der Aenderung</label>
            <div className="grid grid-cols-3 gap-2">
              {REQUEST_TYPES.map(t => {
                const Icon = t.icon;
                const selected = form.request_type === t.value;
                return (
                  <button
                    key={t.value}
                    onClick={() => setForm(f => ({ ...f, request_type: t.value }))}
                    className={`p-3 rounded-lg border-2 text-center transition ${
                      selected
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <Icon size={20} className={`mx-auto mb-1 ${selected ? 'text-blue-600' : 'text-gray-400'}`} />
                    <div className={`text-xs font-medium ${selected ? 'text-blue-700' : 'text-gray-600'}`}>
                      {t.label}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Datum */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Datum</label>
            <input
              type="date"
              value={form.requested_date}
              onChange={e => setForm(f => ({ ...f, requested_date: e.target.value }))}
              className="w-full border rounded p-2 text-sm"
            />
          </div>

          {/* Zeitaenderung */}
          {form.request_type === 'change' && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Neue Startzeit</label>
                <input
                  type="time"
                  value={form.requested_start}
                  onChange={e => setForm(f => ({ ...f, requested_start: e.target.value }))}
                  className="w-full border rounded p-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Neue Endzeit</label>
                <input
                  type="time"
                  value={form.requested_end}
                  onChange={e => setForm(f => ({ ...f, requested_end: e.target.value }))}
                  className="w-full border rounded p-2 text-sm"
                />
              </div>
            </div>
          )}

          {/* Tauschpartner */}
          {form.request_type === 'swap' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tausch mit Kollege</label>
              <select
                value={form.swap_employee_id}
                onChange={e => setForm(f => ({ ...f, swap_employee_id: e.target.value }))}
                className="w-full border rounded p-2 text-sm"
              >
                <option value="">-- Kollege waehlen --</option>
                {colleagues.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Grund */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Grund *</label>
            <textarea
              value={form.reason}
              onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
              placeholder="Bitte Grund fuer die Aenderung angeben..."
              className="w-full border rounded p-2 text-sm"
              rows={3}
            />
          </div>

          {/* Absenden */}
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full bg-blue-500 hover:bg-blue-600 text-white py-3 rounded-lg font-medium flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {submitting ? (
              <><Loader2 size={18} className="animate-spin" /> Wird gesendet...</>
            ) : (
              <><Send size={18} /> Anfrage absenden</>
            )}
          </button>
        </div>
      )}

      {/* Bisherige Anfragen */}
      <div>
        <h4 className="text-sm font-bold text-gray-600 mb-2">Meine Anfragen</h4>
        {myRequests.length === 0 ? (
          <div className="bg-gray-50 rounded-lg p-6 text-center text-gray-500 text-sm">
            Keine Anfragen vorhanden
          </div>
        ) : (
          <div className="space-y-2">
            {myRequests.map(req => {
              const typeInfo = REQUEST_TYPES.find(t => t.value === req.request_type) || REQUEST_TYPES[2];
              const TypeIcon = typeInfo.icon;
              const statusInfo = STATUS_MAP[req.status] || STATUS_MAP.pending;
              return (
                <div key={req.id} className="bg-white rounded-lg shadow-sm border p-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <TypeIcon size={16} className="text-gray-500" />
                      <span className="font-medium text-sm">{typeInfo.label}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${statusInfo.color}`}>
                        {statusInfo.label}
                      </span>
                    </div>
                    <span className="text-xs text-gray-400">
                      {req.created_at ? new Date(req.created_at).toLocaleDateString('de-DE') : ''}
                    </span>
                  </div>
                  {req.requested_date && (
                    <div className="text-xs text-gray-600 mt-1">
                      Datum: {new Date(req.requested_date).toLocaleDateString('de-DE')}
                      {req.requested_start && ` | ${req.requested_start} - ${req.requested_end}`}
                    </div>
                  )}
                  {req.swap_employee_name && (
                    <div className="text-xs text-gray-600 mt-1">
                      Tausch mit: {req.swap_employee_name}
                    </div>
                  )}
                  {req.reason && (
                    <div className="text-xs text-gray-500 mt-1">Grund: {req.reason}</div>
                  )}
                  {req.admin_response && (
                    <div className="text-xs text-blue-600 mt-1 bg-blue-50 p-1.5 rounded">
                      Admin: {req.admin_response}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ShiftChangeForm;
