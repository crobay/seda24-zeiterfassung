import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Calendar, Plus, Trash2, Save, Play, X, Clock, Car, AlertCircle, Repeat } from 'lucide-react';

const WEEKDAYS = [
  { value: 0, label: 'Montag', short: 'Mo' },
  { value: 1, label: 'Dienstag', short: 'Di' },
  { value: 2, label: 'Mittwoch', short: 'Mi' },
  { value: 3, label: 'Donnerstag', short: 'Do' },
  { value: 4, label: 'Freitag', short: 'Fr' },
  { value: 5, label: 'Samstag', short: 'Sa' },
  { value: 6, label: 'Sonntag', short: 'So' },
];

const RHYTHMS = [
  { value: 'weekly', label: 'Woechentlich', short: 'Woe.', color: 'bg-blue-100 text-blue-800' },
  { value: 'biweekly_even', label: '14-taegig (gerade KW)', short: '14T ger.', color: 'bg-green-100 text-green-800' },
  { value: 'biweekly_odd', label: '14-taegig (ungerade KW)', short: '14T ung.', color: 'bg-orange-100 text-orange-800' },
  { value: 'monthly', label: 'Monatlich', short: 'Mtl.', color: 'bg-purple-100 text-purple-800' },
];

const MONTH_WEEKS = [
  { value: 1, label: '1. im Monat' },
  { value: 2, label: '2. im Monat' },
  { value: 3, label: '3. im Monat' },
  { value: 4, label: '4. im Monat' },
  { value: -1, label: 'Letzter im Monat' },
];

