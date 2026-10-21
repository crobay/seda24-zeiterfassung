import React, { useState, useEffect } from 'react';
import { Calculator, ChevronLeft, ChevronRight, RefreshCw, X, Lock, Save } from 'lucide-react';
import api from '../services/api';

const LohnUebersichtTab = () => {
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [editingCarryover, setEditingCarryover] = useState(null);
  const [carryoverValue, setCarryoverValue] = useState('');

  // Zeitkonto States
  const [editingSoll, setEditingSoll] = useState(null);
  const [sollValue, setSollValue] = useState('');
  const [showZeitkontoDialog, setShowZeitkontoDialog] = useState(null);
  const [zeitkontoDetail, setZeitkontoDetail] = useState(null);
  const [zeitkontoLoading, setZeitkontoLoading] = useState(false);
  const [vorschussValue, setVorschussValue] = useState('');

  const monthNames = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
  ];

  const getMonthName = (monthStr) => {
    const [year, month] = monthStr.split('-');
    return `${monthNames[parseInt(month) - 1]} ${year}`;
  };

  const changeMonth = (direction) => {
    const [year, month] = selectedMonth.split('-').map(Number);
    let newMonth = month + direction;
    let newYear = year;
    if (newMonth > 12) { newMonth = 1; newYear++; }
    else if (newMonth < 1) { newMonth = 12; newYear--; }
    setSelectedMonth(`${newYear}-${String(newMonth).padStart(2, '0')}`);
  };

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [year, month] = selectedMonth.split('-');
      const response = await api.get(`/admin/lohn-uebersicht?year=${year}&month=${month}`);
      setData(response.data || []);
    } catch (err) {
      console.error('Fehler beim Laden der Lohnübersicht:', err);
      setError('Fehler beim Laden der Daten');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [selectedMonth]);

  const formatHours = (hours) => hours ? hours.toFixed(2) : '0.00';
  const formatEuro = (amount) => amount ? amount.toFixed(2) + ' €' : '0.00 €';

  // Zeitkonto Funktionen
  const openZeitkontoDialog = async (employeeId) => {
    setZeitkontoLoading(true);
    setShowZeitkontoDialog(employeeId);
    try {
      const [yr, mo] = selectedMonth.split('-');
      const res = await api.get(`/admin/zeitkonto/detail?employee_id=${employeeId}&year=${yr}&month=${mo}`);
      setZeitkontoDetail(res.data);
      setVorschussValue(res.data.vorschuss_betrag || res.data.vorschuss_vorschlag || 0);
    } catch (err) {
      console.error('Zeitkonto-Detail Fehler:', err);
      setShowZeitkontoDialog(null);
    } finally {
      setZeitkontoLoading(false);
    }
  };

  const handleSollSave = async (empId) => {
    try {
      const [yr, mo] = selectedMonth.split('-');
      await api.put('/admin/zeitkonto/soll-stunden', {
        employee_id: empId, year: parseInt(yr), month: parseInt(mo),
        soll_stunden: parseFloat(sollValue || 140)
      });
      setEditingSoll(null);
      loadData();
    } catch (err) {
      console.error('Soll speichern Fehler:', err);
    }
  };

  const handleZeitkontoAbschliessen = async () => {
    if (!zeitkontoDetail) return;
    try {
      const [yr, mo] = selectedMonth.split('-');
      await api.post('/admin/zeitkonto/abschliessen', {
        employee_id: zeitkontoDetail.employee_id,
        year: parseInt(yr), month: parseInt(mo),
        soll_stunden: zeitkontoDetail.soll_stunden,
        vorschuss_betrag: parseFloat(vorschussValue || 0),
      });
      setShowZeitkontoDialog(null);
      setZeitkontoDetail(null);
      loadData();
    } catch (err) {
      console.error('Zeitkonto abschliessen Fehler:', err);
    }
  };

  const hasZeitkonto = data.some(r => r.zeitkonto_aktiv);

  const totals = data.reduce((acc, row) => ({
    normal_hours: (acc.normal_hours || 0) + (row.normal_hours || 0),
    normal_amount: (acc.normal_amount || 0) + (row.normal_amount || 0),
    sonder_hours: (acc.sonder_hours || 0) + (row.sonder_hours || 0),
    sonder_amount: (acc.sonder_amount || 0) + (row.sonder_amount || 0),
    sonntag_hours: (acc.sonntag_hours || 0) + (row.sonntag_hours || 0),
    nacht_hours: (acc.nacht_hours || 0) + (row.nacht_hours || 0),
    feiertag_hours: (acc.feiertag_hours || 0) + (row.feiertag_hours || 0),
    urlaub_days: (acc.urlaub_days || 0) + (row.urlaub_days || 0),
    urlaub_amount: (acc.urlaub_amount || 0) + (row.urlaub_amount || 0),
    km_amount: (acc.km_amount || 0) + (row.km_amount || 0),
    gesamt: (acc.gesamt || 0) + (row.gesamt || 0),
  }), {});

  const colCount = hasZeitkonto ? 16 : 14;

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-4 border-b flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <Calculator className="text-blue-600" size={24} />
          <h2 className="text-xl font-bold">Lohnübersicht für Lexware</h2>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => changeMonth(-1)} className="p-2 hover:bg-gray-100 rounded-lg">
            <ChevronLeft size={20} />
          </button>
          <div className="px-4 py-2 bg-blue-50 rounded-lg font-semibold min-w-[180px] text-center">
            {getMonthName(selectedMonth)}
          </div>
          <button onClick={() => changeMonth(1)} className="p-2 hover:bg-gray-100 rounded-lg">
            <ChevronRight size={20} />
          </button>
          <button onClick={loadData} className="ml-4 p-2 hover:bg-gray-100 rounded-lg" title="Aktualisieren">
            <RefreshCw size={20} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {error && <div className="p-4 bg-red-50 text-red-700 border-b">{error}</div>}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-2 py-2 text-left font-semibold border-b whitespace-nowrap">Mitarbeiter</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-green-50">Norm.Std</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-green-50">Satz</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-green-50">Norm.€</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-yellow-50">Sond.Std</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-yellow-50">Sond.€</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-orange-50">So</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-purple-50">Na</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-red-50">Fei</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-blue-50">Url.Tage</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-blue-50">Url.€</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-cyan-50">KM €</th>
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-amber-50">Übertr.</th>
              {hasZeitkonto && <>
                <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-indigo-50">Soll</th>
                <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-teal-50">Zeitk.</th>
              </>}
              <th className="px-2 py-2 text-right font-semibold border-b whitespace-nowrap bg-gray-200">GESAMT</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={colCount} className="px-4 py-6 text-center text-gray-500 text-sm">
                  <RefreshCw className="animate-spin inline mr-2" size={16} />Lade Daten...
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="px-4 py-6 text-center text-gray-500 text-sm">Keine Daten für diesen Monat</td>
              </tr>
            ) : (
              <>
                {data.map((row, index) => (
                  <tr key={row.employee_id || index} className="hover:bg-gray-50">
                    <td className="px-2 py-1.5 border-b font-medium whitespace-nowrap">
                      <div className="text-sm">{row.name}</div>
                      <div className="text-[10px] text-gray-500">{row.personal_nr}</div>
                    </td>
                    <td className="px-2 py-1.5 border-b text-right bg-green-50/50">{formatHours(row.normal_hours)}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-green-50/50 text-gray-600">{row.hourly_rate?.toFixed(2) || '15.50'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-green-50/50 font-medium">{formatEuro(row.normal_amount)}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-yellow-50/50">{row.sonder_hours > 0 ? formatHours(row.sonder_hours) : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-yellow-50/50 font-medium">{row.sonder_hours > 0 ? formatEuro(row.sonder_amount) : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-orange-50/50">{row.sonntag_hours > 0 ? formatHours(row.sonntag_hours) : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-purple-50/50">{row.nacht_hours > 0 ? formatHours(row.nacht_hours) : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-red-50/50">{row.feiertag_hours > 0 ? formatHours(row.feiertag_hours) : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-blue-50/50">{row.urlaub_days > 0 ? row.urlaub_days : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-blue-50/50 font-medium">{row.urlaub_amount > 0 ? formatEuro(row.urlaub_amount) : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-cyan-50/50">{row.km_amount > 0 ? formatEuro(row.km_amount) : '-'}</td>
                    <td className="px-2 py-1.5 border-b text-right bg-amber-50/50">
                      {editingCarryover === row.employee_id ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            step="0.01"
                            value={carryoverValue}
                            onChange={(e) => setCarryoverValue(e.target.value)}
                            className="w-16 p-1 border rounded text-right text-xs"
                            onKeyDown={async (e) => {
                              if (e.key === 'Enter') {
                                const [yr, mo] = selectedMonth.split('-');
                                await api.put('/admin/lohn-uebersicht/carryover', { employee_id: row.employee_id, year: parseInt(yr), month: parseInt(mo), carryover_amount: parseFloat(carryoverValue || 0) });
                                setEditingCarryover(null);
                                loadData();
                              } else if (e.key === 'Escape') {
                                setEditingCarryover(null);
                              }
                            }}
                            autoFocus
                          />
                          <span className="text-xs text-gray-400">€</span>
                        </div>
                      ) : (
                        <button
                          onClick={() => { setEditingCarryover(row.employee_id); setCarryoverValue(row.carryover || 0); }}
                          className={`text-sm hover:underline ${row.carryover ? 'font-medium' : 'text-gray-400'}`}
                        >
                          {row.carryover ? formatEuro(row.carryover) : '-'}
                        </button>
                      )}
                    </td>
                    {/* Zeitkonto-Spalten */}
                    {hasZeitkonto && <>
                      <td className="px-2 py-1.5 border-b text-right bg-indigo-50/50">
                        {row.zeitkonto_aktiv ? (
                          editingSoll === row.employee_id ? (
                            <input
                              type="number"
                              step="0.5"
                              value={sollValue}
                              onChange={(e) => setSollValue(e.target.value)}
                              className="w-14 p-1 border rounded text-right text-xs"
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleSollSave(row.employee_id);
                                else if (e.key === 'Escape') setEditingSoll(null);
                              }}
                              autoFocus
                            />
                          ) : (
                            <button
                              onClick={() => { setEditingSoll(row.employee_id); setSollValue(row.zeitkonto?.soll_stunden || 140); }}
                              className="hover:underline font-medium"
                              title="Klick zum Bearbeiten"
                            >
                              {formatHours(row.zeitkonto?.soll_stunden || 140)}
                            </button>
                          )
                        ) : <span className="text-gray-400">-</span>}
                      </td>
                      <td className="px-2 py-1.5 border-b text-right bg-teal-50/50">
                        {row.zeitkonto_aktiv && row.zeitkonto ? (
                          <button
                            onClick={() => openZeitkontoDialog(row.employee_id)}
                            className="hover:underline text-left"
                            title="Zeitkonto-Details"
                          >
                            {row.zeitkonto.status === 'abgeschlossen' ? (
                              <>
                                <div className={`font-medium ${row.zeitkonto.konto_saldo >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                  {row.zeitkonto.konto_saldo >= 0 ? '+' : ''}{formatHours(row.zeitkonto.konto_saldo)}
                                </div>
                                <div className="text-[10px] text-gray-500">abgeschl.</div>
                              </>
                            ) : (
                              <>
                                <div className={`font-medium ${((row.zeitkonto.vortrag_stunden || 0) + (row.zeitkonto.ist_stunden_normal || 0)) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                  {formatHours((row.zeitkonto.vortrag_stunden || 0) + (row.zeitkonto.ist_stunden_normal || 0))} h
                                </div>
                                <div className="text-[10px] text-gray-500">
                                  V {formatHours(row.zeitkonto.vortrag_stunden || 0)} + I {formatHours(row.zeitkonto.ist_stunden_normal || 0)}
                                </div>
                              </>
                            )}
                          </button>
                        ) : <span className="text-gray-400">-</span>}
                      </td>
                    </>}
                    <td className="px-2 py-1.5 border-b text-right bg-gray-100 font-bold text-sm">{formatEuro(row.gesamt)}</td>
                  </tr>
                ))}
                <tr className="bg-gray-200 font-bold">
                  <td className="px-2 py-2 border-t-2 border-gray-400">SUMME</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{formatHours(totals.normal_hours)}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right text-gray-500">-</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{formatEuro(totals.normal_amount)}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.sonder_hours > 0 ? formatHours(totals.sonder_hours) : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.sonder_hours > 0 ? formatEuro(totals.sonder_amount) : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.sonntag_hours > 0 ? formatHours(totals.sonntag_hours) : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.nacht_hours > 0 ? formatHours(totals.nacht_hours) : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.feiertag_hours > 0 ? formatHours(totals.feiertag_hours) : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.urlaub_days > 0 ? totals.urlaub_days : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.urlaub_amount > 0 ? formatEuro(totals.urlaub_amount) : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">{totals.km_amount > 0 ? formatEuro(totals.km_amount) : '-'}</td>
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right">-</td>
                  {hasZeitkonto && <>
                    <td className="px-2 py-2 border-t-2 border-gray-400 text-right">-</td>
                    <td className="px-2 py-2 border-t-2 border-gray-400 text-right">-</td>
                  </>}
                  <td className="px-2 py-2 border-t-2 border-gray-400 text-right text-base">{formatEuro(totals.gesamt)}</td>
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>

      <div className="p-4 bg-gray-50 border-t text-sm text-gray-600">
        <div className="flex gap-4 flex-wrap">
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-green-200 rounded"></span> Normal</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-yellow-200 rounded"></span> Sonder (20€)</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-orange-200 rounded"></span> Sonntag</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-purple-200 rounded"></span> Nacht 23-06</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-200 rounded"></span> Feiertag</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-blue-200 rounded"></span> Urlaub</span>
          {hasZeitkonto && <>
            <span className="flex items-center gap-1"><span className="w-3 h-3 bg-indigo-200 rounded"></span> Soll</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 bg-teal-200 rounded"></span> Zeitkonto</span>
          </>}
        </div>
      </div>

      {/* Zeitkonto Detail Dialog */}
      {showZeitkontoDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={() => { setShowZeitkontoDialog(null); setZeitkontoDetail(null); }}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
            {zeitkontoLoading ? (
              <div className="p-8 text-center text-gray-500">
                <RefreshCw className="animate-spin inline mr-2" size={20} />Lade Zeitkonto...
              </div>
            ) : zeitkontoDetail ? (
              <>
                <div className="p-5 border-b flex justify-between items-center">
                  <div>
                    <h3 className="text-lg font-bold">Zeitkonto: {zeitkontoDetail.employee_name}</h3>
                    <div className="text-sm text-gray-500 flex items-center gap-2">
                      {getMonthName(selectedMonth)}
                      {zeitkontoDetail.status === 'abgeschlossen' && (
                        <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs font-medium flex items-center gap-1">
                          <Lock size={10} /> Abgeschlossen
                        </span>
                      )}
                    </div>
                  </div>
                  <button onClick={() => { setShowZeitkontoDialog(null); setZeitkontoDetail(null); }} className="p-1 hover:bg-gray-100 rounded">
                    <X size={20} />
                  </button>
                </div>

                <div className="p-5 space-y-3">
                  <div className="flex justify-between py-2 border-b">
                    <span className="text-gray-600">Vortrag aus Vormonat:</span>
                    <span className="font-medium">{formatHours(zeitkontoDetail.vortrag_stunden)} Std</span>
                  </div>
                  <div className="flex justify-between py-2 border-b">
                    <span className="text-gray-600">Echte Normalstunden:</span>
                    <span className="font-medium">{formatHours(zeitkontoDetail.ist_stunden_normal)} Std</span>
                  </div>
                  <div className="flex justify-between py-2 border-b">
                    <span className="text-gray-600">Soll diesen Monat:</span>
                    <span className="font-medium">{formatHours(zeitkontoDetail.soll_stunden)} Std</span>
                  </div>
                  <div className="flex justify-between py-2 px-2 rounded bg-yellow-50 border border-yellow-200">
                    <span className="font-semibold">Übertrag (Ist - Soll):</span>
                    <span className={`font-bold ${zeitkontoDetail.uebertrag_stunden >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {zeitkontoDetail.uebertrag_stunden >= 0 ? '+' : ''}{formatHours(zeitkontoDetail.uebertrag_stunden)} Std
                    </span>
                  </div>
                  <div className="flex justify-between py-3 px-2 rounded bg-blue-50 border border-blue-200">
                    <span className="font-semibold">Neuer Saldo:</span>
                    <span className={`font-bold text-lg ${zeitkontoDetail.konto_saldo >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {zeitkontoDetail.konto_saldo >= 0 ? '+' : ''}{formatHours(zeitkontoDetail.konto_saldo)} Std
                    </span>
                  </div>

                  {/* Zuschlagsstunden */}
                  {(zeitkontoDetail.ist_stunden_sonntag > 0 || zeitkontoDetail.ist_stunden_nacht > 0 || zeitkontoDetail.ist_stunden_feiertag > 0) && (
                    <div className="p-2 bg-gray-50 rounded text-xs border">
                      <div className="font-semibold mb-1 text-gray-700">Zuschlagsstunden (werden separat im Lexware gebucht):</div>
                      {zeitkontoDetail.ist_stunden_sonntag > 0 && <div>Sonntag: {formatHours(zeitkontoDetail.ist_stunden_sonntag)} Std</div>}
                      {zeitkontoDetail.ist_stunden_nacht > 0 && <div>Nacht: {formatHours(zeitkontoDetail.ist_stunden_nacht)} Std</div>}
                      {zeitkontoDetail.ist_stunden_feiertag > 0 && <div>Feiertag: {formatHours(zeitkontoDetail.ist_stunden_feiertag)} Std</div>}
                    </div>
                  )}

                  {/* Vorschuss */}
                  <div className="p-3 border-2 border-dashed border-orange-300 rounded-lg mt-2">
                    <div className="text-sm font-semibold text-orange-700 mb-2">Vorschuss (LA 6005 im Folgemonat)</div>
                    {zeitkontoDetail.offener_vorschuss_vormonat > 0 && (
                      <div className="text-xs text-red-600 mb-2 bg-red-50 p-2 rounded">
                        Offener Vorschuss Vormonat: {zeitkontoDetail.offener_vorschuss_vormonat.toFixed(2)} € (wird diesen Monat abgezogen)
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="10"
                        value={vorschussValue}
                        onChange={(e) => setVorschussValue(e.target.value)}
                        className="flex-1 p-2 border rounded text-right"
                        disabled={zeitkontoDetail.status === 'abgeschlossen'}
                      />
                      <span className="text-sm font-medium">€</span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Vorschlag: {(zeitkontoDetail.vorschuss_vorschlag || 0).toFixed(2)} € ({formatHours(zeitkontoDetail.uebertrag_stunden)} Std × 11 €, auf 10er abgerundet)
                    </div>
                  </div>
                </div>

                <div className="p-5 border-t flex gap-3">
                  <button
                    onClick={() => { setShowZeitkontoDialog(null); setZeitkontoDetail(null); }}
                    className="flex-1 px-4 py-2.5 bg-gray-200 rounded-lg hover:bg-gray-300 font-medium"
                  >
                    Schließen
                  </button>
                  {zeitkontoDetail.status !== 'abgeschlossen' && (
                    <button
                      onClick={handleZeitkontoAbschliessen}
                      className="flex-1 px-4 py-2.5 bg-green-500 text-white rounded-lg hover:bg-green-600 font-medium flex items-center justify-center gap-2"
                    >
                      <Save size={16} /> Speichern & Übertragen
                    </button>
                  )}
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
};

export default LohnUebersichtTab;
