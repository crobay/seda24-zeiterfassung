import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Calendar, Check, X, Clock, Edit2, ArrowRight, Ban, RefreshCw, Calculator, Plus, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';

const UrlaubVerwaltungTab = () => {
  const [requests, setRequests] = useState([]);
  const [overview, setOverview] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [activeView, setActiveView] = useState('requests');
  const [year, setYear] = useState(new Date().getFullYear());
  const [toast, setToast] = useState(null);
  const [editModal, setEditModal] = useState(null);
  const [editingEntitlement, setEditingEntitlement] = useState(null);
  const [entitlementValue, setEntitlementValue] = useState('');
  const [recalcLoading, setRecalcLoading] = useState(false);
  const [recalcResults, setRecalcResults] = useState(null);
  const [correctionPreview, setCorrectionPreview] = useState(null);
  const [correctionLoading, setCorrectionLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({ employee_id: '', start_date: '', end_date: '', type: 'urlaub' });
  const [createLoading, setCreateLoading] = useState(false);
  const [employees, setEmployees] = useState([]);

  // Neue Filter-States
  const [filterEmployee, setFilterEmployee] = useState('');
  const [filterYear, setFilterYear] = useState(new Date().getFullYear());
  const [filterMonths, setFilterMonths] = useState([]);
  const [sortDir, setSortDir] = useState('asc');

  // Kalender-States
  const [calendarData, setCalendarData] = useState([]);
  const [calYear, setCalYear] = useState(new Date().getFullYear());
  const [calMonth, setCalMonth] = useState([new Date().getMonth()]);
  const [hideEmpty, setHideEmpty] = useState(false);
  const [calLoading, setCalLoading] = useState(false);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    loadData();
    loadEmployees();
  }, [filterStatus, year, filterEmployee, filterYear]);

  useEffect(() => {
    if (activeView === 'calendar') loadCalendar();
  }, [activeView, calYear]);

  const loadEmployees = async () => {
    try {
      const res = await api.get('/admin/employees-with-categories?include_inactive=false');
      setEmployees((res.data || []).filter(e => !e.personal_nr?.startsWith('A')));
    } catch (e) { console.error(e); }
  };

  const loadCalendar = async () => {
    setCalLoading(true);
    try {
      const res = await api.get(`/vacation/admin/calendar?year=${calYear}`);
      setCalendarData(res.data || []);
    } catch (e) { console.error(e); }
    finally { setCalLoading(false); }
  };

  const handleCreate = async () => {
    if (!createForm.employee_id || !createForm.start_date || !createForm.end_date) {
      showToast('Bitte alle Felder ausfuellen', 'error'); return;
    }
    setCreateLoading(true);
    try {
      const res = await api.post('/vacation/admin/create-request', createForm);
      showToast(res.data.message, 'success');
      setShowCreateModal(false);
      setCreateForm({ employee_id: '', start_date: '', end_date: '', type: 'urlaub' });
      loadData();
    } catch (e) {
      showToast('Fehler: ' + (e.response?.data?.detail || 'Unbekannt'), 'error');
    } finally {
      setCreateLoading(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterStatus) params.append('status', filterStatus);
      if (filterEmployee) params.append('employee_id', filterEmployee);
      if (filterYear) params.append('year', filterYear);
      const qs = params.toString();
      const [reqRes, ovRes] = await Promise.all([
        api.get(`/vacation/admin/requests${qs ? `?${qs}` : ''}`),
        api.get(`/vacation/admin/overview?year=${year}`),
      ]);
      setRequests(reqRes.data);
      setOverview(ovRes.data);
    } catch (error) {
      console.error('Fehler:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = async (requestId, status, extraData = {}) => {
    const labels = { approved: 'genehmigen', rejected: 'ablehnen', cancelled: 'stornieren', shifted: 'verschieben' };
    if (!window.confirm(`Urlaubsantrag wirklich ${labels[status] || status}?`)) return;
    try {
      await api.put(`/vacation/admin/requests/${requestId}`, { status, ...extraData });
      showToast(`Antrag ${status === 'approved' ? 'genehmigt' : status === 'rejected' ? 'abgelehnt' : status === 'cancelled' ? 'storniert' : 'verschoben'}`, 'success');
      loadData();
    } catch (error) {
      showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
    }
  };

  const handleSaveOnly = async (modal) => {
    try {
      await api.put(`/vacation/admin/requests/${modal.id}`, {
        start_date: modal.start_date,
        end_date: modal.end_date,
      });
      showToast('Daten gespeichert', 'success');
      setEditModal(null);
      loadData();
    } catch (e) {
      showToast('Fehler: ' + (e.response?.data?.detail || 'Unbekannt'), 'error');
    }
  };

  const handleSaveAndApprove = async (modal) => {
    if (!window.confirm('Antrag speichern und genehmigen?')) return;
    try {
      await api.put(`/vacation/admin/requests/${modal.id}`, {
        status: 'approved',
        start_date: modal.start_date,
        end_date: modal.end_date,
      });
      showToast('Gespeichert und genehmigt', 'success');
      setEditModal(null);
      loadData();
    } catch (e) {
      showToast('Fehler: ' + (e.response?.data?.detail || 'Unbekannt'), 'error');
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending': return { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Offen' };
      case 'approved': return { bg: 'bg-green-100', text: 'text-green-800', label: 'Genehmigt' };
      case 'rejected': return { bg: 'bg-red-100', text: 'text-red-800', label: 'Abgelehnt' };
      case 'cancelled': return { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Storniert' };
      case 'shifted': return { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Verschoben' };
      default: return { bg: 'bg-gray-100', text: 'text-gray-800', label: status };
    }
  };

  const getTypeBadge = (type) => {
    if (type === 'abwesenheit') return { bg: 'bg-orange-100', text: 'text-orange-800', label: 'Abwesenheit' };
    return { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Urlaub' };
  };

  const pendingCount = requests.filter(r => r.status === 'pending').length;

  // Client-seitige Sortierung + Monatsfilter
  const sortedRequests = [...requests]
    .filter(req => {
      if (filterMonths.length === 0) return true;
      const startM = new Date(req.start_date).getMonth() + 1;
      const endM = new Date(req.end_date).getMonth() + 1;
      return filterMonths.some(m => {
        if (endM >= startM) return m >= startM && m <= endM;
        return m >= startM || m <= endM; // Jahresuebergang (Dez-Jan)
      });
    })
    .sort((a, b) => {
      const da = new Date(a.start_date), db_date = new Date(b.start_date);
      return sortDir === 'asc' ? da - db_date : db_date - da;
    });

  const monthNames = ['Jan','Feb','Maer','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Urlaubsverwaltung</h2>
          {pendingCount > 0 && (
            <p className="text-orange-600 font-medium">{pendingCount} offene Antraege</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-3 py-1.5 bg-green-500 text-white rounded-lg hover:bg-green-600 text-sm flex items-center gap-1"
          >
            <Plus size={14} /> Neuer Eintrag
          </button>
          <div className="flex bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setActiveView('requests')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeView === 'requests' ? 'bg-white shadow text-blue-600' : 'text-gray-600'}`}
          >
            Antraege
          </button>
          <button
            onClick={() => setActiveView('overview')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeView === 'overview' ? 'bg-white shadow text-blue-600' : 'text-gray-600'}`}
          >
            Uebersicht
          </button>
          <button
            onClick={() => setActiveView('calendar')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeView === 'calendar' ? 'bg-white shadow text-blue-600' : 'text-gray-600'}`}
          >
            <span className="flex items-center gap-1"><Calendar size={14} /> Kalender</span>
          </button>
          </div>
        </div>
      </div>

      {activeView === 'requests' && (
        <>
          {/* Status-Filter */}
          <div className="flex gap-2 flex-wrap">
            {[
              { value: '', label: 'Alle' },
              { value: 'pending', label: 'Offen' },
              { value: 'approved', label: 'Genehmigt' },
              { value: 'rejected', label: 'Abgelehnt' },
              { value: 'cancelled', label: 'Storniert' },
            ].map((f) => (
              <button
                key={f.value}
                onClick={() => setFilterStatus(f.value)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  filterStatus === f.value
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Erweiterte Filter */}
          <div className="bg-white rounded-lg shadow p-4 space-y-3">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Mitarbeiter</label>
                <select
                  value={filterEmployee}
                  onChange={(e) => setFilterEmployee(e.target.value)}
                  className="p-2 border rounded-lg text-sm min-w-[180px]"
                >
                  <option value="">Alle Mitarbeiter</option>
                  {employees.map(emp => (
                    <option key={emp.id} value={emp.id}>{emp.first_name} {emp.last_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Jahr</label>
                <select
                  value={filterYear}
                  onChange={(e) => setFilterYear(e.target.value)}
                  className="p-2 border rounded-lg text-sm"
                >
                  <option value="">Alle Jahre</option>
                  {[2024, 2025, 2026, 2027].map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Monat {filterMonths.length > 0 && <span className="text-gray-400">({filterMonths.length} gewaehlt)</span>}
                </label>
                <div className="flex gap-1 flex-wrap">
                  <button
                    onClick={() => setFilterMonths([])}
                    className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
                      filterMonths.length === 0 ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    Alle
                  </button>
                  {monthNames.map((m, i) => (
                    <button
                      key={i}
                      onClick={() => setFilterMonths(prev =>
                        prev.includes(i + 1) ? prev.filter(x => x !== i + 1) : [...prev, i + 1]
                      )}
                      className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
                        filterMonths.includes(i + 1) ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Antraege Liste */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            {loading ? (
              <div className="p-8 text-center text-gray-500">Lade...</div>
            ) : sortedRequests.length === 0 ? (
              <div className="p-8 text-center text-gray-500">Keine Antraege</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Mitarbeiter</th>
                      <th
                        className="px-4 py-3 text-left text-sm font-semibold cursor-pointer select-none hover:text-blue-600"
                        onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}
                      >
                        <span className="flex items-center gap-1">
                          Zeitraum
                          {sortDir === 'desc' ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                        </span>
                      </th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Typ</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Tage</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Status</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Beantragt</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Aktion</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {sortedRequests.map((req) => {
                      const badge = getStatusBadge(req.status);
                      return (
                        <tr key={req.id} className={`hover:bg-gray-50 ${req.status === 'pending' ? 'bg-yellow-50/50' : ''}`}>
                          <td className="px-4 py-3">
                            <div className="text-sm font-medium">{req.employee_name}</div>
                            <div className="text-xs text-gray-500">{req.personal_nr}</div>
                          </td>
                          <td className="px-4 py-3 text-sm">
                            {formatDate(req.start_date)} - {formatDate(req.end_date)}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {(() => {
                              const tb = getTypeBadge(req.type);
                              return <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${tb.bg} ${tb.text}`}>{tb.label}</span>;
                            })()}
                          </td>
                          <td className="px-4 py-3 text-center text-sm font-medium">
                            {req.working_days}
                            {req.exceeds_entitlement && (
                              <div className="text-[10px] text-red-600 font-bold mt-0.5" title="Uebersteigt Restanspruch">Uebersteigt Anspruch</div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${badge.bg} ${badge.text}`}>
                              {badge.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">
                            {formatDate(req.requested_at)}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <div className="flex gap-1 justify-center flex-wrap">
                              {(req.status === 'pending' || req.status === 'shifted') && (
                                <>
                                  <button
                                    onClick={() => handleDecision(req.id, 'approved')}
                                    className="p-1.5 bg-green-100 text-green-700 rounded-lg hover:bg-green-200"
                                    title="Genehmigen"
                                  >
                                    <Check size={16} />
                                  </button>
                                  <button
                                    onClick={() => handleDecision(req.id, 'rejected')}
                                    className="p-1.5 bg-red-100 text-red-700 rounded-lg hover:bg-red-200"
                                    title="Ablehnen"
                                  >
                                    <X size={16} />
                                  </button>
                                </>
                              )}
                              {(req.status === 'pending' || req.status === 'approved' || req.status === 'shifted') && (
                                <>
                                  <button
                                    onClick={() => setEditModal({ ...req })}
                                    className="p-1.5 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200"
                                    title="Bearbeiten"
                                  >
                                    <Edit2 size={16} />
                                  </button>
                                  <button
                                    onClick={() => handleDecision(req.id, 'cancelled')}
                                    className="p-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                                    title="Stornieren"
                                  >
                                    <Ban size={16} />
                                  </button>
                                </>
                              )}
                              {req.status === 'rejected' && (
                                <button
                                  onClick={() => handleDecision(req.id, 'approved')}
                                  className="p-1.5 bg-green-100 text-green-700 rounded-lg hover:bg-green-200"
                                  title="Doch genehmigen"
                                >
                                  <Check size={16} />
                                </button>
                              )}
                              {req.status === 'cancelled' && (
                                <button
                                  onClick={() => handleDecision(req.id, 'approved')}
                                  className="p-1.5 bg-green-100 text-green-700 rounded-lg hover:bg-green-200"
                                  title="Reaktivieren"
                                >
                                  <Check size={16} />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {activeView === 'overview' && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <button onClick={() => setYear(y => y - 1)} className="px-3 py-1.5 bg-gray-100 rounded-lg hover:bg-gray-200">
                &larr;
              </button>
              <span className="font-bold text-lg">{year}</span>
              <button onClick={() => setYear(y => y + 1)} className="px-3 py-1.5 bg-gray-100 rounded-lg hover:bg-gray-200">
                &rarr;
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (!window.confirm('Urlaubssaetze fuer alle MA nach § 11 BUrlG (Durchschnitt der letzten 13 Wochen) neu berechnen?')) return;
                  setRecalcLoading(true);
                  try {
                    const res = await api.post('/vacation/admin/recalc-vacation-rates', { year });
                    const updated = res.data.results.filter(r => r.status === 'updated');
                    const skipped = res.data.results.filter(r => r.status === 'skipped');
                    setRecalcResults(res.data.results);
                    showToast(`${updated.length} Saetze aktualisiert, ${skipped.length} uebersprungen`, 'success');
                    loadData();
                  } catch (error) {
                    showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
                  } finally {
                    setRecalcLoading(false);
                  }
                }}
                disabled={recalcLoading}
                className="px-3 py-1.5 bg-orange-500 text-white rounded-lg hover:bg-orange-600 text-sm flex items-center gap-1 disabled:opacity-50"
              >
                <Calculator size={14} /> {recalcLoading ? 'Berechne...' : 'Urlaubssaetze berechnen'}
              </button>
              <button
                onClick={async () => {
                  setCorrectionLoading(true);
                  try {
                    const res = await api.post('/vacation/admin/recalc-vacation-entries', { preview: true, year });
                    if (res.data.results.length === 0) {
                      showToast('Keine Korrekturen noetig - alle Saetze sind aktuell', 'success');
                    } else {
                      setCorrectionPreview(res.data);
                    }
                  } catch (error) {
                    showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
                  } finally {
                    setCorrectionLoading(false);
                  }
                }}
                disabled={correctionLoading}
                className="px-3 py-1.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm flex items-center gap-1 disabled:opacity-50"
              >
                <RefreshCw size={14} className={correctionLoading ? 'animate-spin' : ''} /> {correctionLoading ? 'Pruefe...' : 'Buchungen korrigieren'}
              </button>
              <button
                onClick={async () => {
                  if (!window.confirm(`Resturlaub von ${year - 1} nach ${year} uebertragen?`)) return;
                  try {
                    const res = await api.post('/vacation/admin/carry-over', { from_year: year - 1, to_year: year });
                    showToast(`Uebertrag fuer ${res.data.carried_employees} MA durchgefuehrt`, 'success');
                    loadData();
                  } catch (error) {
                    showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
                  }
                }}
                className="px-3 py-1.5 bg-purple-500 text-white rounded-lg hover:bg-purple-600 text-sm flex items-center gap-1"
              >
                <RefreshCw size={14} /> Vorjahresuebertrag
              </button>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow overflow-hidden">
            {loading ? (
              <div className="p-8 text-center text-gray-500">Lade...</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold">Mitarbeiter</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Anspruch</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Genommen</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Resturlaub</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Tagessatz</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">Offen</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {overview.map((emp) => (
                      <tr key={emp.employee_id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="text-sm font-medium">{emp.name}</div>
                          <div className="text-xs text-gray-500">{emp.personal_nr}</div>
                        </td>
                        <td className="px-4 py-3 text-center">
                          {editingEntitlement === emp.employee_id ? (
                            <div className="flex items-center justify-center gap-1">
                              <input
                                type="number"
                                step="0.5"
                                value={entitlementValue}
                                onChange={(e) => setEntitlementValue(e.target.value)}
                                className="w-20 p-1.5 border-2 border-blue-400 rounded text-center text-sm font-medium focus:ring-2 focus:ring-blue-300"
                                onKeyDown={async (e) => {
                                  if (e.key === 'Enter') {
                                    try {
                                      await api.put('/vacation/admin/entitlement', {
                                        employee_id: emp.employee_id,
                                        year: year,
                                        days_entitled: parseFloat(entitlementValue || 0),
                                      });
                                      showToast('Anspruch gespeichert', 'success');
                                      setEditingEntitlement(null);
                                      loadData();
                                    } catch (err) {
                                      showToast('Fehler', 'error');
                                    }
                                  } else if (e.key === 'Escape') {
                                    setEditingEntitlement(null);
                                  }
                                }}
                                onBlur={async () => {
                                  try {
                                    await api.put('/vacation/admin/entitlement', {
                                      employee_id: emp.employee_id,
                                      year: year,
                                      days_entitled: parseFloat(entitlementValue || 0),
                                    });
                                    showToast('Anspruch gespeichert', 'success');
                                    setEditingEntitlement(null);
                                    loadData();
                                  } catch (err) {
                                    showToast('Fehler', 'error');
                                  }
                                }}
                                autoFocus
                              />
                            </div>
                          ) : (
                            <button
                              onClick={() => { setEditingEntitlement(emp.employee_id); setEntitlementValue(emp.days_entitled); }}
                              className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-800 border border-dashed border-blue-300 rounded px-2 py-0.5 hover:bg-blue-50 transition-colors"
                              title="Klicken zum Bearbeiten"
                            >
                              {emp.days_entitled}
                              <Edit2 size={12} />
                            </button>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center text-sm">{emp.days_taken}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`font-bold text-sm ${emp.days_remaining > 5 ? 'text-green-600' : emp.days_remaining > 0 ? 'text-orange-600' : 'text-red-600'}`}>
                            {emp.days_remaining}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center text-sm">
                          {emp.vacation_rate ? `${emp.vacation_rate.toFixed(2)} €` : '-'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {emp.pending_requests > 0 && (
                            <span className="inline-block px-2 py-0.5 bg-yellow-100 text-yellow-800 rounded-full text-xs font-medium">
                              {emp.pending_requests}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-gray-50 border-t-2 font-bold">
                      <td className="px-4 py-3 text-sm">Summe</td>
                      <td className="px-4 py-3 text-center text-sm">{overview.reduce((s, e) => s + (e.days_entitled || 0), 0)}</td>
                      <td className="px-4 py-3 text-center text-sm">{overview.reduce((s, e) => s + (e.days_taken || 0), 0)}</td>
                      <td className="px-4 py-3 text-center text-sm font-bold text-green-600">{overview.reduce((s, e) => s + (e.days_remaining || 0), 0)}</td>
                      <td className="px-4 py-3 text-center text-sm">-</td>
                      <td className="px-4 py-3 text-center text-sm">{overview.reduce((s, e) => s + (e.pending_requests || 0), 0)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Kalenderansicht — Monatsraster mit Mehrfachauswahl */}
      {activeView === 'calendar' && (() => {
        const fullMonthNames = ['Januar','Februar','Maerz','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];

        // Welche Monate anzeigen? calMonths (Array) oder alle 12
        const selectedMonths = calMonth === null ? [] : (Array.isArray(calMonth) ? calMonth : [calMonth]);
        const displayMonths = selectedMonths.length > 0
          ? selectedMonths.sort((a, b) => a - b)
          : Array.from({ length: 12 }, (_, i) => i);

        // Wochenend-Erkennung
        const isWeekend = (month, day) => {
          const d = new Date(calYear, month, day);
          return d.getDay() === 0 || d.getDay() === 6;
        };

        // Daten fuer einen Monat filtern + Zeitraum-Gruppierung
        const processEmployee = (emp, month) => {
          const monthDays = emp.days.filter(d => {
            const dt = new Date(d.date);
            return dt.getMonth() === month && dt.getFullYear() === calYear;
          });
          const dayMap = {};
          monthDays.forEach(d => { dayMap[new Date(d.date).getDate()] = d; });

          // Zeitraum-Positionen per request_id
          const groups = {};
          monthDays.forEach(d => {
            const rid = d.request_id || d.date;
            if (!groups[rid]) groups[rid] = [];
            groups[rid].push(new Date(d.date).getDate());
          });
          const posMap = {};
          Object.values(groups).forEach(days => {
            days.sort((a, b) => a - b);
            days.forEach((day, idx) => {
              if (days.length === 1) posMap[day] = 'single';
              else if (idx === 0) posMap[day] = 'first';
              else if (idx === days.length - 1) posMap[day] = 'last';
              else posMap[day] = 'middle';
            });
          });

          const approvedCount = monthDays.filter(d => d.status === 'approved').length;
          return { dayMap, posMap, approvedCount, hasAny: monthDays.length > 0 };
        };

        // Hat MA in mindestens einem der angezeigten Monate Urlaub?
        const empHasAnyInDisplayMonths = (emp) =>
          displayMonths.some(m => processEmployee(emp, m).hasAny);

        const displayData = hideEmpty
          ? calendarData.filter(empHasAnyInDisplayMonths)
          : calendarData;

        // Toggle Monat in Mehrfachauswahl
        const toggleMonth = (mi) => {
          setCalMonth(prev => {
            const arr = prev === null ? [] : (Array.isArray(prev) ? prev : [prev]);
            return arr.includes(mi) ? arr.filter(x => x !== mi) : [...arr, mi].sort((a, b) => a - b);
          });
        };

        return (
        <>
          {/* Navigation: Jahr + Monatsauswahl + Toggle */}
          <div className="space-y-3">
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2">
                <button onClick={() => setCalYear(y => y - 1)} className="p-2 bg-gray-100 rounded-lg hover:bg-gray-200">
                  <ChevronLeft size={18} />
                </button>
                <span className="font-bold text-lg w-12 text-center">{calYear}</span>
                <button onClick={() => setCalYear(y => y + 1)} className="p-2 bg-gray-100 rounded-lg hover:bg-gray-200">
                  <ChevronRight size={18} />
                </button>
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer ml-auto">
                <input type="checkbox" checked={hideEmpty} onChange={e => setHideEmpty(e.target.checked)}
                  className="rounded border-gray-300" />
                Nur mit Urlaub
              </label>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Monate {selectedMonths.length > 0 && <span className="text-gray-400">({selectedMonths.length} gewaehlt)</span>}
              </label>
              <div className="flex gap-1 flex-wrap">
                <button
                  onClick={() => setCalMonth([])}
                  className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
                    selectedMonths.length === 0 ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  Alle
                </button>
                {monthNames.map((m, i) => (
                  <button
                    key={i}
                    onClick={() => toggleMonth(i)}
                    className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
                      selectedMonths.includes(i) ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {calLoading ? (
            <div className="p-8 text-center text-gray-500 bg-white rounded-lg shadow">Lade Kalender...</div>
          ) : displayMonths.map(mi => {
            const daysInMonth = new Date(calYear, mi + 1, 0).getDate();
            const dayNumbers = Array.from({ length: daysInMonth }, (_, i) => i + 1);

            return (
            <div key={mi} className="bg-white rounded-lg shadow overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="sticky left-0 bg-gray-50 px-3 py-2 text-left font-semibold min-w-[140px] z-10 border-r">
                        {fullMonthNames[mi]}
                      </th>
                      {dayNumbers.map(day => (
                        <th key={day} className={`px-0 py-2 text-center font-semibold w-8 min-w-[28px] ${isWeekend(mi, day) ? 'bg-gray-200 text-gray-500' : ''}`}>
                          {day}
                        </th>
                      ))}
                      <th className="px-2 py-2 text-center font-semibold min-w-[40px] border-l">Tage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {displayData.map(emp => {
                      const { dayMap, posMap, approvedCount } = processEmployee(emp, mi);
                      if (hideEmpty && !processEmployee(emp, mi).hasAny) return null;
                      return (
                        <tr key={emp.employee_id} className="hover:bg-gray-50/50">
                          <td className="sticky left-0 bg-white px-3 py-1 font-medium text-sm z-10 border-r">
                            <div className="leading-tight">{emp.name}</div>
                            <div className="text-[10px] text-gray-400">{emp.personal_nr}</div>
                          </td>
                          {dayNumbers.map(day => {
                            const d = dayMap[day];
                            const we = isWeekend(mi, day);
                            if (!d) {
                              return <td key={day} className={`px-0 py-1 ${we ? 'bg-gray-100' : ''}`}></td>;
                            }
                            const pos = posMap[day] || 'single';
                            const isApprovedUrlaub = d.status === 'approved' && d.type !== 'abwesenheit';
                            const isPending = d.status === 'pending';
                            const isAbwesenheit = d.status === 'approved' && d.type === 'abwesenheit';

                            let roundCls = 'rounded';
                            if (pos === 'first') roundCls = 'rounded-l';
                            else if (pos === 'last') roundCls = 'rounded-r';
                            else if (pos === 'middle') roundCls = '';

                            let colorCls = '';
                            let extraStyle = {};
                            if (isApprovedUrlaub) {
                              colorCls = `bg-blue-400 text-white ${roundCls}`;
                            } else if (isPending) {
                              colorCls = `bg-orange-300 border-dashed border-2 border-orange-500 ${roundCls}`;
                            } else if (isAbwesenheit) {
                              colorCls = `text-white ${roundCls}`;
                              extraStyle = {
                                background: 'repeating-linear-gradient(135deg, #a855f7, #a855f7 3px, #9333ea 3px, #9333ea 6px)',
                              };
                            }

                            return (
                              <td key={day} className={`px-0 py-1 ${we ? 'bg-gray-100' : ''}`}>
                                <div
                                  className={`h-6 flex items-center justify-center text-[10px] font-bold ${colorCls}`}
                                  style={extraStyle}
                                  title={`${new Date(calYear, mi, day).toLocaleDateString('de-DE')} — ${
                                    isApprovedUrlaub ? 'Genehmigt' : isPending ? 'Offen' : 'Abwesenheit'
                                  }`}
                                >
                                  {day}
                                </div>
                              </td>
                            );
                          })}
                          <td className="px-2 py-1 text-center font-bold text-sm border-l">
                            {approvedCount}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            );
          })}

          {/* Legende */}
          <div className="flex gap-5 p-3 bg-white rounded-lg shadow text-xs text-gray-600 flex-wrap">
            <span className="flex items-center gap-1">
              <span className="w-5 h-5 bg-blue-400 text-white rounded text-[9px] text-center leading-5 font-bold inline-block">5</span>
              Genehmigt (Urlaub)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-5 h-5 bg-orange-300 border-dashed border-2 border-orange-500 rounded text-[9px] text-center leading-4 font-bold inline-block">3</span>
              Offen (ausstehend)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-5 h-5 rounded text-white text-[9px] text-center leading-5 font-bold inline-block"
                style={{ background: 'repeating-linear-gradient(135deg, #a855f7, #a855f7 3px, #9333ea 3px, #9333ea 6px)' }}>A</span>
              Abwesenheit
            </span>
            <span className="flex items-center gap-1">
              <span className="w-5 h-5 bg-gray-200 rounded text-[9px] text-center leading-5 inline-block"></span>
              Wochenende
            </span>
          </div>
        </>
        );
      })()}

      {/* Recalc Ergebnis Modal */}
      {recalcResults && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-lg max-h-[80vh] overflow-auto">
            <h3 className="text-lg font-bold mb-4">Urlaubssaetze - Referenzwerte (§ 11 BUrlG)</h3>
            <p className="text-xs text-gray-500 mb-2">Durchschnittsverdienst pro Arbeitstag der letzten 13 Wochen</p>
            <p className="text-xs text-orange-600 mb-3 font-medium">Nur Referenzwert aktualisiert - bereits gebuchte Urlaubstage bleiben unveraendert.</p>
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left">Mitarbeiter</th>
                  <th className="px-3 py-2 text-right">Alt</th>
                  <th className="px-3 py-2 text-right">Neu</th>
                  <th className="px-3 py-2 text-center">Gebucht</th>
                  <th className="px-3 py-2 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {recalcResults.map((r, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-3 py-2">{r.name}</td>
                    <td className="px-3 py-2 text-right">{r.old_rate != null ? `${Number(r.old_rate).toFixed(2)} €` : '-'}</td>
                    <td className="px-3 py-2 text-right font-medium">{r.new_rate != null ? `${Number(r.new_rate).toFixed(2)} €` : '-'}</td>
                    <td className="px-3 py-2 text-center text-xs">{r.booked_days != null ? `${r.booked_days} Tage` : '-'}</td>
                    <td className="px-3 py-2 text-center">
                      {r.status === 'updated' ? (
                        <span className="text-green-600 text-xs font-medium">Aktualisiert</span>
                      ) : (
                        <span className="text-gray-400 text-xs" title={r.reason}>Uebersprungen</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button
              onClick={() => setRecalcResults(null)}
              className="mt-4 w-full px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
            >
              Schliessen
            </button>
          </div>
        </div>
      )}

      {/* Korrektur-Vorschau-Modal */}
      {correctionPreview && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[85vh] overflow-auto">
            <h3 className="text-lg font-bold mb-2">Urlaubssaetze korrigieren - Vorschau</h3>
            <p className="text-xs text-gray-500 mb-1">Neuberechnung nach § 11 BUrlG (13 Wochen vor Urlaubsbeginn)</p>
            <p className="text-xs text-orange-600 mb-3 font-medium">Abgerechnete Monate werden uebersprungen.</p>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-sm">
              <span className="font-medium">{correctionPreview.total_entries} Eintraege</span> bei {correctionPreview.results.length} MA betroffen &middot;
              Gesamtdifferenz: <span className={`font-bold ${correctionPreview.total_diff >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                {correctionPreview.total_diff >= 0 ? '+' : ''}{correctionPreview.total_diff.toFixed(2)} EUR
              </span>
            </div>

            {correctionPreview.results.map((r, i) => (
              <div key={i} className="mb-4">
                <div className="flex justify-between items-center bg-gray-50 px-3 py-2 rounded-t font-medium text-sm">
                  <span>{r.personal_nr} {r.name}</span>
                  <span className={`text-xs ${r.total_diff >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                    {r.total_diff >= 0 ? '+' : ''}{r.total_diff.toFixed(2)} EUR ({r.count} Tage)
                  </span>
                </div>
                <table className="w-full text-xs border border-gray-200">
                  <thead>
                    <tr className="bg-gray-100">
                      <th className="px-2 py-1 text-left">Datum</th>
                      <th className="px-2 py-1 text-right">Alt</th>
                      <th className="px-2 py-1 text-right">Neu</th>
                      <th className="px-2 py-1 text-right">Diff</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {r.entries.map((e, j) => (
                      <tr key={j}>
                        <td className="px-2 py-1">{new Date(e.date + 'T00:00').toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })}</td>
                        <td className="px-2 py-1 text-right">{e.old_rate.toFixed(2)} EUR</td>
                        <td className="px-2 py-1 text-right font-medium">{e.new_rate.toFixed(2)} EUR</td>
                        <td className={`px-2 py-1 text-right ${e.diff >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                          {e.diff >= 0 ? '+' : ''}{e.diff.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}

            <div className="flex gap-2 mt-4">
              <button
                onClick={async () => {
                  setCorrectionLoading(true);
                  try {
                    await api.post('/vacation/admin/recalc-vacation-entries', { preview: false, year });
                    showToast(`${correctionPreview.total_entries} Urlaubssaetze korrigiert`, 'success');
                    setCorrectionPreview(null);
                    loadData();
                  } catch (error) {
                    showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
                  } finally {
                    setCorrectionLoading(false);
                  }
                }}
                disabled={correctionLoading}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50"
              >
                {correctionLoading ? 'Wird geschrieben...' : `${correctionPreview.total_entries} Eintraege korrigieren`}
              </button>
              <button
                onClick={() => setCorrectionPreview(null)}
                className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit-Modal */}
      {editModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">Urlaub bearbeiten</h3>
            <p className="text-sm text-gray-600 mb-1">{editModal.employee_name}</p>
            <p className="text-xs text-gray-400 mb-4">
              Status: {getStatusBadge(editModal.status).label}
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Von</label>
                <input
                  type="date"
                  value={editModal.start_date}
                  onChange={(e) => setEditModal({ ...editModal, start_date: e.target.value })}
                  className="w-full p-2 border rounded-lg"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Bis</label>
                <input
                  type="date"
                  value={editModal.end_date}
                  onChange={(e) => setEditModal({ ...editModal, end_date: e.target.value })}
                  className="w-full p-2 border rounded-lg"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setEditModal(null)}
                className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
              <button
                onClick={() => handleSaveOnly(editModal)}
                className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center justify-center gap-1"
              >
                <Check size={16} /> Speichern
              </button>
              {editModal.status !== 'approved' && (
                <button
                  onClick={() => handleSaveAndApprove(editModal)}
                  className="flex-1 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center justify-center gap-1"
                >
                  <Check size={16} /> Speichern + Genehmigen
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Neuer Eintrag Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">Urlaub / Abwesenheit eintragen</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Mitarbeiter</label>
                <select
                  value={createForm.employee_id}
                  onChange={(e) => setCreateForm({ ...createForm, employee_id: parseInt(e.target.value) || '' })}
                  className="w-full p-2 border rounded-lg"
                >
                  <option value="">Bitte waehlen...</option>
                  {employees.map(emp => (
                    <option key={emp.id} value={emp.id}>{emp.first_name} {emp.last_name} ({emp.personal_nr})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Typ</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCreateForm({ ...createForm, type: 'urlaub' })}
                    className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border-2 transition-colors ${
                      createForm.type === 'urlaub'
                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                        : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Urlaub (bezahlt)
                  </button>
                  <button
                    onClick={() => setCreateForm({ ...createForm, type: 'abwesenheit' })}
                    className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border-2 transition-colors ${
                      createForm.type === 'abwesenheit'
                        ? 'border-orange-500 bg-orange-50 text-orange-700'
                        : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Abwesenheit (unbezahlt)
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium mb-1">Von</label>
                  <input
                    type="date"
                    value={createForm.start_date}
                    onChange={(e) => setCreateForm({ ...createForm, start_date: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Bis</label>
                  <input
                    type="date"
                    value={createForm.end_date}
                    onChange={(e) => setCreateForm({ ...createForm, end_date: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                  />
                </div>
              </div>

              {createForm.type === 'abwesenheit' && (
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-800">
                  Abwesenheit wird NICHT vom Urlaubskonto abgezogen. 0h gebucht, unbezahlt.
                </div>
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => { setShowCreateModal(false); setCreateForm({ employee_id: '', start_date: '', end_date: '', type: 'urlaub' }); }}
                className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
              <button
                onClick={handleCreate}
                disabled={createLoading}
                className="flex-1 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 font-medium"
              >
                {createLoading ? 'Speichern...' : 'Eintragen'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 text-white text-sm font-medium flex items-center gap-2
          ${toast.type === 'success' ? 'bg-green-500' : ''}
          ${toast.type === 'error' ? 'bg-red-500' : ''}
          ${toast.type === 'info' ? 'bg-blue-500' : ''}
        `}>
          {toast.type === 'success' && <Check size={18} />}
          {toast.type === 'error' && <X size={18} />}
          {toast.message}
        </div>
      )}
    </div>
  );
};

export default UrlaubVerwaltungTab;
