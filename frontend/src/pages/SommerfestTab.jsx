import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Sun, Users, CheckCircle, XCircle, Clock, Edit2, Trash2, Plus, X } from 'lucide-react';

const SommerfestTab = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // { personal_nr, first_name, last_name, termin_wahl?, begleitung? }
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const res = await api.get('/fest/admin/overview');
      setData(res.data);
    } catch (e) {
      console.error('Fest load error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const terminLabel = (tw) => {
    switch(tw) {
      case '25_07': return 'Sa 25.07.';
      case '01_08': return 'Sa 01.08.';
      case 'beide': return 'Beide';
      case 'keiner': return 'Keiner';
      default: return tw;
    }
  };

  const terminColor = (tw) => {
    switch(tw) {
      case '25_07': return { bg: '#dbeafe', color: '#1e40af' };
      case '01_08': return { bg: '#dcfce7', color: '#166534' };
      case 'beide': return { bg: '#fef9c3', color: '#854d0e' };
      case 'keiner': return { bg: '#fee2e2', color: '#991b1b' };
      default: return { bg: '#f3f4f6', color: '#374151' };
    }
  };

  const handleSave = async () => {
    if (!modal.termin_wahl || !modal.begleitung) return;
    setSaving(true);
    try {
      await api.post('/fest/antwort', {
        personal_nr: modal.personal_nr,
        termin_wahl: modal.termin_wahl,
        begleitung: modal.begleitung
      });
      setModal(null);
      await load();
    } catch (e) {
      console.error('Save error:', e);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (personal_nr) => {
    if (!confirm('Antwort wirklich löschen?')) return;
    try {
      await api.delete(`/fest/admin/antwort/${personal_nr}`);
      await load();
    } catch (e) {
      console.error('Delete error:', e);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-yellow-500"></div></div>;
  if (!data) return <div className="text-center py-8 text-gray-500">Fehler beim Laden</div>;

  const { stats, answers, not_answered } = data;

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-yellow-400 to-orange-500 rounded-lg shadow p-6 text-white">
        <div className="flex items-center gap-3">
          <Sun size={32} />
          <div>
            <h2 className="text-2xl font-bold">Sommerfest 2026</h2>
            <p className="text-yellow-100">Umfrage-Auswertung</p>
          </div>
        </div>
      </div>

      {/* Statistiken */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 rounded-lg p-4 text-center">
          <p className="text-sm text-blue-600 font-medium">Sa 25. Juli</p>
          <p className="text-3xl font-bold text-blue-700">{stats.personen_25_07}</p>
          <p className="text-xs text-blue-500">Personen</p>
        </div>
        <div className="bg-green-50 rounded-lg p-4 text-center">
          <p className="text-sm text-green-600 font-medium">Sa 1. August</p>
          <p className="text-3xl font-bold text-green-700">{stats.personen_01_08}</p>
          <p className="text-xs text-green-500">Personen</p>
        </div>
        <div className="bg-yellow-50 rounded-lg p-4 text-center">
          <div className="flex items-center justify-center gap-1 mb-1"><CheckCircle size={16} className="text-yellow-600" /></div>
          <p className="text-3xl font-bold text-yellow-700">{stats.total_answered}</p>
          <p className="text-xs text-yellow-600">Geantwortet</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-4 text-center">
          <div className="flex items-center justify-center gap-1 mb-1"><Clock size={16} className="text-gray-500" /></div>
          <p className="text-3xl font-bold text-gray-700">{stats.total_not_answered}</p>
          <p className="text-xs text-gray-500">Offen</p>
        </div>
      </div>

      {/* Antworten */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-4 border-b">
          <h3 className="font-bold text-lg flex items-center gap-2"><Users size={20} /> Antworten ({answers.length})</h3>
        </div>
        <div className="divide-y">
          {answers.map(a => {
            const tc = terminColor(a.termin_wahl);
            return (
              <div key={a.personal_nr} className="px-4 py-3 flex items-center justify-between">
                <div>
                  <span className="font-medium">{a.first_name} {a.last_name}</span>
                  <span className="text-gray-400 text-sm ml-2">{a.personal_nr}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span style={{ background: tc.bg, color: tc.color, padding: '2px 10px', borderRadius: 20, fontSize: 13, fontWeight: 600 }}>
                    {terminLabel(a.termin_wahl)}
                  </span>
                  <span style={{ background: a.begleitung === 'zu_zweit' ? '#fce7f3' : '#f3f4f6', color: a.begleitung === 'zu_zweit' ? '#9d174d' : '#6b7280', padding: '2px 10px', borderRadius: 20, fontSize: 13 }}>
                    {a.begleitung === 'zu_zweit' ? 'Zu zweit' : 'Allein'}
                  </span>
                  <button onClick={() => setModal({ personal_nr: a.personal_nr, first_name: a.first_name, last_name: a.last_name, termin_wahl: a.termin_wahl, begleitung: a.begleitung })}
                    className="p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded" title="Bearbeiten">
                    <Edit2 size={16} />
                  </button>
                  <button onClick={() => handleDelete(a.personal_nr)}
                    className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded" title="Löschen">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            );
          })}
          {answers.length === 0 && <div className="text-center py-6 text-gray-400">Noch keine Antworten</div>}
        </div>
      </div>

      {/* Noch nicht geantwortet */}
      {not_answered.length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <div className="p-4 border-b">
            <h3 className="font-bold text-lg flex items-center gap-2 text-gray-500"><XCircle size={20} /> Noch nicht geantwortet ({not_answered.length})</h3>
          </div>
          <div className="p-4 flex flex-wrap gap-2">
            {not_answered.map(m => (
              <button key={m.personal_nr}
                onClick={() => setModal({ personal_nr: m.personal_nr, first_name: m.first_name, last_name: m.last_name, termin_wahl: '', begleitung: '' })}
                className="px-3 py-1 bg-gray-100 text-gray-600 rounded-full text-sm hover:bg-yellow-100 hover:text-yellow-800 transition-colors cursor-pointer flex items-center gap-1">
                <Plus size={14} /> {m.first_name} {m.last_name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-bold text-lg">Antwort für {modal.first_name} {modal.last_name}</h3>
              <button onClick={() => setModal(null)} className="p-1 hover:bg-gray-100 rounded"><X size={20} /></button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="font-medium text-sm text-gray-700 block mb-2">Termin</label>
                {[
                  { value: '25_07', label: 'Samstag, 25. Juli' },
                  { value: '01_08', label: 'Samstag, 1. August' },
                  { value: 'beide', label: 'Beide Termine' },
                  { value: 'keiner', label: 'Keiner' },
                ].map(opt => (
                  <button key={opt.value}
                    onClick={() => setModal({ ...modal, termin_wahl: opt.value })}
                    style={{
                      display: 'block', width: '100%', padding: '10px 14px', marginBottom: 6,
                      borderRadius: 8, border: modal.termin_wahl === opt.value ? '2px solid #f59e0b' : '2px solid #e5e7eb',
                      background: modal.termin_wahl === opt.value ? '#fffbeb' : 'white',
                      textAlign: 'left', cursor: 'pointer', fontSize: 14, color: '#374151'
                    }}>
                    {opt.label}
                  </button>
                ))}
              </div>
              <div>
                <label className="font-medium text-sm text-gray-700 block mb-2">Begleitung</label>
                {[
                  { value: 'allein', label: 'Allein' },
                  { value: 'zu_zweit', label: 'Zu zweit (mit Partner/in)' },
                ].map(opt => (
                  <button key={opt.value}
                    onClick={() => setModal({ ...modal, begleitung: opt.value })}
                    style={{
                      display: 'block', width: '100%', padding: '10px 14px', marginBottom: 6,
                      borderRadius: 8, border: modal.begleitung === opt.value ? '2px solid #f59e0b' : '2px solid #e5e7eb',
                      background: modal.begleitung === opt.value ? '#fffbeb' : 'white',
                      textAlign: 'left', cursor: 'pointer', fontSize: 14, color: '#374151'
                    }}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="p-4 border-t flex gap-2">
              <button onClick={() => setModal(null)} className="flex-1 py-2 border rounded-lg text-gray-600 hover:bg-gray-50">Abbrechen</button>
              <button onClick={handleSave} disabled={!modal.termin_wahl || !modal.begleitung || saving}
                className="flex-1 py-2 bg-yellow-500 text-white rounded-lg font-bold hover:bg-yellow-600 disabled:bg-gray-300 disabled:cursor-default">
                {saving ? 'Speichern...' : 'Speichern'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SommerfestTab;
