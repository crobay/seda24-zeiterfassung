// HistoryTab.jsx - Erweitert mit Zeitraum-Filtern und Mobile Design
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, subDays, startOfMonth, endOfMonth, subMonths } from 'date-fns';
import { de } from 'date-fns/locale';
import { Calendar, Clock, Building, Euro } from 'lucide-react';

const HistoryTab = () => {
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateFilter, setDateFilter] = useState('30days'); // 30days, 7days, thisMonth, lastMonth, all

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      let url = `https://192.168.178.87:8001/api/v1/reports/my/history`;
      const params = new URLSearchParams();
      
      // Je nach Filter verschiedene Parameter setzen
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
          // Keine Parameter = alle Daten
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
  }, [dateFilter]);

  const formatTime = (datetime) => {
    if (!datetime) return '-';
    return format(new Date(datetime), 'HH:mm', { locale: de });
  };

  const formatDate = (date) => {
    if (!date) return '-';
    return format(new Date(date), 'dd.MM.yyyy', { locale: de });
  };

  const formatCurrency = (amount) => {
    if (!amount) return '0,00 €';
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR'
    }).format(amount);
  };

  // Mobile Card Component
  const MobileCard = ({ entry }) => (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-3">
      <div className="flex justify-between items-start mb-2">
        <div>
          <div className="font-semibold text-sm">{formatDate(entry.date || entry.check_in)}</div>
          <div className="text-gray-600 text-xs mt-1">{entry.object_name}</div>
        </div>
        <span className={`inline-flex px-2 py-1 text-xs rounded-full ${
          entry.service_type === 'Fensterreinigung' ? 'bg-blue-100 text-blue-800' :
          entry.service_type === 'Grundreinigung' ? 'bg-green-100 text-green-800' :
          entry.service_type === 'Unterhaltsreinigung' ? 'bg-yellow-100 text-yellow-800' :
          'bg-gray-100 text-gray-800'
        }`}>
          {entry.service_type || 'Standard'}
        </span>
      </div>
      
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-gray-500">Check-in:</span>
          <span className="ml-1 font-medium">{formatTime(entry.check_in)}</span>
        </div>
        <div>
          <span className="text-gray-500">Check-out:</span>
          <span className="ml-1 font-medium">
            {entry.check_out ? formatTime(entry.check_out) : 
             <span className="text-green-600">Läuft...</span>}
          </span>
        </div>
      </div>
      
      <div className="flex justify-between items-center mt-3 pt-3 border-t">
        <div>
          <span className="text-gray-500 text-xs">Stunden:</span>
          <span className="ml-1 font-bold text-sm">{entry.hours?.toFixed(2) || entry.total_hours?.toFixed(2)} h</span>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-500">{formatCurrency(entry.hourly_rate)}/h</div>
          <div className="font-bold text-green-600">{formatCurrency(entry.amount || (entry.total_hours * entry.hourly_rate))}</div>
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

  // Daten vorbereiten - entweder entries array oder direkt das array
  const entries = history?.entries || history || [];
  const totalHours = entries.reduce((sum, entry) => sum + (entry.hours || entry.total_hours || 0), 0);
  const totalAmount = entries.reduce((sum, entry) => sum + (entry.amount || (entry.total_hours * entry.hourly_rate) || 0), 0);

  return (
    <div className="space-y-6">
      {/* Filter-Bereich mit neuen Buttons */}
      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h3 className="text-lg font-semibold">Arbeitshistorie</h3>
          
          {/* NEUE FILTER BUTTONS */}
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

      {/* Zusammenfassung - Dein schönes Design behalten */}
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
          <div className="text-sm text-green-600 font-medium">Gesamtstunden</div>
          <div className="text-2xl font-bold mt-1">
            {totalHours.toFixed(2)} h
          </div>
        </div>
        <div className="bg-purple-50 p-4 rounded-lg">
          <div className="text-sm text-purple-600 font-medium">Gesamtbetrag</div>
          <div className="text-2xl font-bold mt-1">
            {formatCurrency(totalAmount)}
          </div>
        </div>
      </div>

      {/* MOBILE: Cards für kleine Bildschirme */}
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

      {/* DESKTOP: Deine schöne Tabelle für größere Bildschirme */}
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
              {entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {formatDate(entry.date || entry.check_in)}
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
                    {(entry.hours || entry.total_hours || 0).toFixed(2)} h
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <span className={`inline-flex px-2 py-1 text-xs rounded-full ${
                      entry.service_type === 'Fensterreinigung' ? 'bg-blue-100 text-blue-800' :
                      entry.service_type === 'Grundreinigung' ? 'bg-green-100 text-green-800' :
                      entry.service_type === 'Unterhaltsreinigung' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {entry.service_type || 'Standard'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {formatCurrency(entry.hourly_rate || 15)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold">
                    {formatCurrency(entry.amount || (entry.total_hours * (entry.hourly_rate || 15)))}
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

export default HistoryTab;