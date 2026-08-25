// ScheduleTab.jsx - Dienstplan mit Wochen- und Monatsansicht, Objekt-Farben, Filtern
// V2.0 - Modernes Design
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Calendar, Clock, Users, Copy, AlertCircle, Check, X, Edit2, UserPlus, Car, FileText, Repeat, ChevronLeft, ChevronRight, Plus, Filter, LayoutGrid, List, Flag } from 'lucide-react';
import api from "../services/api";

// Farbpalette fuer Objekte - kraeftigere Akzentfarben
const COLOR_PALETTE = [
  { accent: '#3b82f6', bg: 'bg-blue-50',  text: 'text-blue-700',  dot: 'bg-blue-500',  badge: 'bg-blue-100 text-blue-700',  ring: 'ring-blue-200' },
  { accent: '#10b981', bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500', badge: 'bg-emerald-100 text-emerald-700', ring: 'ring-emerald-200' },
  { accent: '#f59e0b', bg: 'bg-amber-50', text: 'text-amber-700', dot: 'bg-amber-500', badge: 'bg-amber-100 text-amber-700', ring: 'ring-amber-200' },
  { accent: '#8b5cf6', bg: 'bg-violet-50', text: 'text-violet-700', dot: 'bg-violet-500', badge: 'bg-violet-100 text-violet-700', ring: 'ring-violet-200' },
  { accent: '#ec4899', bg: 'bg-pink-50', text: 'text-pink-700', dot: 'bg-pink-500', badge: 'bg-pink-100 text-pink-700', ring: 'ring-pink-200' },
  { accent: '#14b8a6', bg: 'bg-teal-50', text: 'text-teal-700', dot: 'bg-teal-500', badge: 'bg-teal-100 text-teal-700', ring: 'ring-teal-200' },
  { accent: '#f97316', bg: 'bg-orange-50', text: 'text-orange-700', dot: 'bg-orange-500', badge: 'bg-orange-100 text-orange-700', ring: 'ring-orange-200' },
  { accent: '#e11d48', bg: 'bg-rose-50', text: 'text-rose-700', dot: 'bg-rose-500', badge: 'bg-rose-100 text-rose-700', ring: 'ring-rose-200' },
  { accent: '#6366f1', bg: 'bg-indigo-50', text: 'text-indigo-700', dot: 'bg-indigo-500', badge: 'bg-indigo-100 text-indigo-700', ring: 'ring-indigo-200' },
  { accent: '#06b6d4', bg: 'bg-cyan-50', text: 'text-cyan-700', dot: 'bg-cyan-500', badge: 'bg-cyan-100 text-cyan-700', ring: 'ring-cyan-200' },
  { accent: '#84cc16', bg: 'bg-lime-50', text: 'text-lime-700', dot: 'bg-lime-500', badge: 'bg-lime-100 text-lime-700', ring: 'ring-lime-200' },
  { accent: '#d946ef', bg: 'bg-fuchsia-50', text: 'text-fuchsia-700', dot: 'bg-fuchsia-500', badge: 'bg-fuchsia-100 text-fuchsia-700', ring: 'ring-fuchsia-200' },
  { accent: '#0ea5e9', bg: 'bg-sky-50', text: 'text-sky-700', dot: 'bg-sky-500', badge: 'bg-sky-100 text-sky-700', ring: 'ring-sky-200' },
  { accent: '#7c3aed', bg: 'bg-purple-50', text: 'text-purple-700', dot: 'bg-purple-500', badge: 'bg-purple-100 text-purple-700', ring: 'ring-purple-200' },
];

const statusConfig = {
  normal: { icon: null, label: 'Normal', color: '' },
  urlaub: { icon: '\u{1F3D6}\u{FE0F}', label: 'Urlaub', color: 'bg-amber-100 text-amber-700' },
  abwesend: { icon: '\u{1F6AB}', label: 'Abwesend', color: 'bg-orange-100 text-orange-700' },
  krank: { icon: '\u{1F912}', label: 'Krank', color: 'bg-red-100 text-red-700' },
  vertretung: { icon: '\u2194\u{FE0F}', label: 'Vertretung', color: 'bg-blue-100 text-blue-700' },
  storniert: { icon: '\u274C', label: 'Storniert', color: 'bg-gray-100 text-gray-500' },
};

const WEEKDAY_NAMES = {
  0: 'Montag', 1: 'Dienstag', 2: 'Mittwoch', 3: 'Donnerstag',
  4: 'Freitag', 5: 'Samstag', 6: 'Sonntag'
};
const WEEKDAY_SHORT = { 0: 'Mo', 1: 'Di', 2: 'Mi', 3: 'Do', 4: 'Fr', 5: 'Sa', 6: 'So' };

const MONTH_NAMES = [
  'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
];

// --- Modal Wrapper Komponente ---
const Modal = ({ isOpen, onClose, children, size = 'md' }) => {
  if (!isOpen) return null;
  const sizeClass = size === 'lg' ? 'max-w-2xl' : size === 'sm' ? 'max-w-sm' : 'max-w-lg';
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" onClick={onClose}>
      <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm transition-opacity" />
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          className={`relative ${sizeClass} w-full bg-white rounded-2xl shadow-2xl ring-1 ring-black/5 max-h-[90vh] overflow-y-auto transform transition-all`}
          onClick={(e) => e.stopPropagation()}
        >
          {children}
        </div>
      </div>
    </div>
  );
};

