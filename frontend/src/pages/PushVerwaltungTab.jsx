import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Smartphone, WifiOff, RefreshCw, Search, CheckCircle, XCircle, Info } from 'lucide-react';

const PushVerwaltungTab = () => {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterMode, setFilterMode] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  useEffect(() => {
    loadEmployees();
  }, []);

  const loadEmployees = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/push-settings');
      setEmployees(res.data || []);
    } catch (e) {
      console.error('Laden fehlgeschlagen:', e);
    }
    setLoading(false);
  };

  const filtered = employees.filter(e => {
    if (search && !e.name.toLowerCase().includes(search.toLowerCase()) &&
        !e.personal_nr?.toLowerCase().includes(search.toLowerCase())) return false;
    if (filterMode && e.tracking_mode !== filterMode) return false;
    if (filterStatus === 'connected' && !e.telegram_chat_id) return false;
    if (filterStatus === 'not_connected' && e.telegram_chat_id) return false;
    return true;
  });

  const connected = employees.filter(e => e.telegram_chat_id).length;
  const notConnected = employees.filter(e => !e.telegram_chat_id).length;
  const katBNotConnected = employees.filter(e => e.tracking_mode === 'B' && !e.telegram_chat_id).length;

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">Telegram-Verwaltung</h2>
        <button
          onClick={loadEmployees}
          className="text-gray-500 hover:text-blue-500"
        >
          <RefreshCw size={20} />
        </button>
      </div>

      {/* Statistik-Karten */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-green-50 rounded-lg p-3 text-center">
          <CheckCircle size={24} className="mx-auto text-green-500 mb-1" />
          <div className="text-2xl font-bold text-green-700">{connected}</div>
          <div className="text-xs text-green-600">Verbunden</div>
        </div>
        <div className="bg-red-50 rounded-lg p-3 text-center">
          <XCircle size={24} className="mx-auto text-red-400 mb-1" />
          <div className="text-2xl font-bold text-red-600">{notConnected}</div>
          <div className="text-xs text-red-500">Nicht verbunden</div>
        </div>
        <div className="bg-blue-50 rounded-lg p-3 text-center">
          <Smartphone size={24} className="mx-auto text-blue-500 mb-1" />
          <div className="text-2xl font-bold text-blue-700">{employees.length}</div>
          <div className="text-xs text-blue-600">Gesamt</div>
        </div>
      </div>

      {/* Warnung wenn Kat-B MAs nicht verbunden */}
      {katBNotConnected > 0 && (
        <div className="bg-orange-50 border-l-4 border-orange-500 p-3 rounded">
          <p className="text-sm text-orange-700 font-medium">
            {katBNotConnected} Kat-B Mitarbeiter ohne Telegram-Verbindung!
          </p>
          <p className="text-xs text-orange-600 mt-1">
            Diese MA erhalten keine Schichtbestaetigungen per Telegram.
          </p>
        </div>
      )}

      {/* Filter */}
      <div className="bg-white rounded-lg shadow p-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="relative">
            <Search size={18} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Mitarbeiter suchen..."
              className="w-full border rounded p-2 pl-10 text-sm"
            />
          </div>
          <select
            value={filterMode}
            onChange={e => setFilterMode(e.target.value)}
            className="border rounded p-2 text-sm"
          >
            <option value="">Alle Kategorien</option>
            <option value="A">Kat. A (Automatik)</option>
            <option value="B">Kat. B (Push-Bestaetigung)</option>
            <option value="C">Kat. C (Stempeluhr)</option>
          </select>
          <select
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)}
            className="border rounded p-2 text-sm"
          >
            <option value="">Alle Status</option>
            <option value="connected">Verbunden</option>
            <option value="not_connected">Nicht verbunden</option>
          </select>
        </div>
      </div>

      {/* Mitarbeiter-Liste */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="divide-y">
          {filtered.map(emp => {
            const isConnected = !!emp.telegram_chat_id;
            return (
              <div key={emp.id} className="px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`p-2 rounded-full ${isConnected ? 'bg-green-100' : 'bg-gray-100'}`}>
                    {isConnected
                      ? <CheckCircle size={18} className="text-green-500" />
                      : <WifiOff size={18} className="text-gray-400" />
                    }
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium truncate">{emp.name}</div>
                    <div className="text-xs text-gray-500">
                      {emp.personal_nr} | Kat. {emp.tracking_mode}
                      {emp.email && ` | ${emp.email}`}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  {isConnected ? (
                    <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                      Verbunden
                    </span>
                  ) : (
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-1 rounded-full">
                      Nicht verbunden
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {filtered.length === 0 && (
        <div className="text-center text-gray-500 py-8">
          Keine Mitarbeiter gefunden
        </div>
      )}

      {/* Info-Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700">
        <Info size={18} className="inline mr-2" />
        <strong>Telegram-Bot Anleitung:</strong>
        <ul className="mt-2 space-y-1 ml-6 list-disc">
          <li>Mitarbeiter oeffnet Telegram und sucht nach dem SEDA24-Bot</li>
          <li>Sendet <code className="bg-blue-100 px-1 rounded">/start PERSONALNUMMER</code> (z.B. /start D0001)</li>
          <li>Bot verknuepft automatisch das Telegram-Konto</li>
          <li>Kat-B MAs erhalten Schichtbestaetigungen per Telegram</li>
          <li>Alle MAs erhalten Monatsbestaetigungen</li>
        </ul>
      </div>
    </div>
  );
};

export default PushVerwaltungTab;
