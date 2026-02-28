import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { TrendingUp, Edit2, X, Save, Trash2 } from 'lucide-react';

const KmJournalTab = ({ employees, customers, showToast }) => {
  const [kmEntries, setKmEntries] = useState([]);
  const [filteredEntries, setFilteredEntries] = useState([]);
  const [selectedEmployee, setSelectedEmployee] = useState('all');
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0);

  const [dateFrom, setDateFrom] = useState(
    `${firstDay.getFullYear()}-${String(firstDay.getMonth() + 1).padStart(2, '0')}-01`
  );
  const [dateTo, setDateTo] = useState(
    `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`
  );
  const [selectedObject, setSelectedObject] = useState('all');
  const [editModal, setEditModal] = useState(false);
  const [editEntry, setEditEntry] = useState(null);
  const [editKm, setEditKm] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => { loadKmEntries(); }, []);
  useEffect(() => { applyFilters(); }, [kmEntries, dateFrom, dateTo, selectedEmployee, selectedObject]);

  const loadKmEntries = async () => {
    try {
      const response = await api.get("/admin/km-journal/all");
      setKmEntries(response.data);
    } catch (error) {
      console.error("KM Load Error:", error);
      showToast("Fehler beim Laden", "error");
    }
  };

  const applyFilters = () => {
    let filtered = [...kmEntries];
    if (dateFrom) filtered = filtered.filter(e => new Date(e.date) >= new Date(dateFrom));
    if (dateTo) filtered = filtered.filter(e => new Date(e.date) <= new Date(dateTo));
    if (selectedEmployee !== 'all') filtered = filtered.filter(e => e.employee_id === parseInt(selectedEmployee));
    if (selectedObject !== 'all') filtered = filtered.filter(e => e.object_id === parseInt(selectedObject));
    setFilteredEntries(filtered);
  };

  const openEditModal = (entry) => {
    setEditEntry(entry);
    setEditKm(entry.distance_km);
    setEditModal(true);
  };

  const closeEditModal = () => {
    setEditModal(false);
    setEditEntry(null);
    setEditKm('');
  };

  const saveEdit = async () => {
    try {
      const url = '/admin/km-journal/' + editEntry.id + '?distance_km=' + parseFloat(editKm);
      await api.put(url);
      showToast("KM erfolgreich aktualisiert", "success");
      closeEditModal();
      loadKmEntries();
    } catch (error) {
      console.error("Edit Error:", error);
      showToast("Fehler beim Speichern", "error");
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredEntries.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredEntries.map(e => e.id)));
    }
  };

  const bulkDelete = async () => {
    try {
      await api.post("/admin/km-journal/bulk-delete", { ids: Array.from(selectedIds) });
      showToast(`${selectedIds.size} Einträge gelöscht`, "success");
      setSelectedIds(new Set());
      setShowDeleteConfirm(false);
      loadKmEntries();
    } catch (error) {
      console.error("Bulk Delete Error:", error);
      showToast("Fehler beim Löschen", "error");
    }
  };

  const totalKm = filteredEntries.reduce((sum, e) => sum + parseFloat(e.distance_km || 0), 0);
  const totalAmount = filteredEntries.reduce((sum, e) => sum + parseFloat(e.amount || 0), 0);

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-orange-500 to-red-600 rounded-lg shadow p-6 text-white">
        <h2 className="text-2xl font-bold">KM-Journal</h2>
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-600">Gesamt KM</p>
          <p className="text-2xl font-bold text-blue-600">{totalKm.toFixed(1)} km</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-600">Betrag</p>
          <p className="text-2xl font-bold text-orange-600">{totalAmount.toFixed(2)} Euro</p>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="font-bold text-lg mb-4">Filter</h3>
        <div className="grid grid-cols-4 gap-4">
          <div>
            <label className="block text-sm mb-1">Von</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full p-2 border rounded" />
          </div>
          <div>
            <label className="block text-sm mb-1">Bis</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full p-2 border rounded" />
          </div>
          <div>
            <label className="block text-sm mb-1">MA</label>
            <select value={selectedEmployee} onChange={(e) => setSelectedEmployee(e.target.value)} className="w-full p-2 border rounded">
              <option value="all">Alle</option>
              {Array.isArray(employees) && employees.length > 0 && employees.map(emp => <option key={emp.id} value={emp.id}>{emp.first_name} {emp.last_name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1">Objekt</label>
            <select value={selectedObject} onChange={(e) => setSelectedObject(e.target.value)} className="w-full p-2 border rounded">
              <option value="all">Alle</option>
              {Array.isArray(customers) && customers.length > 0 && customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
          <span className="text-red-700 font-medium">{selectedIds.size} Einträge ausgewählt</span>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 transition"
          >
            <Trash2 size={16} />
            Ausgewählte löschen
          </button>
        </div>
      )}

      <div className="bg-white rounded-lg shadow overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-3 text-center w-10">
                <input
                  type="checkbox"
                  checked={filteredEntries.length > 0 && selectedIds.size === filteredEntries.length}
                  onChange={toggleSelectAll}
                  className="w-4 h-4 rounded"
                />
              </th>
              <th className="px-4 py-3 text-left text-sm">Datum</th>
              <th className="px-4 py-3 text-left text-sm">MA</th>
              <th className="px-4 py-3 text-left text-sm">Objekt</th>
              <th className="px-4 py-3 text-right text-sm">KM</th>
              <th className="px-4 py-3 text-right text-sm">Betrag</th>
              <th className="px-4 py-3 text-center text-sm">Aktionen</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {filteredEntries.map(entry => (
              <tr key={entry.id} className={`hover:bg-gray-50 ${selectedIds.has(entry.id) ? 'bg-red-50' : ''}`}>
                <td className="px-3 py-3 text-center">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(entry.id)}
                    onChange={() => toggleSelect(entry.id)}
                    className="w-4 h-4 rounded"
                  />
                </td>
                <td className="px-4 py-3 text-sm">{new Date(entry.date).toLocaleDateString('de-DE')}</td>
                <td className="px-4 py-3 text-sm">{entry.employee_name}</td>
                <td className="px-4 py-3 text-sm">{entry.object_name}</td>
                <td className="px-4 py-3 text-sm text-right">{entry.distance_km} km</td>
                <td className="px-4 py-3 text-sm text-right">{entry.amount && entry.amount.toFixed(2)} Euro</td>
                <td className="px-4 py-3 text-center">
                  <button
                    onClick={() => openEditModal(entry)}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 transition"
                  >
                    <Edit2 size={14} />
                    <span className="text-xs">Bearbeiten</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredEntries.length === 0 && <div className="text-center py-8 text-gray-500">Keine Eintraege</div>}
      </div>

      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-96">
            <h3 className="text-xl font-bold text-red-600 mb-4">Einträge löschen?</h3>
            <p className="text-gray-700 mb-6">
              Sollen wirklich <strong>{selectedIds.size} Einträge</strong> unwiderruflich gelöscht werden?
            </p>
            <div className="flex gap-3">
              <button
                onClick={bulkDelete}
                className="flex-1 flex items-center justify-center gap-2 bg-red-500 text-white py-2 px-4 rounded hover:bg-red-600 transition"
              >
                <Trash2 size={18} />
                Ja, löschen
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 bg-gray-300 text-gray-700 py-2 px-4 rounded hover:bg-gray-400 transition"
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}

      {editModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-96">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold">KM bearbeiten</h3>
              <button onClick={closeEditModal} className="text-gray-500 hover:text-gray-700">
                <X size={24} />
              </button>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Mitarbeiter</label>
                <input type="text" value={editEntry?.employee_name || ''} disabled className="w-full p-2 border rounded bg-gray-50" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Objekt</label>
                <input type="text" value={editEntry?.object_name || ''} disabled className="w-full p-2 border rounded bg-gray-50" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Datum</label>
                <input type="text" value={editEntry ? new Date(editEntry.date).toLocaleDateString('de-DE') : ''} disabled className="w-full p-2 border rounded bg-gray-50" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Kilometer *</label>
                <input
                  type="number"
                  step="0.1"
                  value={editKm}
                  onChange={(e) => setEditKm(e.target.value)}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                  autoFocus
                />
              </div>
              <div className="bg-blue-50 p-3 rounded">
                <p className="text-sm text-gray-600">Neuer Betrag:</p>
                <p className="text-lg font-bold text-blue-600">{(parseFloat(editKm || 0) * 0.30).toFixed(2)} €</p>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={saveEdit}
                className="flex-1 flex items-center justify-center gap-2 bg-green-500 text-white py-2 px-4 rounded hover:bg-green-600 transition"
              >
                <Save size={18} />
                Speichern
              </button>
              <button
                onClick={closeEditModal}
                className="flex-1 bg-gray-300 text-gray-700 py-2 px-4 rounded hover:bg-gray-400 transition"
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KmJournalTab;