const ScheduleTab = () => {
  // View mode
  const [viewMode, setViewMode] = useState('week');

  // Week state
  const [weekOffset, setWeekOffset] = useState(0);
  const [weekData, setWeekData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Month state
  const [monthOffset, setMonthOffset] = useState(0);
  const [monthData, setMonthData] = useState(null);
  const [loadingMonth, setLoadingMonth] = useState(false);

  // Filters
  const [filterEmployee, setFilterEmployee] = useState('');
  const [filterObject, setFilterObject] = useState('');

  // Conflicts
  const [conflicts, setConflicts] = useState([]);

  // Modals
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDayDetail, setShowDayDetail] = useState(null);

  // Generate from Stamm
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [generatePreview, setGeneratePreview] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generateResult, setGenerateResult] = useState(null);
  const [genOverwrite, setGenOverwrite] = useState(false);

  // Add shift
  const [newShiftData, setNewShiftData] = useState({
    dayIndex: null, weekday: null, employee_id: '', object_id: '',
    start_time: '06:00', end_time: '14:00', notes: '', is_driver: true,
  });

  // Edit shift
  const [editingSchedule, setEditingSchedule] = useState(null);

  // Edit modal extras
  const [includeSaturday, setIncludeSaturday] = useState(false);
  const [repeatEnabled, setRepeatEnabled] = useState(false);
  const [repeatUntil, setRepeatUntil] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [splitPartnerOpen, setSplitPartnerOpen] = useState(false);

  // Error
  const [scheduleError, setScheduleError] = useState(null);

  // Konflikte aufklappbar
  const [conflictsOpen, setConflictsOpen] = useState(false);

  const todayStr = new Date().toISOString().split('T')[0];

  // Conflict-Schedule-IDs
  const conflictScheduleIds = useMemo(() => {
    const ids = new Set();
    conflicts.forEach(c => (c.schedule_ids || []).forEach(id => ids.add(id)));
    return ids;
  }, [conflicts]);

  // Objekt-Farben-Map
  const objectColorMap = useMemo(() => {
    const objects = [...(weekData?.objects || monthData?.objects || [])];
    const map = {};
    objects.sort((a, b) => a.id - b.id).forEach((obj, i) => {
      map[obj.id] = COLOR_PALETTE[i % COLOR_PALETTE.length];
    });
    return map;
  }, [weekData?.objects, monthData?.objects]);

  const getObjectColor = (objectId) => objectColorMap[objectId] || COLOR_PALETTE[0];

  // --- Data Loading ---
  const loadWeekData = async () => {
    setLoading(true);
    try {
      const response = await api.get(`/admin/schedules/week?week_offset=${weekOffset}`);
      setWeekData(response.data);
      const conflictResponse = await api.get(`/admin/schedules/conflicts?week_offset=${weekOffset}`);
      setConflicts(conflictResponse.data.conflicts || []);
    } catch (error) {
      console.error('Fehler beim Laden der Wochendaten:', error);
    }
    setLoading(false);
  };

  const loadMonthData = async () => {
    setLoadingMonth(true);
    try {
      const now = new Date();
      let targetMonth = now.getMonth() + 1 + monthOffset;
      let targetYear = now.getFullYear();
      while (targetMonth > 12) { targetMonth -= 12; targetYear++; }
      while (targetMonth < 1) { targetMonth += 12; targetYear--; }
      const res = await api.get(`/admin/schedules/month?month=${targetMonth}&year=${targetYear}`);
      setMonthData(res.data);
    } catch (error) {
      console.error('Fehler beim Laden der Monatsdaten:', error);
    }
    setLoadingMonth(false);
  };

  useEffect(() => { if (viewMode === 'week') loadWeekData(); }, [weekOffset, viewMode]);
  useEffect(() => { if (viewMode === 'month') loadMonthData(); }, [monthOffset, viewMode]);

  // --- Helpers ---
  const showScheduleError = (msg) => {
    setScheduleError(msg);
    setTimeout(() => setScheduleError(null), 8000);
  };

  const showAction = (msg) => {
    setActionMessage(msg);
    setTimeout(() => setActionMessage(''), 4000);
  };

  const getObjectDayCount = (daySchedules, objectId) => daySchedules.filter(s => s.object_id === objectId).length;

  const calcHours = (startStr, endStr) => {
    if (!startStr || !endStr) return '\u2014';
    const s = startStr.split(':');
    const e = endStr.split(':');
    const h = (parseInt(e[0]) - parseInt(s[0])) + (parseInt(e[1]) - parseInt(s[1])) / 60;
    return isNaN(h) ? '\u2014' : h.toFixed(1);
  };

  const filterSchedules = (schedules) => {
    return schedules.filter(s => {
      if (filterEmployee && s.employee_id != filterEmployee) return false;
      if (filterObject && s.object_id != filterObject) return false;
      return true;
    });
  };

  // --- Actions ---
  const toggleDriver = async (scheduleId, currentVal) => {
    try {
      await api.post('/admin/schedules/bulk-update', [{ id: scheduleId, is_driver: !currentVal }]);
      loadWeekData();
    } catch (e) { console.error('Fahrer-Toggle fehlgeschlagen:', e); }
  };

  const toggleLastShift = async (scheduleId, currentVal) => {
    try {
      await api.post('/admin/schedules/bulk-update', [{ id: scheduleId, is_last_shift_of_month: !currentVal }]);
      if (viewMode === 'week') loadWeekData(); else loadMonthData();
    } catch (e) { console.error('Letzte-Schicht-Toggle fehlgeschlagen:', e); }
  };

  const handleObjectChange = (objectId, isEdit = false) => {
    if (!objectId) return;

    const data = weekData || monthData;
    const obj = data?.objects?.find(o => o.id == objectId);

    // Zeiten aus v2 (times_by_weekday) pro Wochentag
    const dayIndex = isEdit ? editingSchedule?.dayIndex : newShiftData?.dayIndex;
    const dateStr = (viewMode === 'week' ? weekData : monthData)?.days?.[dayIndex]?.date;
    let startTime = '';
    let endTime = '';
    let noTimesWarning = false;

    if (dateStr && obj?.times_by_weekday) {
      const jsDay = new Date(dateStr + 'T00:00:00').getDay();
      const backendWeekday = (jsDay + 6) % 7; // JS: 0=So → Backend: 0=Mo
      const match = obj.times_by_weekday[backendWeekday];
      if (match && match.start && match.end) {
        startTime = match.start;
        endTime = match.end;
      } else {
        noTimesWarning = true;
      }
    }

    // Fallback: Objekt-Default (erster v2-Eintrag)
    if (!startTime || !endTime) {
      startTime = obj?.start_time ? obj.start_time.substring(0, 5) : '';
      endTime = obj?.end_time ? obj.end_time.substring(0, 5) : '';
    }

    if (noTimesWarning && obj) {
      const dayName = dateStr ? ['Sonntag','Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag'][new Date(dateStr + 'T00:00:00').getDay()] : 'diesen Tag';
      alert(`Hinweis: Fuer ${obj.name} sind keine Sollzeiten fuer ${dayName} hinterlegt. Bitte Zeiten manuell eingeben oder Sollzeiten im Objekt pflegen.`);
    }

    if (isEdit && editingSchedule) {
      setEditingSchedule(prev => ({ ...prev, object_id: objectId, start_time: startTime, end_time: endTime }));
    } else {
      setNewShiftData(prev => ({ ...prev, object_id: objectId, start_time: startTime, end_time: endTime }));
    }
  };

  const openAddShiftModal = (dayIndex, weekday) => {
    setNewShiftData({ dayIndex, weekday, employee_id: '', object_id: '', start_time: '06:00', end_time: '14:00', notes: '', is_driver: true });
    setShowAddModal(true);
    setScheduleError(null);
  };

  const openEditModal = (schedule, dayIndex) => {
    setEditingSchedule({
      ...schedule, dayIndex,
      date: weekData?.days?.[dayIndex]?.date || schedule.date,
      status: schedule?.status || 'normal',
      notes: schedule.notes || '',
      is_driver: schedule.is_driver || false,
      partner_schedule_id: schedule.partner_schedule_id || null,
      partner_employee_name: schedule.partner_employee_name || null,
      partner_employee_id: schedule.partner_employee_id || null,
      original_planned_hours: schedule.original_planned_hours || null,
      original_end_time: schedule.original_end_time || null,
    });
    setShowEditModal(true);
    setSplitPartnerOpen(!!(schedule.partner_schedule_id));
    setRepeatEnabled(false);
    setRepeatUntil('');
    setIncludeSaturday(false);
    setActionMessage('');
    setScheduleError(null);
  };

  const saveNewShift = async () => {
    if (!newShiftData.employee_id || !newShiftData.object_id) { alert('Bitte Mitarbeiter und Objekt auswaehlen'); return; }
    try {
      await api.post('/admin/schedules/quick-assign', {
        employee_id: parseInt(newShiftData.employee_id),
        object_id: parseInt(newShiftData.object_id),
        date: weekData?.days[newShiftData.dayIndex]?.date,
        start_time: newShiftData.start_time,
        end_time: newShiftData.end_time,
        notes: newShiftData.notes,
        is_driver: newShiftData.is_driver,
      });
      setShowAddModal(false);
      await loadWeekData();
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (error.response?.status === 409 && detail) showScheduleError(detail);
      else showScheduleError('Fehler beim Hinzufuegen der Schicht');
    }
  };

  const saveEditedShift = async () => {
    try {
      await api.post('/admin/schedules/bulk-update', [{
        id: editingSchedule.id,
        employee_id: parseInt(editingSchedule.employee_id),
        object_id: parseInt(editingSchedule.object_id),
        start_time: editingSchedule.start_time,
        end_time: editingSchedule.end_time,
        status: editingSchedule?.status || 'normal',
        date: editingSchedule.date,
        is_driver: editingSchedule.is_driver,
        is_last_shift_of_month: editingSchedule.is_last_shift_of_month || false,
        notes: editingSchedule.notes || '',
      }]);
      setShowEditModal(false);
      await loadWeekData();
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (error.response?.status === 409 && detail) { showScheduleError(detail); setShowEditModal(false); }
      else showScheduleError('Fehler beim Speichern');
    }
  };

  const deleteShift = async (scheduleId) => {
    try {
      await api.delete(`/admin/schedules/${scheduleId}`);
      await loadWeekData();
    } catch (error) { console.error('Fehler beim Loeschen:', error); }
  };

  const copyWeek = async (targetWeekOffset) => {
    try {
      // Montag der aktuellen Woche berechnen (getDay: 0=So, 1=Mo...6=Sa)
      // Sonntag (0) muss als 7 behandelt werden damit wir auf den AKTUELLEN Montag kommen
      const sourceDate = new Date();
      const srcDay = sourceDate.getDay() || 7; // Sonntag=0 -> 7
      sourceDate.setDate(sourceDate.getDate() - srcDay + 1);
      sourceDate.setDate(sourceDate.getDate() + (weekOffset * 7));
      const targetDate = new Date();
      const tgtDay = targetDate.getDay() || 7;
      targetDate.setDate(targetDate.getDate() - tgtDay + 1);
      targetDate.setDate(targetDate.getDate() + (targetWeekOffset * 7));
      await api.post('/admin/schedules/copy-week', { source_week: sourceDate.toISOString(), target_week: targetDate.toISOString() });
      setWeekOffset(targetWeekOffset);
      await loadWeekData();
      setShowCopyModal(false);
    } catch (error) { console.error('Fehler beim Kopieren:', error); }
  };

  const copyShiftToWeek = async () => {
    try {
      const res = await api.post('/admin/schedules/copy-to-week', {
        schedule_id: editingSchedule.id,
        include_saturday: includeSaturday,
      });
      showAction(res.data.message);
      await loadWeekData();
      setShowEditModal(false);
    } catch (error) { showScheduleError(error.response?.data?.detail || 'Fehler beim Kopieren'); }
  };

  const repeatShift = async () => {
    if (!repeatUntil) { alert('Bitte Enddatum waehlen'); return; }
    try {
      const res = await api.post('/admin/schedules/repeat', {
        schedule_id: editingSchedule.id,
        until_date: repeatUntil,
      });
      showAction(res.data.message);
      await loadWeekData();
      setShowEditModal(false);
    } catch (error) { showScheduleError(error.response?.data?.detail || 'Fehler bei Wiederholung'); }
  };

  const createReplacement = async (replacementEmployeeId) => {
    try {
      await api.post('/admin/schedules/replacement', {
        original_schedule_id: editingSchedule.id,
        replacement_employee_id: parseInt(replacementEmployeeId),
        reason: editingSchedule?.status || 'normal',
      });
      await loadWeekData();
      setShowEditModal(false);
      showAction('Vertretung wurde angelegt!');
    } catch (err) { showScheduleError('Fehler: ' + (err.response?.data?.detail || err.message)); }
  };

  const createSplitShift = async (partnerEmployeeId) => {
    try {
      const res = await api.post('/admin/schedules/split-shift', {
        schedule_id: editingSchedule.id,
        partner_employee_id: parseInt(partnerEmployeeId),
      });
      showAction(res.data.message);
      await loadWeekData();
      setShowEditModal(false);
    } catch (err) { showScheduleError(err.response?.data?.detail || 'Fehler beim Teilen'); }
  };

  const unsplitShift = async () => {
    if (!confirm('Schicht wirklich wieder einzeln machen? Der Partner-Eintrag wird geloescht.')) return;
    try {
      const res = await api.post('/admin/schedules/unsplit-shift', {
        schedule_id: editingSchedule.id,
      });
      showAction(res.data.message);
      await loadWeekData();
      setShowEditModal(false);
    } catch (err) { showScheduleError(err.response?.data?.detail || 'Fehler beim Aufheben'); }
  };

  const openDayDetail = (dayData) => {
    setShowDayDetail(dayData);
  };

  // --- Stabile sortierte Listen ---
  const currentEmployees = useMemo(() => {
    return [...((viewMode === 'week' ? weekData?.employees : monthData?.employees) || [])];
  }, [viewMode, weekData?.employees, monthData?.employees]);

  const currentObjects = useMemo(() => {
    return [...((viewMode === 'week' ? weekData?.objects : monthData?.objects) || [])];
  }, [viewMode, weekData?.objects, monthData?.objects]);

  const employeesByName = useMemo(() => [...currentEmployees].sort((a, b) => a.name.localeCompare(b.name)), [currentEmployees]);
  const employeesById = useMemo(() => [...currentEmployees].sort((a, b) => a.id - b.id), [currentEmployees]);
  const objectsByName = useMemo(() => [...currentObjects].sort((a, b) => a.name.localeCompare(b.name)), [currentObjects]);
  const objectsById = useMemo(() => [...currentObjects].sort((a, b) => a.id - b.id), [currentObjects]);

  // ESC-Taste schliesst alle Modals
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (showEditModal) setShowEditModal(false);
        else if (showAddModal) setShowAddModal(false);
        else if (showCopyModal) setShowCopyModal(false);
        else if (showDayDetail) setShowDayDetail(null);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [showEditModal, showAddModal, showCopyModal, showDayDetail]);

  // --- Loading ---
  if (viewMode === 'week' && loading && !weekData) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-blue-500 border-t-transparent"></div>
      </div>
    );
  }

  // --- Schicht-Card Komponente (Wochenansicht) ---
  const ShiftCard = ({ schedule, daySchedules, dayIndex }) => {
    const isConflict = conflictScheduleIds.has(schedule.id);
    const maCount = getObjectDayCount(daySchedules, schedule.object_id);
    const objColor = getObjectColor(schedule.object_id);
    const status = statusConfig[schedule?.status] || statusConfig.normal;

    return (
      <div
        className={`group relative rounded-lg cursor-pointer transition-all duration-150 hover:scale-[1.02] hover:shadow-lg ${isConflict ? 'ring-2 ring-red-500 ring-offset-1' : ''}`}
        style={{ backgroundColor: objColor.accent + '18', borderLeft: `3px solid ${objColor.accent}` }}
        onClick={() => openEditModal(schedule, dayIndex)}
      >
        <div className="px-2 py-1.5">
          {/* Name + Icons */}
          <div className="flex items-center justify-between gap-1">
            <span className="font-bold text-[12px] truncate" style={{ color: objColor.accent }}>{schedule.employee_name}</span>
            <div className="flex items-center gap-0.5 flex-shrink-0">
              {isConflict && <AlertCircle size={11} className="text-red-500" />}
              {status.icon && <span className="text-[11px]" title={status.label}>{status.icon}</span>}
              {schedule.is_driver && <Car size={11} style={{ color: objColor.accent }} />}
              {schedule.is_last_shift_of_month && <Flag size={11} className="text-orange-500" title="Letzte Schicht des Monats" />}
              {schedule.notes && <FileText size={9} className="text-gray-400" title={schedule.notes} />}
            </div>
          </div>

          {/* Objekt + Zeit in einer Zeile */}
          <div className="flex items-center justify-between mt-0.5">
            <span className="text-[10px] font-semibold text-gray-600 truncate">{schedule.object_name}</span>
            <div className="flex items-center gap-1 flex-shrink-0">
              {maCount >= 2 && (
                <span className="text-[9px] font-bold text-purple-500">{maCount}x</span>
              )}
              <span className="text-[10px] text-gray-500 font-medium">{schedule.start_time}-{schedule.end_time}</span>
            </div>
          </div>

          {/* Vertretung */}
          {schedule.replacement_for && (
            <div className="text-[9px] text-blue-500 mt-0.5 font-medium">Vertr. MA-{schedule.replacement_for}</div>
          )}
          {/* Zu zweit Badge */}
          {schedule.partner_schedule_id && (
            <div className="flex items-center gap-0.5 mt-0.5">
              <span className="inline-flex items-center gap-0.5 text-[9px] font-bold text-purple-600 bg-purple-100 px-1 py-0.5 rounded">
                <Users size={8} /> Zu zweit
              </span>
            </div>
          )}
        </div>
      </div>
    );
  };

  // ======================== RENDER ========================
  return (
    <div className="bg-white min-h-screen">
      {/* ===== HEADER ===== */}
      <div className="bg-white border-b sticky top-0 z-10">
        <div className="px-4 sm:px-6 py-3">
          {/* Zeile 1: Toggle + Nav + Actions */}
          <div className="flex items-center justify-between gap-4">
            {/* Links: View Toggle */}
            <div className="flex items-center gap-4">
              <div className="inline-flex bg-gray-100 rounded-lg p-0.5">
                <button
                  onClick={() => setViewMode('week')}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${viewMode === 'week' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                >
                  <List size={14} /> Woche
                </button>
                <button
                  onClick={() => setViewMode('month')}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${viewMode === 'month' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                >
                  <LayoutGrid size={14} /> Monat
                </button>
              </div>

              {/* Navigation */}
              {viewMode === 'week' && weekData && (
                <div className="flex items-center gap-1">
                  <button onClick={() => setWeekOffset(weekOffset - 1)} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"><ChevronLeft size={18} /></button>
                  <button onClick={() => setWeekOffset(0)} className="px-3 py-1 rounded-lg hover:bg-blue-50 text-sm font-bold text-gray-800 transition-colors whitespace-nowrap">
                    KW {weekData.week_number}<span className="text-gray-400 font-normal ml-1">/{weekData.year}</span>
                  </button>
                  <button onClick={() => setWeekOffset(weekOffset + 1)} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"><ChevronRight size={18} /></button>
                </div>
              )}
              {viewMode === 'month' && monthData && (
                <div className="flex items-center gap-1">
                  <button onClick={() => setMonthOffset(monthOffset - 1)} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"><ChevronLeft size={18} /></button>
                  <button onClick={() => setMonthOffset(0)} className="px-3 py-1 rounded-lg hover:bg-blue-50 text-sm font-bold text-gray-800 transition-colors whitespace-nowrap">
                    {MONTH_NAMES[monthData.month - 1]} {monthData.year}
                  </button>
                  <button onClick={() => setMonthOffset(monthOffset + 1)} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"><ChevronRight size={18} /></button>
                </div>
              )}
            </div>

            {/* Rechts: Actions */}
            <div className="flex items-center gap-2">
              {viewMode === 'week' && (
                <button onClick={() => setShowCopyModal(true)} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800 text-xs font-medium transition-colors">
                  <Copy size={13} /> Kopieren
                </button>
              )}
              {viewMode === 'month' && monthData && (
                <button
                  onClick={() => { setGeneratePreview(null); setGenerateResult(null); setGenOverwrite(false); setShowGenerateModal(true); }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-xs font-medium transition-colors"
                >
                  <Plus size={13} /> Aus Stamm generieren
                </button>
              )}
              <button
                onClick={viewMode === 'week' ? loadWeekData : loadMonthData}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                title="Aktualisieren"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
              </button>
            </div>
          </div>

          {/* Zeile 2: Filter + Legende */}
          <div className="flex items-center justify-between gap-3 mt-2.5 pt-2.5 border-t border-gray-100">
            <div className="flex items-center gap-2">
              <Filter size={13} className="text-gray-400" />
              <select
                value={filterEmployee}
                onChange={(e) => setFilterEmployee(e.target.value)}
                className="text-xs border-0 bg-gray-100 rounded-lg py-1.5 px-2.5 text-gray-700 focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
              >
                <option value="">Alle Mitarbeiter</option>
                {employeesByName.map(emp => (
                  <option key={emp.id} value={emp.id}>{emp.personal_nr} - {emp.name}</option>
                ))}
              </select>
              <select
                value={filterObject}
                onChange={(e) => setFilterObject(e.target.value)}
                className="text-xs border-0 bg-gray-100 rounded-lg py-1.5 px-2.5 text-gray-700 focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
              >
                <option value="">Alle Objekte</option>
                {objectsByName.map(obj => (
                  <option key={obj.id} value={obj.id}>{obj.name}</option>
                ))}
              </select>
              {(filterEmployee || filterObject) && (
                <button onClick={() => { setFilterEmployee(''); setFilterObject(''); }} className="text-xs text-red-500 hover:text-red-700 transition-colors">
                  <X size={14} />
                </button>
              )}
            </div>

            {/* Mini-Legende */}
            <div className="hidden lg:flex items-center gap-2 text-[10px] text-gray-400">
              {objectsByName.slice(0, 6).map(obj => {
                const c = getObjectColor(obj.id);
                return (
                  <span key={obj.id} className="inline-flex items-center gap-1">
                    <span className={`w-2 h-2 rounded-full ${c.dot}`}></span>
                    <span className="truncate max-w-[60px]">{obj.name}</span>
                  </span>
                );
              })}
              {objectsByName.length > 6 && <span>+{objectsByName.length - 6}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Inhalt mit Padding */}
      <div className="px-4 sm:px-6 py-4">
        {/* Error / Action Messages */}
        {scheduleError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-3 mb-4 flex items-start gap-3 animate-in">
            <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-sm">
              <span className="font-semibold text-red-800">Fehler: </span>
              <span className="text-red-600">{scheduleError}</span>
            </div>
            <button type="button" onClick={() => setScheduleError(null)} className="text-red-300 hover:text-red-500 transition-colors"><X size={16} /></button>
          </div>
        )}
        {actionMessage && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 mb-4 text-emerald-700 text-sm font-medium flex items-center gap-2 animate-in">
            <Check size={16} className="text-emerald-500" /> {actionMessage}
          </div>
        )}

        {/* Conflicts - aufklappbar */}
        {viewMode === 'week' && conflicts.length > 0 && (
          <button
            type="button"
            onClick={() => setConflictsOpen(!conflictsOpen)}
            className="w-full mb-3 text-left"
          >
            <div className="flex items-center gap-2 px-3 py-1.5 bg-red-50 rounded-lg hover:bg-red-100 transition-colors">
              <span className="w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">{conflicts.length}</span>
              <span className="text-xs font-semibold text-red-700">Konflikte</span>
              <ChevronRight size={14} className={`text-red-400 ml-auto transition-transform ${conflictsOpen ? 'rotate-90' : ''}`} />
            </div>
            {conflictsOpen && (
              <div className="mt-1 px-3 py-2 bg-red-50/50 rounded-lg text-[11px] text-red-600 space-y-0.5" onClick={(e) => e.stopPropagation()}>
                {conflicts.map((c, i) => (
                  <div key={i}>
                    <strong>{c.employee}</strong>: {c.weekday || ''} - {c.shift1?.object} {c.shift1?.time} / {c.shift2?.object} {c.shift2?.time}
                  </div>
                ))}
              </div>
            )}
          </button>
        )}

        {/* ===================== WOCHENANSICHT ===================== */}
        {viewMode === 'week' && weekData && (
          <div className="bg-white rounded-2xl shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <div className="grid grid-cols-7 min-w-[840px]">
                {/* Tag-Header */}
                {weekData.days.map((day, index) => {
                  const isToday = day.date === todayStr;
                  const dateObj = new Date(day.date);
                  const count = filterSchedules(day.schedules).length;
                  return (
                    <div key={index} className={`text-center py-3 ${isToday ? 'bg-blue-600' : 'bg-gray-800'} ${index > 0 ? 'border-l border-white/10' : ''}`}>
                      <div className={`text-[10px] font-bold uppercase tracking-widest ${isToday ? 'text-blue-200' : 'text-gray-400'}`}>
                        {day.weekday.substring(0, 2)}
                      </div>
                      <div className={`text-xl font-black ${isToday ? 'text-white' : 'text-white'}`}>
                        {dateObj.getDate()}
                      </div>
                      <div className={`text-[9px] mt-0.5 ${isToday ? 'text-blue-200' : 'text-gray-500'}`}>
                        {count} {count === 1 ? 'Schicht' : 'Schichten'}
                      </div>
                    </div>
                  );
                })}

                {/* Schichten pro Tag */}
                {weekData.days.map((day, dayIndex) => {
                  const isToday = day.date === todayStr;
                  const filtered = [...filterSchedules(day.schedules)].sort((a, b) => a.start_time.localeCompare(b.start_time));
                  return (
                    <div
                      key={dayIndex}
                      className={`p-1.5 min-h-[140px] ${isToday ? 'bg-blue-50/30' : dayIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50/40'} ${dayIndex > 0 ? 'border-l border-gray-100' : ''}`}
                    >
                      <div className="space-y-1">
                        {filtered.map((schedule) => (
                          <ShiftCard key={schedule.id} schedule={schedule} daySchedules={day.schedules} dayIndex={dayIndex} />
                        ))}

                        {/* Neue Schicht */}
                        <button
                          onClick={() => openAddShiftModal(dayIndex, day.weekday_index)}
                          className="w-full py-1.5 rounded-lg border border-dashed border-gray-200 text-gray-300 hover:text-blue-500 hover:border-blue-300 hover:bg-blue-50/50 transition-all flex items-center justify-center gap-1 text-[10px]"
                        >
                          <Plus size={12} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Volle Legende unter Wochenansicht */}
        {viewMode === 'week' && weekData && (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[11px] text-gray-500">
            {objectsByName.map(obj => {
              const c = getObjectColor(obj.id);
              return (
                <span key={obj.id} className="inline-flex items-center gap-1">
                  <span className={`w-2.5 h-2.5 rounded ${c.dot}`}></span>
                  {obj.name}
                </span>
              );
            })}
            <span className="border-l pl-3 inline-flex items-center gap-1"><Car size={11} className="text-blue-500" /> Fahrer</span>
            <span className="inline-flex items-center gap-1"><Users size={11} className="text-purple-500" /> Mehrere MA</span>
          </div>
        )}

        {/* ===================== MONATSANSICHT ===================== */}
        {viewMode === 'month' && (
          <>
            {loadingMonth && !monthData ? (
              <div className="flex justify-center items-center h-64">
                <div className="animate-spin rounded-full h-10 w-10 border-2 border-blue-500 border-t-transparent"></div>
              </div>
            ) : monthData ? (
              <div className="bg-white rounded-2xl shadow-md overflow-hidden">
                {(() => {
                  const firstDayOfMonth = new Date(monthData.year, monthData.month - 1, 1);
                  const startWeekday = (firstDayOfMonth.getDay() + 6) % 7;
                  const daysInMonth = monthData.days.length;
                  const totalCells = startWeekday + daysInMonth;
                  const rows = Math.ceil(totalCells / 7);

                  return (
                    <>
                      {/* Wochentag-Header */}
                      <div className="grid grid-cols-7 bg-gray-800">
                        {['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map((d, i) => (
                          <div key={d} className={`text-center py-2 text-[10px] font-bold uppercase tracking-widest text-gray-400 ${i > 0 ? 'border-l border-white/10' : ''}`}>{d}</div>
                        ))}
                      </div>
                      {/* Tage */}
                      {Array.from({ length: rows }).map((_, rowIdx) => (
                        <div key={rowIdx} className="grid grid-cols-7 border-b border-gray-100 last:border-b-0">
                          {Array.from({ length: 7 }).map((_, colIdx) => {
                            const cellIndex = rowIdx * 7 + colIdx;
                            const dayIdx = cellIndex - startWeekday;
                            const dayData = dayIdx >= 0 && dayIdx < daysInMonth ? monthData.days[dayIdx] : null;

                            if (!dayData) {
                              return <div key={colIdx} className={`h-[100px] bg-gray-50/50 ${colIdx > 0 ? 'border-l border-gray-100' : ''}`}></div>;
                            }

                            const isToday = dayData.date === todayStr;
                            const filtered = filterSchedules(dayData.schedules);
                            const dayNum = new Date(dayData.date).getDate();
                            const isWeekend = colIdx >= 5;
                            const maxShow = 4;

                            return (
                              <div
                                key={colIdx}
                                className={`h-[100px] p-1 cursor-pointer hover:bg-blue-50/30 transition-colors relative ${colIdx > 0 ? 'border-l border-gray-100' : ''} ${isToday ? 'bg-blue-50' : isWeekend ? 'bg-gray-50/50' : 'bg-white'}`}
                                onClick={() => openDayDetail(dayData)}
                              >
                                {isToday && <div className="absolute top-0 left-0 right-0 h-[3px] bg-blue-500 rounded-b" />}

                                <div className="flex items-center justify-between mb-0.5">
                                  <div className="flex items-center gap-1">
                                    <span className={`text-[11px] font-bold ${isToday ? '' : 'text-gray-600'}`}>
                                      {isToday ? (
                                        <span className="bg-blue-600 text-white w-5 h-5 rounded-full inline-flex items-center justify-center text-[10px]">{dayNum}</span>
                                      ) : dayNum}
                                    </span>
                                    <span className={`text-[9px] font-bold ${colIdx === 5 ? 'text-orange-500' : colIdx === 6 ? 'text-red-500' : 'text-gray-400'}`}>
                                      {['Mo','Di','Mi','Do','Fr','Sa','So'][colIdx]}
                                    </span>
                                  </div>
                                  {filtered.length > 0 && (
                                    <span className="text-[8px] text-gray-400 font-medium">{filtered.length}x</span>
                                  )}
                                </div>
                                <div className="space-y-0.5">
                                  {filtered.slice(0, maxShow).map(s => {
                                    const c = getObjectColor(s.object_id);
                                    return (
                                      <div key={s.id} className="rounded px-1 py-px text-[9px] leading-tight truncate font-medium" style={{ backgroundColor: c.accent + '20', color: c.accent, borderLeft: `2px solid ${c.accent}` }}>
                                        {s.employee_name.split(' ')[0]} {s.start_time} <span style={{ opacity: 0.7 }}>{(s.object_name || '').substring(0, 6)}</span>
                                      </div>
                                    );
                                  })}
                                  {filtered.length > maxShow && (
                                    <div className="text-[9px] text-blue-600 font-bold px-1">+{filtered.length - maxShow}</div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ))}
                    </>
                  );
                })()}
              </div>
            ) : (
              <div className="text-gray-400 text-center py-12">Keine Daten verfuegbar</div>
            )}

            {/* Legende Monat */}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[11px] text-gray-500">
              {objectsByName.map(obj => {
                const c = getObjectColor(obj.id);
                return (
                  <span key={obj.id} className="inline-flex items-center gap-1">
                    <span className={`w-2.5 h-2.5 rounded ${c.dot}`}></span>
                    {obj.name}
                  </span>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* ===================== COPY WEEK MODAL ===================== */}
      <Modal isOpen={showCopyModal} onClose={() => setShowCopyModal(false)} size="sm">
        <div className="p-6">
          <h3 className="text-base font-bold text-gray-900 mb-1">Woche kopieren</h3>
          <p className="text-sm text-gray-500 mb-4">KW {weekData?.week_number} uebertragen nach:</p>
          <div className="grid grid-cols-2 gap-2">
            {[1, 2, 3, 4].map(n => (
              <button key={n} type="button" onClick={() => copyWeek(weekOffset + n)} className="p-2.5 bg-gray-900 text-white rounded-xl hover:bg-gray-800 text-sm font-medium transition-colors">
                {n === 1 ? 'Naechste Woche' : `In ${n} Wochen`}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => setShowCopyModal(false)} className="mt-3 w-full p-2 text-gray-500 hover:text-gray-700 text-sm transition-colors">Abbrechen</button>
        </div>
      </Modal>

      {/* ===================== ADD SHIFT MODAL ===================== */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)}>
        <div className="p-6">
          <div className="flex justify-between items-center mb-5">
            <div>
              <h3 className="text-base font-bold text-gray-900">Neue Schicht</h3>
              <p className="text-xs text-gray-500 mt-0.5">{WEEKDAY_NAMES[newShiftData.dayIndex]}</p>
            </div>
            <button type="button" onClick={() => setShowAddModal(false)} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"><X size={18} /></button>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Mitarbeiter</label>
              <select value={newShiftData.employee_id} onChange={(e) => setNewShiftData({ ...newShiftData, employee_id: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors">
                <option value="">-- Auswaehlen --</option>
                {employeesById.filter(e => e.is_active !== false).map(emp => (
                  <option key={emp.id} value={emp.id}>{emp.personal_nr} - {emp.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Objekt</label>
              <select value={newShiftData.object_id} onChange={(e) => handleObjectChange(e.target.value, false)} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors">
                <option value="">-- Auswaehlen --</option>
                {objectsById.filter(o => o.is_active !== false).map(obj => (
                  <option key={obj.id} value={obj.id}>{obj.name} {obj.customer_name && `(${obj.customer_name})`}</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Von</label>
                <input type="time" value={newShiftData.start_time} onChange={(e) => setNewShiftData({ ...newShiftData, start_time: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Bis</label>
                <input type="time" value={newShiftData.end_time} onChange={(e) => setNewShiftData({ ...newShiftData, end_time: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>

            <div className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2">
              <span className="text-sm text-gray-600">{calcHours(newShiftData.start_time, newShiftData.end_time)} Stunden</span>
              <button
                type="button"
                onClick={() => setNewShiftData({ ...newShiftData, is_driver: !newShiftData.is_driver })}
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${newShiftData.is_driver ? 'bg-blue-100 text-blue-700' : 'bg-white text-gray-400 hover:text-gray-600'}`}
              >
                <Car size={12} /> {newShiftData.is_driver ? 'Fahrer' : 'Kein Fahrer'}
              </button>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Notizen</label>
              <textarea value={newShiftData.notes} onChange={(e) => setNewShiftData({ ...newShiftData, notes: e.target.value })} placeholder="Optional..." rows={2} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 resize-none" />
            </div>
          </div>

          <div className="flex justify-end gap-2 mt-5 pt-4 border-t border-gray-100">
            <button type="button" onClick={() => setShowAddModal(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors">Abbrechen</button>
            <button type="button" onClick={saveNewShift} className="px-5 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm font-medium transition-colors">Hinzufuegen</button>
          </div>
        </div>
      </Modal>

      {/* ===================== EDIT SHIFT MODAL ===================== */}
      <Modal isOpen={showEditModal && !!editingSchedule} onClose={() => setShowEditModal(false)} size="lg">
        {editingSchedule && (
          <div className="flex flex-col max-h-[85vh]">
          <div className="overflow-y-auto flex-1 p-6 pb-2">
            <div className="flex justify-between items-start mb-5">
              <div>
                <h3 className="text-base font-bold text-gray-900">Schicht bearbeiten</h3>
                <p className="text-xs text-gray-500 mt-0.5">{WEEKDAY_NAMES[editingSchedule.dayIndex]} - {editingSchedule.date && new Date(editingSchedule.date).toLocaleDateString('de-DE')}</p>
              </div>
              <button type="button" onClick={() => setShowEditModal(false)} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"><X size={18} /></button>
            </div>

            {/* Aktionsmeldung im Modal */}
            {actionMessage && (
              <div className="bg-emerald-50 rounded-xl p-2.5 mb-4 text-emerald-700 text-xs font-medium flex items-center gap-2">
                <Check size={14} /> {actionMessage}
              </div>
            )}

            <div className="space-y-4">
              {/* MA + Objekt + Status */}
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Mitarbeiter</label>
                  <select value={editingSchedule.employee_id} onChange={(e) => setEditingSchedule({ ...editingSchedule, employee_id: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500">
                    {employeesById.map(emp => (
                      <option key={emp.id} value={emp.id}>{emp.personal_nr} - {emp.name}</option>
                    ))}
                  </select>
                </div>
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Objekt</label>
                  <select value={editingSchedule.object_id} onChange={(e) => handleObjectChange(e.target.value, true)} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500">
                    {objectsById.map(obj => (
                      <option key={obj.id} value={obj.id}>{obj.name} {obj.customer_name && `(${obj.customer_name})`}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Status + Datum */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Status</label>
                  <select value={editingSchedule?.status || 'normal'} onChange={(e) => setEditingSchedule({ ...editingSchedule, status: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500">
                    <option value="normal">Normal</option>
                    <option value="urlaub">Urlaub</option>
                    <option value="abwesend">Abwesend</option>
                    <option value="krank">Krank</option>
                    <option value="vertretung">Vertretung</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Datum</label>
                  <input type="date" value={editingSchedule.date || ''} onChange={(e) => setEditingSchedule({ ...editingSchedule, date: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500" />
                </div>
              </div>

              {/* Zeit */}
              <div className="grid grid-cols-3 gap-3 items-end">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Von</label>
                  <input type="time" value={editingSchedule.start_time} onChange={(e) => setEditingSchedule({ ...editingSchedule, start_time: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Bis</label>
                  <input type="time" value={editingSchedule.end_time} onChange={(e) => setEditingSchedule({ ...editingSchedule, end_time: e.target.value })} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500" />
                </div>
                <div className="flex items-center gap-3 pb-0.5">
                  <span className="text-sm font-bold text-gray-700">{calcHours(editingSchedule.start_time, editingSchedule.end_time)}h</span>
                  <button
                    type="button"
                    onClick={() => setEditingSchedule({ ...editingSchedule, is_driver: !editingSchedule.is_driver })}
                    className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${editingSchedule.is_driver ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-400 hover:text-gray-600'}`}
                  >
                    <Car size={12} /> {editingSchedule.is_driver ? 'Fahrer' : 'Nein'}
                  </button>
                </div>
              </div>

              {/* Letzte Schicht des Monats */}
              <div className="flex items-center justify-between bg-orange-50 rounded-xl px-3 py-2">
                <span className="text-sm text-gray-700 font-medium">Letzte Schicht diesen Monat</span>
                <button
                  type="button"
                  onClick={() => setEditingSchedule({ ...editingSchedule, is_last_shift_of_month: !editingSchedule.is_last_shift_of_month })}
                  className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${editingSchedule.is_last_shift_of_month ? 'bg-orange-500 text-white' : 'bg-white text-gray-400 hover:text-gray-600 border border-gray-200'}`}
                >
                  <Flag size={12} /> {editingSchedule.is_last_shift_of_month ? 'Markiert' : 'Nicht markiert'}
                </button>
              </div>

              {/* Notizen */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Notizen</label>
                <textarea value={editingSchedule.notes || ''} onChange={(e) => setEditingSchedule({ ...editingSchedule, notes: e.target.value })} placeholder="Optional..." rows={2} className="w-full px-3 py-2 bg-gray-50 border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 resize-none" />
              </div>

              {/* Zu zweit arbeiten */}
              <div className="bg-purple-50 rounded-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setSplitPartnerOpen(!splitPartnerOpen)}
                  className="w-full flex items-center justify-between px-3 py-2.5 text-sm font-semibold text-purple-700 hover:bg-purple-100 transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Users size={14} /> Zu zweit arbeiten
                    {editingSchedule.partner_schedule_id && (
                      <span className="text-[10px] bg-purple-200 text-purple-800 px-1.5 py-0.5 rounded-full font-bold">aktiv</span>
                    )}
                  </span>
                  <ChevronRight size={14} className={`transition-transform ${splitPartnerOpen ? 'rotate-90' : ''}`} />
                </button>
                {splitPartnerOpen && (
                  <div className="px-3 pb-3 space-y-2">
                    {editingSchedule.partner_schedule_id ? (
                      <>
                        <div className="flex items-center justify-between bg-white rounded-lg px-3 py-2">
                          <div>
                            <span className="text-xs text-gray-500">Partner:</span>
                            <span className="text-sm font-medium text-gray-800 ml-1">{editingSchedule.partner_employee_name}</span>
                          </div>
                          <span className="text-xs text-purple-600 font-bold">
                            je {editingSchedule.planned_hours}h ({editingSchedule.start_time}-{editingSchedule.end_time})
                            {editingSchedule.original_planned_hours && <span className="text-gray-400 font-normal"> von {editingSchedule.original_planned_hours}h</span>}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={unsplitShift}
                          className="w-full px-3 py-2 bg-red-50 text-red-600 rounded-lg text-xs font-medium hover:bg-red-100 transition-colors"
                        >
                          Einzeln machen (Partner entfernen)
                        </button>
                      </>
                    ) : (
                      <>
                        <p className="text-xs text-purple-600">Partner auswaehlen - Stunden werden halbiert:</p>
                        <select
                          defaultValue=""
                          onChange={(e) => { if (e.target.value) createSplitShift(e.target.value); }}
                          className="w-full px-3 py-2 bg-white border-0 rounded-xl text-sm focus:ring-2 focus:ring-purple-500"
                        >
                          <option value="">-- Partner auswaehlen --</option>
                          {employeesByName.filter(e => e.id != editingSchedule.employee_id && e.is_active !== false).map(emp => (
                            <option key={emp.id} value={emp.id}>{emp.personal_nr} - {emp.name}</option>
                          ))}
                        </select>
                        <p className="text-[10px] text-purple-400">
                          Aktuelle Stunden: {editingSchedule.planned_hours}h → je {(editingSchedule.planned_hours / 2).toFixed(1)}h
                        </p>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Vertretung - nur bei krank/urlaub */}
              {(editingSchedule?.status === 'krank' || editingSchedule?.status === 'urlaub') && (
                <div className="bg-blue-50 rounded-xl p-3">
                  <label className="block text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1.5">Vertretung anlegen</label>
                  <select
                    defaultValue=""
                    onChange={(e) => { if (e.target.value) createReplacement(e.target.value); }}
                    className="w-full px-3 py-2 bg-white border-0 rounded-xl text-sm focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">-- Vertreter auswaehlen --</option>
                    {employeesByName.filter(e => e.id != editingSchedule.employee_id && e.is_active !== false).map(emp => (
                      <option key={emp.id} value={emp.id}>{emp.personal_nr} - {emp.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Erweiterte Aktionen */}
              <div className="border-t border-gray-100 pt-3 space-y-2">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Erweitert</p>

                {/* Ganze Woche */}
                <div className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2.5">
                  <span className="text-sm text-gray-700">Ganze Woche uebernehmen</span>
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-gray-400 flex items-center gap-1 cursor-pointer">
                      <input type="checkbox" checked={includeSaturday} onChange={(e) => setIncludeSaturday(e.target.checked)} className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                      +Sa
                    </label>
                    <button type="button" onClick={copyShiftToWeek} className="inline-flex items-center gap-1 px-3 py-1.5 bg-gray-900 text-white rounded-lg text-xs font-medium hover:bg-gray-800 transition-colors">
                      <Copy size={12} /> Mo-{includeSaturday ? 'Sa' : 'Fr'}
                    </button>
                  </div>
                </div>

                {/* Wiederholung */}
                <div className="bg-gray-50 rounded-xl px-3 py-2.5">
                  <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                    <input type="checkbox" checked={repeatEnabled} onChange={(e) => setRepeatEnabled(e.target.checked)} className="rounded border-gray-300 text-purple-600 focus:ring-purple-500" />
                    <Repeat size={13} className="text-gray-400" /> Woechentlich wiederholen
                  </label>
                  {repeatEnabled && (
                    <div className="flex items-center gap-2 mt-2 ml-6">
                      <span className="text-xs text-gray-500">Bis:</span>
                      <input type="date" value={repeatUntil} onChange={(e) => setRepeatUntil(e.target.value)} className="px-2 py-1 bg-white border-0 rounded-lg text-xs focus:ring-2 focus:ring-purple-500" />
                      <button type="button" onClick={repeatShift} className="px-3 py-1 bg-purple-600 text-white rounded-lg text-xs font-medium hover:bg-purple-700 transition-colors">Erstellen</button>
                    </div>
                  )}
                </div>
              </div>
            </div>

          </div>
          {/* Sticky Footer Buttons */}
          <div className="sticky bottom-0 bg-white border-t border-gray-100 px-6 py-3 flex justify-between rounded-b-2xl">
              <button
                type="button"
                onClick={async () => { if (confirm('Schicht wirklich loeschen?')) { await deleteShift(editingSchedule.id); setShowEditModal(false); } }}
                className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-xl text-sm font-medium transition-colors"
              >
                Loeschen
              </button>
              <div className="flex gap-2">
                <button type="button" onClick={() => setShowEditModal(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors">Abbrechen</button>
                <button type="button" onClick={saveEditedShift} className="px-5 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm font-medium transition-colors">Speichern</button>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* ===================== DAY DETAIL MODAL (Monatsansicht) ===================== */}
      <Modal isOpen={!!showDayDetail} onClose={() => setShowDayDetail(null)}>
        {showDayDetail && (
          <div className="p-6">
            <div className="flex justify-between items-center mb-5">
              <div>
                <h3 className="text-base font-bold text-gray-900">
                  {showDayDetail.weekday}
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  {new Date(showDayDetail.date).toLocaleDateString('de-DE', { day: '2-digit', month: 'long', year: 'numeric' })}
                </p>
              </div>
              <button type="button" onClick={() => setShowDayDetail(null)} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"><X size={18} /></button>
            </div>

            {(() => {
              const filtered = filterSchedules(showDayDetail.schedules || []);
              if (filtered.length === 0) {
                return <div className="text-gray-400 text-center py-10 text-sm">Keine Schichten an diesem Tag</div>;
              }
              return (
                <div className="space-y-2">
                  {[...filtered].sort((a, b) => a.start_time.localeCompare(b.start_time)).map(s => {
                    const objColor = getObjectColor(s.object_id);
                    const status = statusConfig[s.status] || statusConfig.normal;
                    return (
                      <div key={s.id} className="rounded-xl overflow-hidden transition-all hover:scale-[1.01]" style={{ backgroundColor: objColor.accent + '15', borderLeft: `4px solid ${objColor.accent}` }}>
                        <div className="px-3 py-2.5">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-sm" style={{ color: objColor.accent }}>{s.employee_name}</span>
                            <div className="flex items-center gap-1.5">
                              {status.icon && <span className="text-xs">{status.icon}</span>}
                              {s.is_driver && <Car size={13} style={{ color: objColor.accent }} />}
                              {s.is_last_shift_of_month && <Flag size={13} className="text-orange-500" title="Letzte Schicht des Monats" />}
                              {s.status && s.status !== 'normal' && (
                                <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium ${status.color}`}>{status.label}</span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-3 mt-1">
                            <span className="text-xs font-semibold text-gray-600">{s.object_name}</span>
                            <span className="text-xs text-gray-500 flex items-center gap-1">
                              <Clock size={10} /> {s.start_time} - {s.end_time}
                              <span className="font-semibold">({s.planned_hours}h)</span>
                            </span>
                          </div>
                          {s.notes && (
                            <div className="mt-1.5 text-[11px] text-gray-400 flex items-center gap-1">
                              <FileText size={10} /> {s.notes}
                            </div>
                          )}
                          {s.replacement_for && (
                            <div className="mt-1 text-[10px] font-medium" style={{ color: objColor.accent }}>Vertretung fuer MA-{s.replacement_for}</div>
                          )}
                          {s.partner_schedule_id && (
                            <div className="mt-1 inline-flex items-center gap-0.5 text-[10px] font-bold text-purple-600 bg-purple-100 px-1.5 py-0.5 rounded">
                              <Users size={9} /> Zu zweit{s.partner_employee_name ? ` mit ${s.partner_employee_name}` : ''}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })()}

            <div className="mt-4 pt-3 border-t border-gray-100 text-center">
              <span className="text-xs text-gray-400">{filterSchedules(showDayDetail.schedules || []).length} Schicht(en)</span>
            </div>
          </div>
        )}
      </Modal>

      {/* === Generate from Stamm Modal === */}
      <Modal isOpen={showGenerateModal} onClose={() => setShowGenerateModal(false)} size="lg">
        <div className="p-5">
          <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Plus size={20} className="text-green-600" /> Aus Stamm-Dienstplan generieren
          </h3>

          {!generatePreview && !generateResult && (
            <div>
              <p className="text-sm text-gray-600 mb-4">
                Generiert Schichten fuer <strong>{monthData ? `${MONTH_NAMES[monthData.month - 1]} ${monthData.year}` : ''}</strong> basierend auf dem Stamm-Dienstplan.
              </p>
              <label className="flex items-center gap-2 mb-4 cursor-pointer">
                <input type="checkbox" checked={genOverwrite} onChange={e => setGenOverwrite(e.target.checked)} className="w-4 h-4" />
                <span className="text-sm">Bestehende Schichten aktualisieren (Overwrite)</span>
              </label>
              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    setGenerating(true);
                    try {
                      const res = await api.post('/admin/master-schedule/generate', {
                        month: monthData.month, year: monthData.year, overwrite: genOverwrite, dry_run: true
                      });
                      setGeneratePreview(res.data);
                    } catch (err) {
                      alert(err.response?.data?.detail || 'Fehler');
                    }
                    setGenerating(false);
                  }}
                  disabled={generating}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
                >
                  {generating ? 'Lade...' : 'Vorschau laden'}
                </button>
                <button onClick={() => setShowGenerateModal(false)} className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-sm">Abbrechen</button>
              </div>
            </div>
          )}

          {generatePreview && !generateResult && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm text-gray-600">
                  <strong>{generatePreview.total}</strong> Schichten werden erstellt, <strong>{generatePreview.skipped}</strong> uebersprungen
                </p>
                <button onClick={() => setGeneratePreview(null)} className="text-xs text-blue-600 hover:underline">Zurueck</button>
              </div>

              {generatePreview.conflicts?.length > 0 && (
                <div className="mb-3 p-2 bg-red-50 rounded-lg text-xs text-red-700">
                  <strong>Konflikte:</strong> {generatePreview.conflicts.slice(0, 3).map((c, i) => <div key={i}>{c}</div>)}
                </div>
              )}

              <div className="max-h-80 overflow-y-auto border rounded-lg mb-4">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left font-semibold">Mitarbeiter</th>
                      <th className="px-3 py-2 text-left font-semibold">Datum</th>
                      <th className="px-3 py-2 text-left font-semibold">Objekt</th>
                      <th className="px-3 py-2 text-center font-semibold">Zeit</th>
                      <th className="px-3 py-2 text-center font-semibold">Std.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {generatePreview.preview?.map((item, idx) => (
                      <tr key={idx} className={item.action === 'update' ? 'bg-amber-50' : 'hover:bg-gray-50'}>
                        <td className="px-3 py-1.5">
                          <span className="font-medium">{item.employee_name}</span>
                          <span className="text-gray-400 ml-1">{item.personal_nr}</span>
                        </td>
                        <td className="px-3 py-1.5">
                          {item.weekday_name}, {new Date(item.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}
                        </td>
                        <td className="px-3 py-1.5">{item.object_name}</td>
                        <td className="px-3 py-1.5 text-center">{item.start_time}-{item.end_time}</td>
                        <td className="px-3 py-1.5 text-center font-medium">{item.planned_hours}h</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    setGenerating(true);
                    try {
                      const res = await api.post('/admin/master-schedule/generate', {
                        month: monthData.month, year: monthData.year, overwrite: genOverwrite, dry_run: false
                      });
                      setGenerateResult(res.data);
                      loadMonthData();
                    } catch (err) {
                      alert(err.response?.data?.detail || 'Fehler');
                    }
                    setGenerating(false);
                  }}
                  disabled={generating || generatePreview.total === 0}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium disabled:opacity-50"
                >
                  {generating ? 'Generiere...' : `${generatePreview.total} Schichten jetzt erstellen`}
                </button>
                <button onClick={() => setShowGenerateModal(false)} className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-sm">Abbrechen</button>
              </div>
            </div>
          )}

          {generateResult && (
            <div>
              <div className="p-4 bg-green-50 rounded-lg mb-4">
                <p className="text-green-800 font-medium flex items-center gap-2">
                  <Check size={18} /> {generateResult.message}
                </p>
              </div>
              <button onClick={() => setShowGenerateModal(false)} className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 text-sm font-medium">Schliessen</button>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default ScheduleTab;
