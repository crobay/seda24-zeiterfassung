import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus, Trash2, Save, X, Users, Building2, Car, CheckSquare, Square, Euro, Briefcase } from 'lucide-react';

const ROLES = [
  { value: 'mitarbeiter', label: 'Mitarbeiter' },
  { value: 'objektleitung', label: 'Objektleitung' },
  { value: 'hauptkraft', label: 'Hauptkraft' },
  { value: 'nebenkraft', label: 'Nebenkraft' },
];

const MitarbeiterObjekteTab = () => {
  const [assignments, setAssignments] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [objects, setObjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [filterEmployee, setFilterEmployee] = useState('');
  const [filterObject, setFilterObject] = useState('');
  const [message, setMessage] = useState(null);
  const [saving, setSaving] = useState(false);

  // Bulk-Form: Ein Objekt, mehrere MA
  const [bulkObjectId, setBulkObjectId] = useState('');
  const [bulkRole, setBulkRole] = useState('mitarbeiter');
  const [selectedEmployees, setSelectedEmployees] = useState({});
  const [driverEmployees, setDriverEmployees] = useState({});
  const [bulkTrackingCategory, setBulkTrackingCategory] = useState('B');
  const [empSearch, setEmpSearch] = useState('');

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [assignRes, empRes, objRes] = await Promise.all([
        api.get('/admin/assignments').catch(() => ({ data: [] })),
        api.get('/admin/employees-with-categories').catch(() => ({ data: [] })),
        api.get('/admin/objects-list').catch(() => ({ data: [] })),
      ]);
      setAssignments(assignRes.data || []);
      setEmployees(empRes.data || []);
      setObjects(objRes.data || []);
    } catch (e) {
      console.error('Laden fehlgeschlagen:', e);
    }
    setLoading(false);
  };

  const showMsg = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 4000);
  };

  // Welche MA sind schon dem gewaehlten Objekt zugewiesen?
  const alreadyAssigned = bulkObjectId
    ? new Set(assignments.filter(a => a.object_id === parseInt(bulkObjectId)).map(a => a.employee_id))
    : new Set();

  // Gefilterte MA fuer Checkbox-Liste
  const availableEmployees = employees
    .filter(e => e.is_active !== false)
    .filter(e => !alreadyAssigned.has(e.id))
    .filter(e => !empSearch || e.name.toLowerCase().includes(empSearch.toLowerCase()));

  const toggleEmployee = (empId) => {
    setSelectedEmployees(prev => {
      const next = { ...prev };
      if (next[empId]) {
        delete next[empId];
      } else {
        next[empId] = true;
      }
      return next;
    });
  };

  const toggleDriver = (empId) => {
    setDriverEmployees(prev => ({ ...prev, [empId]: !prev[empId] }));
  };

  const selectAll = () => {
    const all = {};
    availableEmployees.forEach(e => { all[e.id] = true; });
    setSelectedEmployees(all);
  };

  const selectNone = () => {
    setSelectedEmployees({});
    setDriverEmployees({});
  };

  const selectedCount = Object.keys(selectedEmployees).length;

  const handleBulkCreate = async () => {
    if (!bulkObjectId) {
      showMsg('Bitte Objekt auswaehlen', 'error');
      return;
    }
    const ids = Object.keys(selectedEmployees).map(Number);
    if (ids.length === 0) {
      showMsg('Bitte mindestens einen Mitarbeiter auswaehlen', 'error');
      return;
    }

    setSaving(true);
    let created = 0;
    let errors = 0;
    for (const empId of ids) {
      try {
        await api.post('/admin/assignments', {
          employee_id: empId,
          object_id: parseInt(bulkObjectId),
          role: bulkRole,
          is_driver: !!driverEmployees[empId],
          tracking_category: bulkTrackingCategory,
        });
        created++;
      } catch (e) {
        errors++;
      }
    }
    setSaving(false);

    if (errors > 0) {
      showMsg(`${created} erstellt, ${errors} fehlgeschlagen`, errors > 0 ? 'error' : 'success');
    } else {
      showMsg(`${created} Zuweisung${created > 1 ? 'en' : ''} erstellt`);
    }

    setShowForm(false);
    setSelectedEmployees({});
    setDriverEmployees({});
    setBulkObjectId('');
    setEmpSearch('');
    loadAll();
  };

  const handleUpdate = async (id, field, value) => {
    try {
      await api.put(`/admin/assignments/${id}`, { [field]: value });
      setAssignments(prev =>
        prev.map(a => a.id === id ? { ...a, [field]: value } : a)
      );
      showMsg('Gespeichert');
    } catch (e) {
      showMsg('Fehler beim Speichern', 'error');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Zuweisung wirklich entfernen?')) return;
    try {
      await api.put(`/admin/assignments/${id}`, { is_active: false });
      setAssignments(prev => prev.filter(a => a.id !== id));
      showMsg('Zuweisung entfernt');
    } catch (e) {
      showMsg('Fehler beim Entfernen', 'error');
    }
  };

  // Filter anwenden
  const filtered = assignments.filter(a => {
    if (filterEmployee && a.employee_id !== parseInt(filterEmployee)) return false;
    if (filterObject && a.object_id !== parseInt(filterObject)) return false;
    return true;
  });

  // Gruppiert nach Objekt
  const groupedByObject = {};
  filtered.forEach(a => {
    if (!groupedByObject[a.object_id]) {
      groupedByObject[a.object_id] = {
        object_name: a.object_name,
        assignments: [],
      };
    }
    groupedByObject[a.object_id].assignments.push(a);
  });

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
        <h2 className="text-xl font-bold">Mitarbeiter-Objekt-Zuweisungen</h2>
        <button
          onClick={() => { setShowForm(!showForm); setSelectedEmployees({}); setDriverEmployees({}); setEmpSearch(''); }}
          className="bg-blue-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 hover:bg-blue-600"
        >
          {showForm ? <X size={18} /> : <Plus size={18} />}
          {showForm ? 'Abbrechen' : 'Zuweisungen erstellen'}
        </button>
      </div>

      {/* Meldung */}
      {message && (
        <div className={`p-3 rounded ${message.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
          {message.text}
        </div>
      )}

      {/* Bulk-Zuweisung Form */}
      {showForm && (
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-blue-500">
          <h3 className="font-bold mb-3">Neue Zuweisungen</h3>

          {/* Objekt + Rolle */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Objekt *</label>
              <select
                value={bulkObjectId}
                onChange={e => { setBulkObjectId(e.target.value); setSelectedEmployees({}); setDriverEmployees({}); }}
                className="w-full border rounded p-2"
              >
                <option value="">-- Objekt waehlen --</option>
                {objects
                  .filter(o => o.is_active !== false)
                  .sort((a, b) => a.name.localeCompare(b.name, 'de'))
                  .map(obj => (
                    <option key={obj.id} value={obj.id}>{obj.name}</option>
                  ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Rolle fuer alle</label>
              <select
                value={bulkRole}
                onChange={e => setBulkRole(e.target.value)}
                className="w-full border rounded p-2"
              >
                {ROLES.map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Tracking-Kategorie */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Tracking-Kategorie</label>
            <select
              value={bulkTrackingCategory}
              onChange={e => setBulkTrackingCategory(e.target.value)}
              className="border rounded p-2"
              style={{ minWidth: '120px' }}
            >
              <option value="B">B - Standard</option>
              <option value="C">C - Stempeluhr</option>
            </select>
          </div>

          {/* MA-Auswahl */}
          {bulkObjectId && (
            <>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700">
                  Mitarbeiter auswaehlen ({selectedCount} gewaehlt)
                </label>
                <div className="flex gap-2">
                  <button onClick={selectAll} className="text-xs text-blue-600 hover:underline">Alle</button>
                  <span className="text-gray-300">|</span>
                  <button onClick={selectNone} className="text-xs text-gray-500 hover:underline">Keine</button>
                </div>
              </div>

              {/* Suche */}
              <input
                type="text"
                value={empSearch}
                onChange={e => setEmpSearch(e.target.value)}
                placeholder="Mitarbeiter suchen..."
                className="w-full border rounded p-2 text-sm mb-2"
              />

              {/* Checkbox-Liste */}
              <div className="border rounded max-h-64 overflow-y-auto divide-y">
                {availableEmployees.length === 0 ? (
                  <div className="p-4 text-center text-gray-500 text-sm">
                    {alreadyAssigned.size > 0
                      ? 'Alle Mitarbeiter sind bereits zugewiesen'
                      : 'Keine Mitarbeiter gefunden'}
                  </div>
                ) : (
                  availableEmployees.map(emp => (
                    <div
                      key={emp.id}
                      className={`flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-blue-50 ${
                        selectedEmployees[emp.id] ? 'bg-blue-50' : ''
                      }`}
                      onClick={() => toggleEmployee(emp.id)}
                    >
                      <div className="flex items-center gap-3">
                        {selectedEmployees[emp.id]
                          ? <CheckSquare size={20} className="text-blue-600" />
                          : <Square size={20} className="text-gray-300" />
                        }
                        <div>
                          <span className="font-medium text-sm">{emp.name}</span>
                          <span className="text-xs text-gray-500 ml-2">({emp.personal_nr})</span>
                          <span className="text-xs text-gray-400 ml-2">Kat. {emp.tracking_mode || 'C'}</span>
                        </div>
                      </div>
                      {selectedEmployees[emp.id] && (
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleDriver(emp.id); }}
                          className={`flex items-center gap-1 text-xs px-2 py-1 rounded ${
                            driverEmployees[emp.id]
                              ? 'bg-blue-100 text-blue-700 border border-blue-300'
                              : 'bg-gray-100 text-gray-400 border border-gray-200'
                          }`}
                          title="KM-Fahrer"
                        >
                          <Car size={12} />
                          Fahrer
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>

              {/* Bereits zugewiesen Info */}
              {alreadyAssigned.size > 0 && (
                <div className="text-xs text-gray-500 mt-1">
                  {alreadyAssigned.size} MA bereits zugewiesen (ausgeblendet)
                </div>
              )}

              {/* Speichern */}
              <button
                onClick={handleBulkCreate}
                disabled={saving || selectedCount === 0}
                className="mt-4 w-full bg-green-500 text-white py-3 rounded-lg flex items-center justify-center gap-2 font-bold hover:bg-green-600 disabled:opacity-50"
              >
                <Save size={18} />
                {saving
                  ? 'Wird gespeichert...'
                  : `${selectedCount} Zuweisung${selectedCount !== 1 ? 'en' : ''} erstellen`
                }
              </button>
            </>
          )}
        </div>
      )}

      {/* Filter */}
      <div className="bg-white rounded-lg shadow p-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="flex items-center gap-2">
            <Users size={18} className="text-gray-400" />
            <select
              value={filterEmployee}
              onChange={e => setFilterEmployee(e.target.value)}
              className="flex-1 border rounded p-2 text-sm"
            >
              <option value="">Alle Mitarbeiter</option>
              {employees.map(emp => (
                <option key={emp.id} value={emp.id}>{emp.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Building2 size={18} className="text-gray-400" />
            <select
              value={filterObject}
              onChange={e => setFilterObject(e.target.value)}
              className="flex-1 border rounded p-2 text-sm"
            >
              <option value="">Alle Objekte</option>
              {[...objects].sort((a, b) => a.name.localeCompare(b.name, 'de')).map(obj => (
                <option key={obj.id} value={obj.id}>{obj.name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Zuweisungen gruppiert nach Objekt */}
      {Object.keys(groupedByObject).length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          <Users size={48} className="mx-auto mb-2 text-gray-300" />
          <p>Keine Zuweisungen vorhanden</p>
          <p className="text-sm mt-1">Erstelle neue Zuweisungen ueber den Button oben</p>
        </div>
      ) : (
        Object.entries(groupedByObject).map(([objId, group]) => (
          <div key={objId} className="bg-white rounded-lg shadow overflow-hidden">
            <div className="bg-gray-50 px-4 py-3 border-b flex items-center gap-2">
              <Building2 size={18} className="text-blue-500" />
              <span className="font-bold">{group.object_name}</span>
              <span className="text-sm text-gray-500">({group.assignments.length} MA)</span>
            </div>
            <div className="divide-y">
              {group.assignments.map(a => (
                <div key={a.id} className="px-4 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-medium">{a.employee_name}</span>
                    <select
                      value={a.role}
                      onChange={e => handleUpdate(a.id, 'role', e.target.value)}
                      className="text-xs border rounded px-2 py-1 bg-white"
                    >
                      {ROLES.map(r => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleUpdate(a.id, 'is_driver', !a.is_driver)}
                      className={`flex items-center gap-1 text-xs px-2 py-1 rounded ${
                        a.is_driver
                          ? 'bg-blue-100 text-blue-700 border border-blue-300'
                          : 'bg-gray-100 text-gray-400 border border-gray-200'
                      }`}
                    >
                      <Car size={14} />
                      {a.is_driver ? 'Fahrer' : 'Kein Fahrer'}
                    </button>
                    <select
                      value={a.tracking_category || 'B'}
                      onChange={e => handleUpdate(a.id, 'tracking_category', e.target.value)}
                      className="text-xs border rounded px-2 py-1"
                      style={{
                        backgroundColor: a.tracking_category === 'C' ? '#fff7ed' : a.tracking_category === 'A' ? '#f0fdf4' : 'white',
                        borderColor: a.tracking_category === 'C' ? '#f97316' : a.tracking_category === 'A' ? '#22c55e' : '#d1d5db',
                        color: a.tracking_category === 'C' ? '#ea580c' : a.tracking_category === 'A' ? '#16a34a' : '#374151',
                        fontWeight: 'bold',
                      }}
                    >
                      <option value="A">Kat A</option>
                      <option value="B">Kat B</option>
                      <option value="C">Kat C</option>
                    </select>
                    <div className="flex items-center gap-1" title="Stundensatz (leer = Standard)">
                      <Euro size={12} className="text-gray-400" />
                      <input
                        type="number"
                        step="0.50"
                        min="0"
                        placeholder="Std."
                        value={a.custom_hourly_rate || ''}
                        onChange={e => handleUpdate(a.id, 'custom_hourly_rate', e.target.value ? parseFloat(e.target.value) : null)}
                        className="text-xs border rounded px-1 py-1 w-16"
                        style={{ backgroundColor: a.custom_hourly_rate ? '#fef3c7' : 'white' }}
                      />
                    </div>
                    <div className="flex items-center gap-1" title="Dienstleistung (leer = Standard)">
                      <Briefcase size={12} className="text-gray-400" />
                      <input
                        type="text"
                        placeholder="DL-Art"
                        value={a.custom_service_type || ''}
                        onBlur={e => handleUpdate(a.id, 'custom_service_type', e.target.value || null)}
                        onChange={e => {
                          setAssignments(prev => prev.map(x => x.id === a.id ? { ...x, custom_service_type: e.target.value } : x));
                        }}
                        className="text-xs border rounded px-1 py-1 w-28"
                        style={{ backgroundColor: a.custom_service_type ? '#fef3c7' : 'white' }}
                      />
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(a.id)}
                    className="text-red-400 hover:text-red-600 p-1"
                    title="Zuweisung entfernen"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      {/* Statistik */}
      <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-500 text-center">
        {assignments.length} Zuweisungen | {new Set(assignments.map(a => a.employee_id)).size} Mitarbeiter | {new Set(assignments.map(a => a.object_id)).size} Objekte
      </div>
    </div>
  );
};

export default MitarbeiterObjekteTab;
