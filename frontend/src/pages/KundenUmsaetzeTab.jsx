import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { DollarSign, Save, ChevronLeft, ChevronRight, Building2 } from 'lucide-react';

const MONTH_NAMES = ['', 'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

const KundenUmsaetzeTab = ({ showToast }) => {
  const [objects, setObjects] = useState([]);
  const [revenues, setRevenues] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [year, setYear] = useState(new Date().getFullYear());
  const [editValues, setEditValues] = useState({});
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    loadData();
  }, [year]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [objRes, revRes] = await Promise.all([
        api.get('/admin/objects-list'),
        api.get(`/admin/customer-revenues?year=${year}`),
      ]);
      setObjects(objRes.data || []);

      // Revenues als Map: object_id -> month -> revenue
      const revMap = {};
      (revRes.data || []).forEach(r => {
        if (!revMap[r.object_id]) revMap[r.object_id] = {};
        revMap[r.object_id][r.month] = r.revenue;
      });
      setRevenues(revMap);

      // Edit-Values initialisieren
      const edit = {};
      (objRes.data || []).forEach(obj => {
        for (let m = 1; m <= 12; m++) {
          const key = `${obj.id}_${m}`;
          edit[key] = revMap[obj.id]?.[m] || '';
        }
      });
      setEditValues(edit);
      setHasChanges(false);
    } catch (error) {
      console.error('Fehler:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (objectId, month, value) => {
    const key = `${objectId}_${month}`;
    setEditValues(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const entries = [];
      objects.forEach(obj => {
        for (let m = 1; m <= 12; m++) {
          const key = `${obj.id}_${m}`;
          const val = editValues[key];
          if (val !== '' && val !== undefined) {
            entries.push({
              object_id: obj.id,
              year: year,
              month: m,
              revenue: parseFloat(val) || 0,
            });
          }
        }
      });

      await api.post('/admin/customer-revenues/bulk', { entries });
      showToast(`${entries.length} Umsaetze gespeichert`, 'success');
      setHasChanges(false);
      loadData();
    } catch (error) {
      showToast('Fehler beim Speichern', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Summen berechnen
  const getMonthTotal = (month) => {
    return objects.reduce((sum, obj) => {
      const key = `${obj.id}_${month}`;
      return sum + (parseFloat(editValues[key]) || 0);
    }, 0);
  };

  const getObjectTotal = (objectId) => {
    let sum = 0;
    for (let m = 1; m <= 12; m++) {
      const key = `${objectId}_${m}`;
      sum += parseFloat(editValues[key]) || 0;
    }
    return sum;
  };

  const grandTotal = objects.reduce((sum, obj) => sum + getObjectTotal(obj.id), 0);

  const formatCurrency = (val) => {
    return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold">Kunden-Umsaetze</h2>
          <p className="text-sm text-gray-500">Monatliche Umsaetze pro Objekt erfassen</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
            <button onClick={() => setYear(year - 1)} className="p-1 hover:bg-white rounded">
              <ChevronLeft size={18} />
            </button>
            <span className="font-bold text-lg px-2">{year}</span>
            <button onClick={() => setYear(year + 1)} className="p-1 hover:bg-white rounded">
              <ChevronRight size={18} />
            </button>
          </div>
          {hasChanges && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300 flex items-center gap-2 text-sm font-medium"
            >
              {saving ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
              ) : (
                <Save size={16} />
              )}
              Speichern
            </button>
          )}
        </div>
      </div>

      {/* Gesamt-Summe */}
      <div className="bg-gradient-to-r from-green-500 to-green-600 rounded-lg p-4 text-white">
        <p className="text-sm opacity-80">Gesamtumsatz {year}</p>
        <p className="text-3xl font-bold">{formatCurrency(grandTotal)}</p>
      </div>

      {/* Tabelle */}
      {loading ? (
        <div className="text-center py-8 text-gray-500">Lade...</div>
      ) : objects.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          <Building2 size={48} className="mx-auto mb-4 text-gray-300" />
          <p>Keine Objekte vorhanden</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="px-3 py-2 text-left font-medium text-gray-600 sticky left-0 bg-gray-50 min-w-[150px]">Objekt</th>
                {MONTH_NAMES.slice(1).map((name, i) => (
                  <th key={i} className="px-2 py-2 text-center font-medium text-gray-600 min-w-[90px]">{name.substring(0, 3)}</th>
                ))}
                <th className="px-3 py-2 text-right font-medium text-gray-600 min-w-[100px]">Gesamt</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {objects.map(obj => (
                <tr key={obj.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-800 sticky left-0 bg-white">{obj.name}</td>
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(m => {
                    const key = `${obj.id}_${m}`;
                    return (
                      <td key={m} className="px-1 py-1">
                        <input
                          type="number"
                          step="0.01"
                          value={editValues[key] || ''}
                          onChange={(e) => handleChange(obj.id, m, e.target.value)}
                          className="w-full px-2 py-1 border rounded text-right text-sm focus:ring-1 focus:ring-blue-300 focus:border-blue-300"
                          placeholder="0"
                        />
                      </td>
                    );
                  })}
                  <td className="px-3 py-2 text-right font-bold text-gray-800">
                    {formatCurrency(getObjectTotal(obj.id))}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-gray-50 border-t-2 font-bold">
                <td className="px-3 py-2 sticky left-0 bg-gray-50">Summe</td>
                {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                  <td key={m} className="px-2 py-2 text-right text-sm">
                    {formatCurrency(getMonthTotal(m))}
                  </td>
                ))}
                <td className="px-3 py-2 text-right text-green-600">
                  {formatCurrency(grandTotal)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
};

export default KundenUmsaetzeTab;