const StammDienstplanTab = ({ employees = [], showToast }) => {
  const [entries, setEntries] = useState([]);
  const [objects, setObjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [filterEmployee, setFilterEmployee] = useState('');
  const [filterObject, setFilterObject] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generateResult, setGenerateResult] = useState(null);

  // Add-Form
  const [form, setForm] = useState({
    employee_id: '',
    object_id: '',
    weekdays: [],
    start_time: '06:00',
    end_time: '09:00',
    is_driver: false,
    rhythm: 'weekly',
    month_week: 1,
  });

  // Generate-Form
  const [genForm, setGenForm] = useState({
    month: new Date().getMonth() + 1,
    year: new Date().getFullYear(),
    overwrite: false,
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [entriesRes, objectsRes] = await Promise.all([
        api.get('/admin/master-schedule'),
        api.get('/admin/objects-list'),
      ]);
      setEntries(entriesRes.data);
      setObjects(objectsRes.data || []);
    } catch (error) {
      console.error('Fehler:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!form.employee_id || !form.object_id || form.weekdays.length === 0) {
      showToast('Bitte alle Pflichtfelder ausfuellen', 'error');
      return;
    }
    try {
      const res = await api.post('/admin/master-schedule', {
        employee_id: parseInt(form.employee_id),
        object_id: parseInt(form.object_id),
        weekdays: form.weekdays.map(Number),
        start_time: form.start_time,
        end_time: form.end_time,
        is_driver: form.is_driver,
        rhythm: form.rhythm,
        month_week: form.rhythm === 'monthly' ? form.month_week : null,
      });
      const msg = `${res.data.created} Eintrag/e erstellt${res.data.skipped > 0 ? `, ${res.data.skipped} uebersprungen` : ''}`;
      showToast(msg, 'success');
      setShowAddModal(false);
      setForm({ employee_id: '', object_id: '', weekdays: [], start_time: '06:00', end_time: '09:00', is_driver: false, rhythm: 'weekly', month_week: 1 });
      loadData();
    } catch (error) {
      showToast(error.response?.data?.detail || 'Fehler beim Erstellen', 'error');
    }
  };

  // Auto-Load: Standard-Zeiten laden wenn Objekt oder Wochentag sich ändert
  useEffect(() => {
    const loadStdTimes = async () => {
      if (!form.object_id) return;
      try {
        const res = await api.get(`/admin/objects/${form.object_id}/standard-times`);
        const stdTimes = res.data;
        if (stdTimes && stdTimes.length > 0) {
          // Wenn Wochentage gewählt: Match suchen
          if (form.weekdays.length > 0) {
            const match = stdTimes.find(t => form.weekdays.includes(t.weekday));
            if (match) {
              setForm(f => ({ ...f, start_time: match.start_time || f.start_time, end_time: match.end_time || f.end_time }));
              return;
            }
          }
          // Kein Wochentag-Match → ersten Eintrag nehmen
          setForm(f => ({ ...f, start_time: stdTimes[0].start_time || f.start_time, end_time: stdTimes[0].end_time || f.end_time }));
          return;
        }
      } catch (e) {
        // API-Fehler → weiter zu Objekt-Fallback
      }
      // Fallback: Object.start_time / end_time aus lokaler Liste
      const obj = objects.find(o => String(o.id) === String(form.object_id));
      if (obj?.start_time) {
        const st = typeof obj.start_time === 'string' ? obj.start_time.substring(0, 5) : obj.start_time;
        const et = obj.end_time ? (typeof obj.end_time === 'string' ? obj.end_time.substring(0, 5) : obj.end_time) : '14:00';
        setForm(f => ({ ...f, start_time: st, end_time: et }));
      }
    };
    loadStdTimes();
  }, [form.object_id, form.weekdays.length, objects]);

  const toggleWeekday = (wd) => {
    setForm(f => ({
      ...f,
      weekdays: f.weekdays.includes(wd)
        ? f.weekdays.filter(w => w !== wd)
        : [...f.weekdays, wd].sort((a, b) => a - b),
    }));
  };

  const selectWeekdayPreset = (preset) => {
    if (preset === 'mo-fr') setForm(f => ({ ...f, weekdays: [0, 1, 2, 3, 4] }));
    else if (preset === 'mo-sa') setForm(f => ({ ...f, weekdays: [0, 1, 2, 3, 4, 5] }));
    else if (preset === 'all') setForm(f => ({ ...f, weekdays: [0, 1, 2, 3, 4, 5, 6] }));
    else setForm(f => ({ ...f, weekdays: [] }));
  };

  const handleDelete = async (id) => {
    if (!confirm('Eintrag wirklich loeschen?')) return;
    try {
      await api.delete(`/admin/master-schedule/${id}`);
      showToast('Eintrag geloescht', 'success');
      loadData();
    } catch (error) {
      showToast('Fehler beim Loeschen', 'error');
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setGenerateResult(null);
    try {
      const res = await api.post('/admin/master-schedule/generate', {
        month: genForm.month,
        year: genForm.year,
        overwrite: genForm.overwrite,
      });
      setGenerateResult(res.data);
      showToast(res.data.message, 'success');
    } catch (error) {
      showToast(error.response?.data?.detail || 'Fehler beim Generieren', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const getRhythmBadge = (rhythm) => {
    const r = RHYTHMS.find(x => x.value === rhythm) || RHYTHMS[0];
    return r;
  };

  // Eintraege nach Mitarbeiter gruppieren
  const filtered = entries.filter(e => {
    if (filterEmployee && e.employee_id != filterEmployee) return false;
    if (filterObject && e.object_id != filterObject) return false;
    return true;
  });

  const grouped = {};
  filtered.forEach(e => {
    const key = `${e.employee_id}`;
    if (!grouped[key]) {
      grouped[key] = { employee_name: e.employee_name, personal_nr: e.personal_nr, entries: [] };
    }
    grouped[key].entries.push(e);
  });

  const MONTH_NAMES = ['', 'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

  // Wochentag-Label fuer monatlich
  const getMonthWeekLabel = (entry) => {
    if (entry.rhythm !== 'monthly') return '';
    const mw = MONTH_WEEKS.find(x => x.value === entry.month_week);
    const wd = WEEKDAYS.find(x => x.value === entry.weekday);
    return mw && wd ? `${mw.label.replace(' im Monat', '')} ${wd.label}` : '';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold">Stamm-Dienstplan</h2>
          <p className="text-sm text-gray-500">{entries.length} Eintraege gesamt</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowGenerateModal(true)}
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2 text-sm font-medium"
          >
            <Play size={16} /> Monat generieren
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2 text-sm font-medium"
          >
            <Plus size={16} /> Neuer Eintrag
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="flex gap-4 flex-wrap">
        <select
          value={filterEmployee}
          onChange={(e) => setFilterEmployee(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          <option value="">Alle Mitarbeiter</option>
          {employees.map(emp => (
            <option key={emp.id} value={emp.id}>{emp.name || `${emp.first_name} ${emp.last_name}`}</option>
          ))}
        </select>
        <select
          value={filterObject}
          onChange={(e) => setFilterObject(e.target.value)}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          <option value="">Alle Objekte</option>
          {objects.map(obj => (
            <option key={obj.id} value={obj.id}>{obj.name}</option>
          ))}
        </select>
      </div>

      {/* Tabelle pro MA */}
      {loading ? (
        <div className="text-center py-8 text-gray-500">Lade...</div>
      ) : Object.keys(grouped).length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          <Calendar size={48} className="mx-auto mb-4 text-gray-300" />
          <p className="text-lg font-medium">Noch keine Stamm-Eintraege</p>
          <p className="text-sm mt-2">Erstelle Eintraege und generiere dann den Monatsplan</p>
        </div>
      ) : (
        <div className="space-y-4">
          {Object.entries(grouped).map(([empId, group]) => (
            <div key={empId} className="bg-white rounded-lg shadow overflow-hidden">
              <div className="bg-gray-50 px-4 py-3 border-b flex items-center justify-between">
                <div>
                  <span className="font-bold text-gray-800">{group.employee_name}</span>
                  <span className="text-xs text-gray-400 ml-2">{group.personal_nr}</span>
                </div>
                <span className="text-xs text-gray-500">{group.entries.length} Eintraege</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-gray-600">
                      <th className="px-4 py-2 text-left">Wochentag</th>
                      <th className="px-4 py-2 text-left">Objekt</th>
                      <th className="px-4 py-2 text-center">Rhythmus</th>
                      <th className="px-4 py-2 text-center">Uhrzeit</th>
                      <th className="px-4 py-2 text-center">Std.</th>
                      <th className="px-4 py-2 text-center">Fahrer</th>
                      <th className="px-4 py-2 text-center"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {group.entries
                      .sort((a, b) => a.weekday - b.weekday || (a.rhythm || '').localeCompare(b.rhythm || ''))
                      .map(entry => {
                        const rb = getRhythmBadge(entry.rhythm);
                        return (
                          <tr key={entry.id} className="hover:bg-gray-50">
                            <td className="px-4 py-2 font-medium">
                              {entry.weekday_name}
                              {entry.rhythm === 'monthly' && (
                                <span className="text-xs text-gray-400 ml-1">
                                  ({getMonthWeekLabel(entry)})
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-2">{entry.object_name}</td>
                            <td className="px-4 py-2 text-center">
                              <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${rb.color}`}>
                                {rb.short}
                              </span>
                            </td>
                            <td className="px-4 py-2 text-center">
                              <span className="inline-flex items-center gap-1 text-gray-700">
                                <Clock size={14} className="text-gray-400" />
                                {entry.start_time} - {entry.end_time}
                              </span>
                            </td>
                            <td className="px-4 py-2 text-center font-medium">{entry.planned_hours}h</td>
                            <td className="px-4 py-2 text-center">
                              {entry.is_driver && <Car size={16} className="text-blue-500 mx-auto" />}
                            </td>
                            <td className="px-4 py-2 text-center">
                              <button
                                onClick={() => handleDelete(entry.id)}
                                className="text-red-400 hover:text-red-600 p-1"
                              >
                                <Trash2 size={16} />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center p-4 border-b sticky top-0 bg-white">
              <h3 className="text-lg font-bold">Neuer Stamm-Eintrag</h3>
              <button onClick={() => setShowAddModal(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Mitarbeiter</label>
                <select
                  value={form.employee_id}
                  onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                >
                  <option value="">-- Waehlen --</option>
                  {employees.map(emp => (
                    <option key={emp.id} value={emp.id}>{emp.name || `${emp.first_name} ${emp.last_name}`}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Objekt</label>
                <select
                  value={form.object_id}
                  onChange={(e) => setForm({ ...form, object_id: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                >
                  <option value="">-- Waehlen --</option>
                  {objects.map(obj => (
                    <option key={obj.id} value={obj.id}>{obj.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Wochentage</label>
                <div className="flex gap-1 mb-2">
                  {WEEKDAYS.map(wd => (
                    <button
                      key={wd.value}
                      type="button"
                      onClick={() => toggleWeekday(wd.value)}
                      className={`px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                        form.weekdays.includes(wd.value)
                          ? 'bg-blue-500 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {wd.short}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={() => selectWeekdayPreset('mo-fr')} className="text-xs text-blue-600 hover:underline">Mo-Fr</button>
                  <button type="button" onClick={() => selectWeekdayPreset('mo-sa')} className="text-xs text-blue-600 hover:underline">Mo-Sa</button>
                  <button type="button" onClick={() => selectWeekdayPreset('all')} className="text-xs text-blue-600 hover:underline">Alle</button>
                  <button type="button" onClick={() => selectWeekdayPreset('none')} className="text-xs text-gray-500 hover:underline">Keine</button>
                </div>
              </div>

              {/* Rhythmus */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  <Repeat size={14} className="inline mr-1" />
                  Rhythmus
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {RHYTHMS.map(r => (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => setForm({ ...form, rhythm: r.value })}
                      className={`p-2.5 rounded-lg border-2 text-sm font-medium text-left transition-colors ${
                        form.rhythm === r.value
                          ? 'border-blue-500 bg-blue-50 text-blue-700'
                          : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                      }`}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
                {form.rhythm === 'biweekly_even' && (
                  <p className="text-xs text-green-600 mt-1">Gerade KW: 2, 4, 6, 8, 10, 12...</p>
                )}
                {form.rhythm === 'biweekly_odd' && (
                  <p className="text-xs text-orange-600 mt-1">Ungerade KW: 1, 3, 5, 7, 9, 11...</p>
                )}
              </div>

              {/* Monatlich: Welche Woche */}
              {form.rhythm === 'monthly' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Welche Woche im Monat?
                  </label>
                  <select
                    value={form.month_week}
                    onChange={(e) => setForm({ ...form, month_week: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                  >
                    {MONTH_WEEKS.map(mw => (
                      <option key={mw.value} value={mw.value}>{mw.label}</option>
                    ))}
                  </select>
                  <p className="text-xs text-purple-600 mt-1">
                    Nur 1x pro Monat am {form.month_week === -1 ? 'letzten' : `${form.month_week}.`} Vorkommen
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Von</label>
                  <input
                    type="time"
                    value={form.start_time}
                    onChange={(e) => setForm({ ...form, start_time: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                  <input
                    type="time"
                    value={form.end_time}
                    onChange={(e) => setForm({ ...form, end_time: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_driver}
                  onChange={(e) => setForm({ ...form, is_driver: e.target.checked })}
                  className="w-4 h-4 rounded"
                />
                <Car size={16} className="text-blue-500" />
                <span className="text-sm">Fahrer</span>
              </label>
            </div>
            <div className="flex justify-end gap-2 p-4 border-t sticky bottom-0 bg-white">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg text-sm"
              >
                Abbrechen
              </button>
              <button
                onClick={handleAdd}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm font-medium flex items-center gap-2"
              >
                <Save size={16} /> Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Generate Modal */}
      {showGenerateModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
            <div className="flex justify-between items-center p-4 border-b">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <Play size={20} className="text-green-500" />
                Dienstplan generieren
              </h3>
              <button onClick={() => { setShowGenerateModal(false); setGenerateResult(null); }} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <p className="text-sm text-gray-600">
                Erstellt Dienstplan-Eintraege basierend auf dem Stamm-Dienstplan.
                Beruecksichtigt automatisch den Rhythmus (woechentlich, 14-taegig, monatlich).
                Urlaubs- und Krankheitstage werden uebersprungen.
              </p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Monat</label>
                  <select
                    value={genForm.month}
                    onChange={(e) => setGenForm({ ...genForm, month: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                  >
                    {MONTH_NAMES.slice(1).map((name, i) => (
                      <option key={i + 1} value={i + 1}>{name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
                  <select
                    value={genForm.year}
                    onChange={(e) => setGenForm({ ...genForm, year: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                  >
                    <option value={2025}>2025</option>
                    <option value={2026}>2026</option>
                    <option value={2027}>2027</option>
                  </select>
                </div>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={genForm.overwrite}
                  onChange={(e) => setGenForm({ ...genForm, overwrite: e.target.checked })}
                  className="w-4 h-4 rounded"
                />
                <span className="text-sm text-gray-700">Bestehende Schichten ueberschreiben</span>
              </label>

              {/* Rhythmus-Info */}
              <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-600 space-y-1">
                <p className="font-medium text-gray-700">Aktive Rhythmen:</p>
                {(() => {
                  const rhythmCounts = {};
                  entries.forEach(e => {
                    const r = e.rhythm || 'weekly';
                    rhythmCounts[r] = (rhythmCounts[r] || 0) + 1;
                  });
                  return Object.entries(rhythmCounts).map(([r, count]) => {
                    const rb = getRhythmBadge(r);
                    return (
                      <p key={r}>
                        <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${rb.color} mr-1`}>{rb.short}</span>
                        {count} Eintraege
                      </p>
                    );
                  });
                })()}
              </div>

              {generateResult && (
                <div className={`p-3 rounded-lg text-sm ${generateResult.created > 0 ? 'bg-green-50 text-green-800' : 'bg-yellow-50 text-yellow-800'}`}>
                  <p className="font-medium">{generateResult.message}</p>
                  {generateResult.conflicts?.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <p className="font-medium flex items-center gap-1"><AlertCircle size={14} /> Konflikte:</p>
                      {generateResult.conflicts.map((c, i) => (
                        <p key={i} className="text-xs">{c}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 p-4 border-t">
              <button
                onClick={() => { setShowGenerateModal(false); setGenerateResult(null); }}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg text-sm"
              >
                Schliessen
              </button>
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:bg-gray-300 text-sm font-medium flex items-center gap-2"
              >
                {generating ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                    Generiere...
                  </>
                ) : (
                  <>
                    <Play size={16} /> Generieren
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StammDienstplanTab;
