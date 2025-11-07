// KilometerTab.jsx - Saubere Version
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, subDays, startOfMonth, endOfMonth, subMonths } from 'date-fns';
import { de } from 'date-fns/locale';
// DIESE ICONS FUNKTIONIEREN (aus HistoryTab kopiert)
import { Calendar, Clock, Building, Euro } from 'lucide-react';

const KilometerTab = () => {
  const [kmData, setKmData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateFilter, setDateFilter] = useState('thisMonth');

  const fetchKmData = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      let url = `https://app.seda.de/api/v1/km/my-km`;
      const params = new URLSearchParams();
      
      const now = new Date();
      
      switch(dateFilter) {
        case '7days':
          params.append('date_from', format(subDays(now, 7), 'yyyy-MM-dd'));
          params.append('date_to', format(now, 'yyyy-MM-dd'));
          break;
        case '30days':
          params.append('days', '30');
          break;
        case 'thisMonth':
          params.append('date_from', format(startOfMonth(now), 'yyyy-MM-dd'));
          params.append('date_to', format(endOfMonth(now), 'yyyy-MM-dd'));
          break;
        case 'lastMonth':
          const lastMonth = subMonths(now, 1);
          params.append('date_from', format(startOfMonth(lastMonth), 'yyyy-MM-dd'));
          params.append('date_to', format(endOfMonth(lastMonth), 'yyyy-MM-dd'));
          break;
        case 'all':
          break;
        default:
          params.append('days', '30');
      }
      
      if (params.toString()) {
        url += `?${params.toString()}`;
      }
      
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      setKmData(response.data);
      setError(null);
    } catch (err) {
      setError('Fehler beim Laden der Kilometerdaten'); 
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKmData();
  }, [dateFilter]);

  const formatDate = (date) => {
    if (!date) return '-';
    // Frontend liest YYYY-MM-DD
    return format(new Date(date), 'dd.MM.yyyy', { locale: de });
  };

  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return '0,00 €';
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR'
    }).format(amount);
  };

  // Mobile Card für KM-Daten
  const MobileCard = ({ entry }) => (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-3">
      <div className="flex justify-between items-start mb-2">
        <div>
          <div className="font-semibold text-sm">{formatDate(entry.date)}</div>
          <div className="text-gray-600 text-xs mt-1">{entry.object_name}</div>
        </div>
        <div className="text-right">
          <div className="font-bold text-green-600">{formatCurrency(entry.amount)}</div>
          <div className="text-xs text-gray-500 mt-1">{(entry.distance_km || 0).toFixed(1)} km</div>
        </div>
      </div>
    </div>
  );

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

  // Frontend erwartet jetzt ein Array (basierend auf Backend-Fix)
  const entries = kmData || [];
  const totalKm = entries.reduce((sum, entry) => sum + (parseFloat(entry.distance_km) || 0), 0);
  const totalAmount = entries.reduce((sum, entry) => sum + (parseFloat(entry.amount) || 0), 0);

  return (
    <div className="space-y-6">
      {/* Filter-Bereich */}
      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h3 className="text-lg font-semibold">Kilometer-Historie</h3>
          
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setDateFilter('7days')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                dateFilter === '7days' 
                  ? 'bg-blue-600 text-white shadow-md' 
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Letzte 7 Tage
            </button>
            <button
              onClick={() => setDateFilter('30days')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                dateFilter === '30days' 
                  ? 'bg-blue-600 text-white shadow-md' 
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Letzte 30 Tage
            </button>
            <button
              onClick={() => setDateFilter('thisMonth')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                dateFilter === 'thisMonth' 
                  ? 'bg-blue-600 text-white shadow-md' 
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Dieser Monat
            </button>
            <button
              onClick={() => setDateFilter('lastMonth')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                dateFilter === 'lastMonth' 
                  ? 'bg-blue-600 text-white shadow-md' 
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Letzter Monat
            </button>
            <button
              onClick={() => setDateFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                dateFilter === 'all' 
                  ? 'bg-blue-600 text-white shadow-md' 
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Alle
            </button>
          </div>
        </div>
      </div>

      {/* Zusammenfassung (angepasst für KM) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-blue-50 p-4 rounded-lg">
          <div className="text-sm text-blue-600 font-medium">Zeitraum</div>
          <div className="text-lg font-semibold mt-1">
            {dateFilter === '7days' && 'Letzte 7 Tage'}
            {dateFilter === '30days' && 'Letzte 30 Tage'}
            {dateFilter === 'thisMonth' && format(new Date(), 'MMMM yyyy', { locale: de })}
            {dateFilter === 'lastMonth' && format(subMonths(new Date(), 1), 'MMMM yyyy', { locale: de })}
            {dateFilter === 'all' && 'Gesamte Historie'}
          </div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg">
          <div className="text-sm text-green-600 font-medium">Gesamt KM</div>
          <div className="text-2xl font-bold mt-1">
            {totalKm.toFixed(1)} km
          </div>
        </div>
        <div className="bg-purple-50 p-4 rounded-lg">
          <div className="text-sm text-purple-600 font-medium">Gesamtbetrag</div>
          <div className="text-2xl font-bold mt-1">
            {formatCurrency(totalAmount)}
          </div>
        </div>
      </div>

      {/* MOBILE: Cards (angepasst für KM) */}
      <div className="block md:hidden">
        {entries.length === 0 ? (
          <div className="text-center py-8 text-gray-500 bg-white rounded-lg">
            Keine Einträge im gewählten Zeitraum
          </div>
        ) : (
          entries.map((entry) => (
            <MobileCard key={entry.id} entry={entry} />
          ))
        )}
      </div>

      {/* DESKTOP: Tabelle (angepasst für KM) */}
      <div className="hidden md:block bg-white rounded-lg shadow overflow-hidden">
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
                  KM
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Betrag
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {formatDate(entry.date)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {entry.object_name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {(entry.distance_km || 0).toFixed(1)} km
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold">
                    {formatCurrency(entry.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {entries.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              Keine Einträge im gewählten Zeitraum
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default KilometerTab;