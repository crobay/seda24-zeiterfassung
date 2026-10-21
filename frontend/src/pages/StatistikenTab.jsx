import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { TrendingUp, ChevronLeft, ChevronRight, Settings, Plus, Trash2, Save, X, ArrowUp, ArrowDown, Edit3, RotateCcw } from 'lucide-react';

const MONTH_NAMES = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

const StatistikenTab = () => {
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [bwa, setBwa] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showSettings, setShowSettings] = useState(false);

  // Fixkosten-Bearbeitung direkt in BWA
  const [editingFixkosten, setEditingFixkosten] = useState(false);
  const [editFixkostenList, setEditFixkostenList] = useState([]);
  const [savingFixkosten, setSavingFixkosten] = useState(false);

  // Lohnnebenkosten-Bearbeitung direkt in BWA
  const [editingLnk, setEditingLnk] = useState(false);
  const [editLnkPct, setEditLnkPct] = useState(30);
  const [editLnkBetrag, setEditLnkBetrag] = useState('');
  const [savingLnk, setSavingLnk] = useState(false);

  // Settings State
  const [settingsData, setSettingsData] = useState({ settings: {}, fixed_costs: [] });

  const loadBwa = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/bwa?year=${selectedYear}&month=${selectedMonth}`);
      setBwa(res.data);
      setEditingFixkosten(false);
      setEditingLnk(false);
    } catch (err) {
      console.error('BWA laden fehlgeschlagen:', err);
    } finally {
      setLoading(false);
    }
  };

  const openSettings = async () => {
    try {
      const res = await api.get('/admin/finance-settings');
      setSettingsData(res.data);
      setShowSettings(true);
    } catch (err) {
      console.error('Settings laden fehlgeschlagen:', err);
    }
  };

  useEffect(() => { loadBwa(); }, [selectedYear, selectedMonth]);

  const changeMonth = (dir) => {
    let m = selectedMonth + dir;
    let y = selectedYear;
    if (m > 12) { m = 1; y++; }
    else if (m < 1) { m = 12; y--; }
    setSelectedMonth(m);
    setSelectedYear(y);
  };

  const fmt = (val) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val || 0);
  const fmtNum = (val) => new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val || 0);

  // Fixkosten bearbeiten
  const startEditFixkosten = () => {
    setEditFixkostenList(
      (bwa?.fixkosten_details || []).map(fc => ({ ...fc }))
    );
    setEditingFixkosten(true);
  };

  const addFixkostenRow = () => {
    setEditFixkostenList([...editFixkostenList, { name: '', amount: 0 }]);
  };

  const removeFixkostenRow = (index) => {
    setEditFixkostenList(editFixkostenList.filter((_, i) => i !== index));
  };

  const updateFixkostenRow = (index, field, value) => {
    const updated = [...editFixkostenList];
    updated[index] = { ...updated[index], [field]: value };
    setEditFixkostenList(updated);
  };

  const saveFixkosten = async () => {
    setSavingFixkosten(true);
    try {
      await api.put('/admin/bwa/fixkosten', {
        year: selectedYear,
        month: selectedMonth,
        costs: editFixkostenList.filter(fc => fc.name.trim()),
      });
      setEditingFixkosten(false);
      loadBwa();
    } catch (err) {
      console.error('Fixkosten speichern fehlgeschlagen:', err);
    } finally {
      setSavingFixkosten(false);
    }
  };

  const resetFixkosten = async () => {
    if (!confirm('Monatliche Fixkosten zurücksetzen auf Standard?')) return;
    try {
      await api.delete(`/admin/bwa/fixkosten/${selectedYear}/${selectedMonth}`);
      setEditingFixkosten(false);
      loadBwa();
    } catch (err) {
      console.error('Reset fehlgeschlagen:', err);
    }
  };

  // Lohnnebenkosten bearbeiten
  const startEditLnk = () => {
    setEditLnkPct(bwa?.gesamt?.lohnnebenkosten_pct || 30);
    setEditLnkBetrag(bwa?.gesamt?.lohnnebenkosten_betrag ?? '');
    setEditingLnk(true);
  };

  const saveLnk = async () => {
    setSavingLnk(true);
    try {
      await api.put('/admin/bwa/lohnnebenkosten', {
        year: selectedYear,
        month: selectedMonth,
        pct: parseFloat(editLnkPct),
        betrag: editLnkBetrag !== '' ? parseFloat(editLnkBetrag) : null,
      });
      setEditingLnk(false);
      loadBwa();
    } catch (err) {
      console.error('Lohnnebenkosten speichern fehlgeschlagen:', err);
    } finally {
      setSavingLnk(false);
    }
  };

  const resetLnk = async () => {
    if (!confirm('Lohnnebenkosten zurücksetzen auf Standard?')) return;
    try {
      await api.delete(`/admin/bwa/lohnnebenkosten/${selectedYear}/${selectedMonth}`);
      setEditingLnk(false);
      loadBwa();
    } catch (err) {
      console.error('Reset fehlgeschlagen:', err);
    }
  };

  const g = bwa?.gesamt || {};
  const editTotal = editFixkostenList.reduce((sum, fc) => sum + (parseFloat(fc.amount) || 0), 0);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center flex-wrap gap-3">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <TrendingUp className="text-blue-600" size={24} />
          Mini-BWA
        </h2>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-white rounded-lg shadow px-2 py-1">
            <button onClick={() => changeMonth(-1)} className="p-1 hover:bg-gray-100 rounded">
              <ChevronLeft size={18} />
            </button>
            <span className="font-semibold text-sm min-w-[130px] text-center">
              {MONTH_NAMES[selectedMonth]} {selectedYear}
            </span>
            <button onClick={() => changeMonth(1)} className="p-1 hover:bg-gray-100 rounded">
              <ChevronRight size={18} />
            </button>
          </div>
          <button
            onClick={openSettings}
            className="p-2 bg-white rounded-lg shadow hover:bg-gray-50 transition"
            title="Standard-Einstellungen"
          >
            <Settings size={20} className="text-gray-600" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">Lade BWA...</div>
      ) : !bwa ? (
        <div className="text-center py-12 text-gray-500">Keine Daten</div>
      ) : (
        <>
          {/* Kennzahlen-Karten */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <KpiCard label="Stunden" value={`${fmtNum(g.total_hours)}h`} color="gray" />
            <KpiCard label="Bruttoumsatz" value={fmt(g.brutto_umsatz)} color="blue" />
            <KpiCard label={`Personal (${g.lohnnebenkosten_pct || 30}% NK)`} value={fmt(g.personalkosten)} color="red" />
            <KpiCard label="Fixkosten" value={fmt(g.fixkosten)} color="orange" />
            <KpiCard label="Vorsteuer-Abf." value={fmt(g.vorsteuer_abfuehrung)} color="purple" />
            <KpiCard
              label="Netto-Gewinn"
              value={fmt(g.netto_gewinn)}
              color={g.netto_gewinn >= 0 ? 'green' : 'red'}
              icon={g.netto_gewinn >= 0 ? <ArrowUp size={16} /> : <ArrowDown size={16} />}
              bold
            />
          </div>

          {/* Gewinn-Berechnung kompakt */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="text-sm font-semibold text-gray-500 mb-3">Berechnung</h3>
            <div className="space-y-1 text-sm">
              <CalcRow label="Netto-Umsatz" value={g.netto_umsatz} />
              <CalcRow label={`+ MwSt (${bwa.settings?.vat_rate || 19}%)`} value={g.mwst_betrag} />
              <div className="border-t pt-1">
                <CalcRow label="= Bruttoumsatz" value={g.brutto_umsatz} bold />
              </div>
              <CalcRow label={`− Personalkosten (Löhne ${fmt(g.personalkosten_netto)} + ${g.lohnnebenkosten_betrag != null ? fmt(g.lohnnebenkosten_betrag) + ' NK' : (g.lohnnebenkosten_pct || 30) + '% NK'})`} value={-g.personalkosten} />
              <CalcRow label="− Fixkosten" value={-g.fixkosten} />
              <CalcRow label={`− Vorsteuer-Abf. (${bwa.settings?.vorsteuer_pct || 60}% der MwSt)`} value={-g.vorsteuer_abfuehrung} />
              <div className="border-t-2 border-gray-800 pt-1 mt-1">
                <CalcRow label="= Netto-Gewinn" value={g.netto_gewinn} bold big />
              </div>
            </div>
          </div>

          {/* Tabelle pro Objekt */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b">
              <h3 className="font-semibold text-gray-700">Ergebnis pro Objekt</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b">
                    <th className="px-4 py-2 text-left font-medium text-gray-600">Objekt</th>
                    <th className="px-4 py-2 text-right font-medium text-gray-600">Umsatz (Netto)</th>
                    <th className="px-4 py-2 text-right font-medium text-gray-600">Personalkosten</th>
                    <th className="px-4 py-2 text-right font-medium text-gray-600">Gewinn</th>
                    <th className="px-4 py-2 text-right font-medium text-gray-600">Marge</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {bwa.objekte?.map(obj => {
                    const marge = obj.netto_umsatz > 0 ? (obj.gewinn / obj.netto_umsatz * 100) : 0;
                    return (
                      <tr key={obj.object_id} className="hover:bg-gray-50">
                        <td className="px-4 py-2 font-medium text-gray-800">
                          {obj.object_name}
                          {!obj.is_active && <span className="ml-1 text-xs text-red-400">(inaktiv)</span>}
                        </td>
                        <td className="px-4 py-2 text-right text-blue-700">{fmt(obj.netto_umsatz)}</td>
                        <td className="px-4 py-2 text-right text-red-600">{fmt(obj.personalkosten)}</td>
                        <td className={`px-4 py-2 text-right font-semibold ${obj.gewinn >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {fmt(obj.gewinn)}
                        </td>
                        <td className={`px-4 py-2 text-right text-xs ${marge >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {obj.netto_umsatz > 0 ? `${marge.toFixed(0)}%` : '–'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-100 font-bold border-t-2">
                    <td className="px-4 py-3">SUMME</td>
                    <td className="px-4 py-3 text-right text-blue-700">{fmt(g.netto_umsatz)}</td>
                    <td className="px-4 py-3 text-right text-red-600">{fmt(g.personalkosten)}</td>
                    <td className={`px-4 py-3 text-right ${(g.netto_umsatz - g.personalkosten) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {fmt(g.netto_umsatz - g.personalkosten)}
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-gray-500">
                      {g.netto_umsatz > 0 ? `${((g.netto_umsatz - g.personalkosten) / g.netto_umsatz * 100).toFixed(0)}%` : '–'}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Lohnnebenkosten – EDITIERBAR pro Monat */}
          <div className="bg-white rounded-lg shadow p-4">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-semibold text-gray-500 flex items-center gap-2">
                Lohnnebenkosten – {MONTH_NAMES[selectedMonth]} {selectedYear}
                {bwa.lohnnebenkosten_is_monthly ? (
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">Monatswert</span>
                ) : (
                  <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Standard</span>
                )}
              </h3>
              <div className="flex gap-2">
                {!editingLnk ? (
                  <button
                    onClick={startEditLnk}
                    className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
                  >
                    <Edit3 size={14} /> Bearbeiten
                  </button>
                ) : (
                  <>
                    {bwa.lohnnebenkosten_is_monthly && (
                      <button
                        onClick={resetLnk}
                        className="text-xs flex items-center gap-1 text-orange-600 hover:text-orange-800 px-2 py-1 rounded hover:bg-orange-50"
                        title="Auf Standard zurücksetzen"
                      >
                        <RotateCcw size={14} /> Standard
                      </button>
                    )}
                    <button
                      onClick={() => setEditingLnk(false)}
                      className="text-xs flex items-center gap-1 text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100"
                    >
                      <X size={14} /> Abbrechen
                    </button>
                    <button
                      onClick={saveLnk}
                      disabled={savingLnk}
                      className="text-xs flex items-center gap-1 text-white bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded disabled:opacity-50"
                    >
                      <Save size={14} /> {savingLnk ? '...' : 'Speichern'}
                    </button>
                  </>
                )}
              </div>
            </div>

            {editingLnk ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-sm text-gray-600">Prozentsatz:</span>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.5"
                      value={editLnkPct}
                      onChange={(e) => setEditLnkPct(e.target.value)}
                      className="w-24 p-2 border rounded text-sm text-right pr-7"
                    />
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">%</span>
                  </div>
                  <span className="text-xs text-gray-400">
                    = {fmt((g.personalkosten_netto || 0) * (parseFloat(editLnkPct || 0) / 100))} NK
                  </span>
                </div>
                <div className="flex items-center gap-3 flex-wrap border-t pt-3">
                  <span className="text-sm text-gray-600">Tatsächlicher KK-Betrag:</span>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.01"
                      value={editLnkBetrag}
                      onChange={(e) => setEditLnkBetrag(e.target.value)}
                      placeholder="leer = Prozent"
                      className={`w-32 p-2 border rounded text-sm text-right pr-6 ${editLnkBetrag ? 'border-blue-400 bg-blue-50' : ''}`}
                    />
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">€</span>
                  </div>
                  {editLnkBetrag ? (
                    <span className="text-xs text-blue-600 font-medium">Betrag überschreibt Prozent-Berechnung</span>
                  ) : (
                    <span className="text-xs text-gray-400">Leer lassen = Prozent wird verwendet</span>
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-1 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Reine Löhne</span>
                  <span className="font-medium">{fmt(g.personalkosten_netto)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">
                    + Lohnnebenkosten
                    {g.lohnnebenkosten_betrag != null
                      ? <span className="text-blue-600 ml-1">(Betrag: {fmt(g.lohnnebenkosten_betrag)})</span>
                      : ` (${g.lohnnebenkosten_pct || 30}%)`
                    }
                  </span>
                  <span className="font-medium">{fmt((g.personalkosten || 0) - (g.personalkosten_netto || 0))}</span>
                </div>
                <div className="flex justify-between text-sm font-bold border-t pt-1">
                  <span>Personalkosten gesamt</span>
                  <span>{fmt(g.personalkosten)}</span>
                </div>
              </div>
            )}
          </div>

          {/* Fixkosten – EDITIERBAR pro Monat */}
          <div className="bg-white rounded-lg shadow p-4">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-semibold text-gray-500 flex items-center gap-2">
                Fixkosten – {MONTH_NAMES[selectedMonth]} {selectedYear}
                {bwa.fixkosten_is_monthly && (
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">Monatswert</span>
                )}
                {!bwa.fixkosten_is_monthly && (
                  <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Standard</span>
                )}
              </h3>
              <div className="flex gap-2">
                {!editingFixkosten ? (
                  <button
                    onClick={startEditFixkosten}
                    className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
                  >
                    <Edit3 size={14} /> Bearbeiten
                  </button>
                ) : (
                  <>
                    <button
                      onClick={addFixkostenRow}
                      className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
                    >
                      <Plus size={14} /> Zeile
                    </button>
                    {bwa.fixkosten_is_monthly && (
                      <button
                        onClick={resetFixkosten}
                        className="text-xs flex items-center gap-1 text-orange-600 hover:text-orange-800 px-2 py-1 rounded hover:bg-orange-50"
                        title="Auf Standard zurücksetzen"
                      >
                        <RotateCcw size={14} /> Standard
                      </button>
                    )}
                    <button
                      onClick={() => setEditingFixkosten(false)}
                      className="text-xs flex items-center gap-1 text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100"
                    >
                      <X size={14} /> Abbrechen
                    </button>
                    <button
                      onClick={saveFixkosten}
                      disabled={savingFixkosten}
                      className="text-xs flex items-center gap-1 text-white bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded disabled:opacity-50"
                    >
                      <Save size={14} /> {savingFixkosten ? '...' : 'Speichern'}
                    </button>
                  </>
                )}
              </div>
            </div>

            {editingFixkosten ? (
              <div className="space-y-2">
                {editFixkostenList.map((fc, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={fc.name}
                      onChange={(e) => updateFixkostenRow(i, 'name', e.target.value)}
                      placeholder="Bezeichnung..."
                      className="flex-1 p-2 border rounded text-sm"
                    />
                    <div className="relative">
                      <input
                        type="number"
                        step="0.01"
                        value={fc.amount}
                        onChange={(e) => updateFixkostenRow(i, 'amount', e.target.value)}
                        className="w-28 p-2 border rounded text-sm text-right pr-7"
                      />
                      <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">€/Mon</span>
                    </div>
                    <button
                      onClick={() => removeFixkostenRow(i)}
                      className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                <div className="flex justify-between font-semibold text-sm border-t pt-2 mt-2">
                  <span>Summe / Monat</span>
                  <span>{fmt(editTotal)}</span>
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                {bwa.fixkosten_details?.map(fc => (
                  <div key={fc.id} className="flex justify-between text-sm items-center">
                    <span className="text-gray-600">
                      {fc.name}
                      {fc.cost_type === 'yearly' && (
                        <span className="text-xs text-gray-400 ml-1">({fmt(fc.original_amount)}/Jahr)</span>
                      )}
                    </span>
                    <span className="font-medium">{fmt(fc.amount)}</span>
                  </div>
                ))}
                <div className="flex justify-between text-sm font-bold border-t pt-1">
                  <span>Summe Fixkosten / Monat</span>
                  <span>{fmt(g.fixkosten)}</span>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Settings Modal (Standard-Einstellungen) */}
      {showSettings && (
        <FinanceSettingsModal
          data={settingsData}
          onClose={() => setShowSettings(false)}
          onSaved={() => { setShowSettings(false); loadBwa(); }}
        />
      )}
    </div>
  );
};


// KPI Card Component
const KpiCard = ({ label, value, color, icon, bold }) => {
  const colors = {
    gray: 'text-gray-800', blue: 'text-blue-600', red: 'text-red-600',
    orange: 'text-orange-600', purple: 'text-purple-600', green: 'text-green-600',
  };
  return (
    <div className="bg-white rounded-lg shadow p-3">
      <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">{icon} {label}</div>
      <p className={`text-lg ${bold ? 'font-bold' : 'font-semibold'} ${colors[color] || 'text-gray-800'}`}>{value}</p>
    </div>
  );
};


// Calculation Row Component
const CalcRow = ({ label, value, bold, big }) => {
  const f = (v) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(Math.abs(v || 0));
  const isNeg = (value || 0) < 0;
  return (
    <div className={`flex justify-between ${bold ? 'font-bold' : ''} ${big ? 'text-lg' : ''}`}>
      <span className={bold ? 'text-gray-800' : 'text-gray-600'}>{label}</span>
      <span className={isNeg ? 'text-red-600' : (value || 0) > 0 ? 'text-green-700' : 'text-gray-600'}>
        {isNeg ? '−' : ''}{f(value)}
      </span>
    </div>
  );
};


// Finance Settings Modal (Standard-Werte)
const FinanceSettingsModal = ({ data, onClose, onSaved }) => {
  const [settings, setSettings] = useState({
    display_mode: data.settings?.display_mode || 'netto',
    vorsteuer_pct: data.settings?.vorsteuer_pct || '60',
    vat_rate: data.settings?.vat_rate || '19',
    lohnnebenkosten_pct: data.settings?.lohnnebenkosten_pct || '30',
  });
  const [fixedCosts, setFixedCosts] = useState(data.fixed_costs || []);
  const [saving, setSaving] = useState(false);

  const fmtModal = (v) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(v || 0);
  const totalMonthly = fixedCosts.reduce((sum, fc) => {
    const amt = parseFloat(fc.amount) || 0;
    return sum + (fc.cost_type === 'yearly' ? amt / 12 : amt);
  }, 0);

  const addCost = () => setFixedCosts([...fixedCosts, { name: '', amount: 0, cost_type: 'monthly' }]);
  const removeCost = (i) => setFixedCosts(fixedCosts.filter((_, idx) => idx !== i));
  const updateCost = (i, field, value) => {
    const u = [...fixedCosts];
    u[i] = { ...u[i], [field]: value };
    setFixedCosts(u);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put('/admin/finance-settings', {
        settings,
        fixed_costs: fixedCosts.filter(fc => fc.name.trim()),
      });
      onSaved();
    } catch (err) {
      console.error('Speichern fehlgeschlagen:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b flex justify-between items-center sticky top-0 bg-white rounded-t-xl">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Settings size={20} /> Standard-Einstellungen
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded"><X size={20} /></button>
        </div>

        <div className="p-4 space-y-6">
          <div className="space-y-3">
            <h4 className="font-semibold text-gray-700 text-sm">Steuer & Personal</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">MwSt-Satz (%)</label>
                <input type="number" step="0.1" value={settings.vat_rate}
                  onChange={(e) => setSettings({ ...settings, vat_rate: e.target.value })}
                  className="w-full p-2 border rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Vorsteuer-Abführung (%)</label>
                <input type="number" step="1" value={settings.vorsteuer_pct}
                  onChange={(e) => setSettings({ ...settings, vorsteuer_pct: e.target.value })}
                  className="w-full p-2 border rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Lohnnebenkosten (%)</label>
                <input type="number" step="0.5" value={settings.lohnnebenkosten_pct}
                  onChange={(e) => setSettings({ ...settings, lohnnebenkosten_pct: e.target.value })}
                  className="w-full p-2 border rounded-lg text-sm" />
              </div>
            </div>
            <p className="text-xs text-gray-400">Lohnnebenkosten = AG-Anteil Sozialversicherung etc. Personalkosten = Löhne × (1 + Lohnnebenkosten%)</p>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <h4 className="font-semibold text-gray-700 text-sm">Standard-Fixkosten pro Monat</h4>
              <button onClick={addCost} className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-800">
                <Plus size={14} /> Neue Zeile
              </button>
            </div>
            <p className="text-xs text-gray-400">Werden verwendet, wenn kein monatsspezifischer Wert eingetragen ist.</p>
            <div className="space-y-2">
              {fixedCosts.map((fc, i) => {
                const isYearly = fc.cost_type === 'yearly';
                const monthlyVal = isYearly ? (parseFloat(fc.amount) || 0) / 12 : parseFloat(fc.amount) || 0;
                return (
                  <div key={i}>
                    <div className="flex items-center gap-2">
                      <input type="text" value={fc.name} onChange={(e) => updateCost(i, 'name', e.target.value)}
                        placeholder="Bezeichnung..." className="flex-1 p-2 border rounded-lg text-sm" />
                      <select
                        value={fc.cost_type || 'monthly'}
                        onChange={(e) => updateCost(i, 'cost_type', e.target.value)}
                        className="p-2 border rounded-lg text-xs w-20"
                      >
                        <option value="monthly">Monat</option>
                        <option value="yearly">Jahr</option>
                      </select>
                      <div className="relative">
                        <input type="number" step="0.01" value={fc.amount}
                          onChange={(e) => updateCost(i, 'amount', e.target.value)}
                          className="w-24 p-2 border rounded-lg text-sm text-right pr-6" />
                        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">€</span>
                      </div>
                      <button onClick={() => removeCost(i)} className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded">
                        <Trash2 size={16} />
                      </button>
                    </div>
                    {isYearly && (
                      <div className="text-xs text-gray-400 ml-1 mt-0.5">= {fmtModal(monthlyVal)} / Monat</div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="flex justify-between font-semibold text-sm border-t pt-2">
              <span>Summe / Monat</span>
              <span>{fmtModal(totalMonthly)}</span>
            </div>
          </div>
        </div>

        <div className="p-4 border-t flex justify-end gap-2 sticky bottom-0 bg-white rounded-b-xl">
          <button onClick={onClose} className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg text-sm">Abbrechen</button>
          <button onClick={handleSave} disabled={saving}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 flex items-center gap-1 disabled:opacity-50">
            <Save size={16} /> {saving ? 'Speichere...' : 'Speichern'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default StatistikenTab;
