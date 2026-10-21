import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import { CheckCircle, AlertTriangle, ArrowLeft, Calendar, Clock, Building, Euro } from 'lucide-react';
import { API_URL } from '../config.js';

const formatHoursReadable = (hours) => {
  if (!hours || hours <= 0) return "0 Min";
  const h = Math.floor(hours);
  const m = Math.round((hours % 1) * 60);
  if (h === 0) return `${m} Min`;
  if (m === 0) return `${h} Std`;
  return `${h} Std ${m} Min`;
};

const MONATSNAMEN = [
  '', 'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
];

const MonthlyConfirmation = () => {
  const { year, month } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [disputing, setDisputing] = useState(false);
  const [disputeReason, setDisputeReason] = useState('');
  const [message, setMessage] = useState('');

  const token = localStorage.getItem('token') || sessionStorage.getItem('token');

  useEffect(() => {
    fetchMonthData();
  }, [year, month]);

  const fetchMonthData = async () => {
    setLoading(true);
    try {
      const response = await axios.get(
        `${API_URL}/confirmations/my-month/${year}/${month}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setData(response.data);
    } catch (error) {
      console.error('Fehler beim Laden:', error);
    }
    setLoading(false);
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      await axios.post(
        `${API_URL}/confirmations/confirm/${year}/${month}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setMessage('Monat erfolgreich bestaetigt!');
      fetchMonthData();
    } catch (error) {
      setMessage('Fehler beim Bestaetigen');
    }
    setConfirming(false);
  };

  const handleDispute = async () => {
    if (!disputeReason.trim()) {
      setMessage('Bitte Grund angeben');
      return;
    }
    setConfirming(true);
    try {
      await axios.post(
        `${API_URL}/confirmations/dispute/${year}/${month}`,
        { reason: disputeReason },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setMessage('Widerspruch eingereicht');
      setDisputing(false);
      fetchMonthData();
    } catch (error) {
      setMessage('Fehler beim Senden');
    }
    setConfirming(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-gray-50 p-4">
        <p className="text-red-500">Daten konnten nicht geladen werden.</p>
      </div>
    );
  }

  const monatName = MONATSNAMEN[parseInt(month)] || month;
  const isConfirmed = data.confirmation_status === 'confirmed';
  const isDisputed = data.confirmation_status === 'disputed';

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-blue-500 text-white p-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/dashboard')} className="text-white">
            <ArrowLeft size={24} />
          </button>
          <div>
            <h1 className="text-xl font-bold">Monatsbestaetigung</h1>
            <p className="text-blue-100">{monatName} {year}</p>
          </div>
        </div>
      </div>

      {/* Status-Banner */}
      {isConfirmed && (
        <div className="bg-green-50 border-l-4 border-green-500 p-4 m-4 rounded">
          <div className="flex items-center gap-2">
            <CheckCircle className="text-green-500" size={20} />
            <span className="font-semibold text-green-700">
              Bestaetigt am {data.confirmed_at ? new Date(data.confirmed_at).toLocaleDateString('de-DE') : ''}
            </span>
          </div>
        </div>
      )}
      {isDisputed && (
        <div className="bg-orange-50 border-l-4 border-orange-500 p-4 m-4 rounded">
          <div className="flex items-center gap-2">
            <AlertTriangle className="text-orange-500" size={20} />
            <span className="font-semibold text-orange-700">Widerspruch eingereicht</span>
          </div>
        </div>
      )}

      {message && (
        <div className="bg-blue-50 text-blue-700 p-3 m-4 rounded">{message}</div>
      )}

      {/* Zusammenfassung */}
      <div className="grid grid-cols-2 gap-3 p-4">
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <Clock size={24} className="mx-auto text-blue-500 mb-1" />
          <p className="text-2xl font-bold">{formatHoursReadable(data.total_hours)}</p>
          <p className="text-xs text-gray-500">Arbeitsstunden</p>
        </div>
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <Calendar size={24} className="mx-auto text-green-500 mb-1" />
          <p className="text-2xl font-bold">{formatHoursReadable(data.total_vacation_hours)}</p>
          <p className="text-xs text-gray-500">Urlaubsstunden</p>
        </div>
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <Building size={24} className="mx-auto text-purple-500 mb-1" />
          <p className="text-2xl font-bold">{data.total_km}</p>
          <p className="text-xs text-gray-500">Kilometer</p>
        </div>
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <Euro size={24} className="mx-auto text-yellow-500 mb-1" />
          <p className="text-2xl font-bold">{data.total_km_amount.toFixed(2)}</p>
          <p className="text-xs text-gray-500">KM-Betrag</p>
        </div>
      </div>

      {/* Buchungen */}
      <div className="p-4">
        <h2 className="text-lg font-bold mb-3">Buchungen ({data.entries.length})</h2>
        <div className="space-y-2">
          {data.entries.map((entry, idx) => (
            <div key={entry.id || idx} className="bg-white rounded-lg shadow p-3">
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-semibold text-sm">{entry.object_name}</p>
                  <p className="text-xs text-gray-500">{entry.date}</p>
                </div>
                <div className="text-right">
                  <p className="font-bold text-blue-600">{formatHoursReadable(entry.hours)}</p>
                  <p className="text-xs text-gray-500">{entry.service_type}</p>
                </div>
              </div>
              {entry.check_in && entry.check_out && (
                <p className="text-xs text-gray-400 mt-1">
                  {new Date(entry.check_in).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} -
                  {new Date(entry.check_out).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                </p>
              )}
            </div>
          ))}
          {data.entries.length === 0 && (
            <p className="text-gray-500 text-center py-4">Keine Buchungen in diesem Monat</p>
          )}
        </div>
      </div>

      {/* Aktions-Buttons (nur wenn noch nicht bestaetigt) */}
      {!isConfirmed && (
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t p-4 space-y-2">
          {!disputing ? (
            <>
              <button
                onClick={handleConfirm}
                disabled={confirming}
                className="w-full bg-green-500 hover:bg-green-600 text-white py-3 rounded-lg font-bold disabled:opacity-50"
              >
                {confirming ? 'Wird bestaetigt...' : 'Monat bestaetigen'}
              </button>
              <button
                onClick={() => setDisputing(true)}
                className="w-full bg-orange-500 hover:bg-orange-600 text-white py-3 rounded-lg font-bold"
              >
                Widerspruch einlegen
              </button>
            </>
          ) : (
            <div className="space-y-2">
              <textarea
                value={disputeReason}
                onChange={(e) => setDisputeReason(e.target.value)}
                placeholder="Bitte Grund fuer den Widerspruch angeben..."
                className="w-full border rounded-lg p-3"
                rows={3}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => setDisputing(false)}
                  className="flex-1 bg-gray-300 text-gray-700 py-2 rounded-lg"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleDispute}
                  disabled={confirming}
                  className="flex-1 bg-orange-500 text-white py-2 rounded-lg disabled:opacity-50"
                >
                  Absenden
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default MonthlyConfirmation;
