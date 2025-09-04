// HistoryTab.jsx - Neue Komponente für den Historie-Tab
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

const HistoryTab = () => {
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(
        `https://192.168.178.87:8001/api/v1/reports/my/history?days=${days}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      setHistory(response.data);
      setError(null);
    } catch (err) {
      setError('Fehler beim Laden der Historie');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [days]);

  const formatTime = (datetime) => {
    if (!datetime) return '-';
    return format(new Date(datetime), 'HH:mm', { locale: de });
  };

  const formatDate = (date) => {
    return format(new Date(date), 'dd.MM.yyyy', { locale: de });
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR'
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filter-Bereich */}
      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Arbeitshistorie</h3>
          <div className="flex items-center gap-4">
            <label className="text-sm text-gray-600">Zeitraum:</label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="border rounded px-3 py-1 text-sm"
            >
              <option value={7}>Letzte 7 Tage</option>
              <option value={14}>Letzte 14 Tage</option>
              <option value={30}>Letzte 30 Tage</option>
              <option value={60}>Letzte 60 Tage</option>
              <option value={90}>Letzte 90 Tage</option>
            </select>
          </div>
        </div>
      </div>

      {/* Zusammenfassung */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-blue-50 p-4 rounded-lg">
          <div className="text-sm text-blue-600 font-medium">Zeitraum</div>
          <div className="text-lg font-semibold mt-1">
            {history && formatDate(history.period_start)} - {history && formatDate(history.period_end)}
          </div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg">
          <div className="text-sm text-green-600 font-medium">Gesamtstunden</div>
          <div className="text-2xl font-bold mt-1">
            {history?.total_hours.toFixed(2)} h
          </div>
        </div>
        <div className="bg-purple-50 p-4 rounded-lg">
          <div className="text-sm text-purple-600 font-medium">Gesamtbetrag</div>
          <div className="text-2xl font-bold mt-1">
            {history && formatCurrency(history.total_amount)}
          </div>
        </div>
      </div>

      {/* Tabelle */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Datum
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Objekt
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Check-in
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Check-out
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Stunden
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Service
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Stundensatz
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Betrag
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {history?.entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {formatDate(entry.date)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {entry.object_name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {formatTime(entry.check_in)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {entry.check_out ? (
                      formatTime(entry.check_out)
                    ) : (
                      <span className="text-green-600 font-medium">Läuft...</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {entry.hours.toFixed(2)} h
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <span className={`inline-flex px-2 py-1 text-xs rounded-full ${
                      entry.service_type === 'A' ? 'bg-blue-100 text-blue-800' :
                      entry.service_type === 'B' ? 'bg-green-100 text-green-800' :
                      entry.service_type === 'C' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {entry.service_type || '-'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {formatCurrency(entry.hourly_rate)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold">
                    {formatCurrency(entry.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {history?.entries.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              Keine Einträge im gewählten Zeitraum
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HistoryTab;
