// FestgehaltSection.jsx - Schalter "Festgehalt" im Mitarbeiterprofil (eigenes Speichern, mit Audit im Backend)
import React, { useEffect, useState } from 'react';
import api from '../services/api';

const FestgehaltSection = ({ employeeId }) => {
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    api.get(`/admin/employees/${employeeId}/festgehalt`)
      .then(res => setForm({
        aktiv: !!res.data.aktiv,
        gueltig_ab: res.data.gueltig_ab || '',
        monatsstunden: String(res.data.monatsstunden ?? 100),
        stundensatz: String(res.data.stundensatz ?? 20),
      }))
      .catch(() => setForm(null));
  }, [employeeId]);

  if (!form) return null;

  const betrag = (parseFloat(form.monatsstunden) || 0) * (parseFloat(String(form.stundensatz).replace(',', '.')) || 0);

  const save = async () => {
    try {
      await api.put(`/admin/employees/${employeeId}/festgehalt`, {
        aktiv: form.aktiv,
        gueltig_ab: form.gueltig_ab,
        monatsstunden: parseFloat(form.monatsstunden),
        stundensatz: parseFloat(String(form.stundensatz).replace(',', '.')),
      });
      setMsg('Festgehalt gespeichert');
    } catch (e) {
      setMsg(e.response?.data?.detail || 'Fehler beim Speichern');
    }
    setTimeout(() => setMsg(''), 4000);
  };

  return (
    <div className="p-3 border rounded-lg space-y-2">
      <label className="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" checked={form.aktiv} onChange={e => setForm({ ...form, aktiv: e.target.checked })} className="rounded" />
        <span className="text-sm font-medium">Festgehalt</span>
      </label>
      {form.aktiv && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <label className="text-xs text-gray-600">Gültig ab
              <input type="date" value={form.gueltig_ab} onChange={e => setForm({ ...form, gueltig_ab: e.target.value })} className="w-full p-1 border rounded text-sm" />
            </label>
            <label className="text-xs text-gray-600">Monatsstunden
              <input type="number" step="0.5" value={form.monatsstunden} onChange={e => setForm({ ...form, monatsstunden: e.target.value })} className="w-full p-1 border rounded text-sm" />
            </label>
            <label className="text-xs text-gray-600">Stundensatz €
              <input type="number" step="0.01" value={form.stundensatz} onChange={e => setForm({ ...form, stundensatz: e.target.value })} className="w-full p-1 border rounded text-sm" />
            </label>
          </div>
          <p className="text-xs text-gray-500">
            Lexware LA 1 jeden Monat {form.monatsstunden} h = {betrag.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €.
            Kein Zeitkonto, keine Werktags-Automatik, Stempeln nicht lohnrelevant.
          </p>
        </>
      )}
      <div className="flex items-center gap-2">
        <button type="button" onClick={save} className="px-3 py-1 bg-blue-500 text-white rounded text-xs hover:bg-blue-600">Festgehalt speichern</button>
        {msg && <span className="text-xs text-gray-600">{msg}</span>}
      </div>
    </div>
  );
};

export default FestgehaltSection;
