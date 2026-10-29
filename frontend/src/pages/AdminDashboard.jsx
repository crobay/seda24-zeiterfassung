import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, Building2, Calendar, Activity, FileText, Plus, Edit2, Trash2,
  Save, X, Check, CheckCircle, AlertCircle, LogOut, Search, Download, Upload,
  MapPin, Clock, Shield, Eye, EyeOff, ChevronDown, Filter, BookOpen, TrendingUp, Menu, Calculator, Bell, ClipboardList, Smartphone, Mail, Lock, MessageSquare, LogIn
} from 'lucide-react';
import ScheduleTab from "../components/ScheduleTab";
import AbrechnungenTab from "./AbrechnungenTab";
import KmJournalTab from "./KmJournalTab";
import KmVerwaltungTab from "../components/KmVerwaltungTab";
import LohnUebersichtTab from "./LohnUebersichtTab";
import OffenePunkteTab from "./OffenePunkteTab";
import AuditLogTab from "./AuditLogTab";
import LoginLogTab from "./LoginLogTab";
import MitarbeiterObjekteTab from "./MitarbeiterObjekteTab";
import PushVerwaltungTab from "./PushVerwaltungTab";
import UrlaubVerwaltungTab from "./UrlaubVerwaltungTab";
import KrankmeldungTab from "./KrankmeldungTab";
import PosteingangTab from "./PosteingangTab";
import StammDienstplanTab from "./StammDienstplanTab";
import KundenUmsaetzeTab from "./KundenUmsaetzeTab";
import StatistikenTab from "./StatistikenTab";
import MonatsbestaetigungenTab from "./MonatsbestaetigungenTab";
import GenehmigungenTab from "./GenehmigungenTab";
// SommerfestTab entfernt
import TelegramLogTab from "./TelegramLogTab";
import api from '../services/api';

  // Hilfsfunktion: Offline-Sync Verzögerung formatieren
  const formatDelay = (minutes) => {
    if (!minutes || minutes < 1) return '';
    if (minutes < 60) return `${minutes}min`;
    if (minutes < 1440) {
      const h = Math.floor(minutes / 60);
      const m = minutes % 60;
      return m > 0 ? `${h}h ${m}min` : `${h}h`;
    }
    const d = Math.floor(minutes / 1440);
    const h = Math.floor((minutes % 1440) / 60);
    return h > 0 ? `${d}d ${h}h` : `${d}d`;
  };

  // ==================== JOURNAL TAB (NEU!) ====================
  
  const JournalTab = React.memo(({ employees, customers, showToast, setShowKmModal, setKmBookingInfo, setKmDistance,
    selectedEmployee, setSelectedEmployee, dateFrom, setDateFrom, dateTo, setDateTo,
    selectedObject, setSelectedObject, selectedServiceType, setSelectedServiceType,
    selectedCleaningType, setSelectedCleaningType,
    selectedEntryType, setSelectedEntryType, sortField, setSortField, sortDirection, setSortDirection }) => {
    // Alle Objekte aus allen Kunden extrahieren (flache Liste)
    const allObjects = customers.flatMap(c =>
      (c.objects || []).filter(o => o.is_active !== false).map(obj => ({
        ...obj,
        customer_name: c.name
      }))
    );

    const [bookings, setBookings] = useState([]);
    const [filteredBookings, setFilteredBookings] = useState([]);
    const [loading, setLoading] = useState(false);
    const [activeQuick, setActiveQuick] = useState(null);
    // Reinigungsart-Optionen DYNAMISCH aus den vorhandenen service_type-Werten
    // (ohne die Buchungsarten Urlaub/Krank/Abwesenheit)
    const cleaningTypes = Array.from(new Set(bookings.map(b => b.service_type).filter(Boolean)))
      .filter(t => !['Urlaub', 'Krank', 'Abwesenheit'].includes(t))
      .sort();
    
    // Filter + Sort kommen jetzt aus Props (State lebt im Parent)
    
    // Modal States
    const [showEditModal, setShowEditModal] = useState(false);
    const [editingBooking, setEditingBooking] = useState(null);
    const [showNewBookingModal, setShowNewBookingModal] = useState(false);
    const [useCustomObject, setUseCustomObject] = useState(false);
    const [newBookingData, setNewBookingData] = useState({
      employee_id: '',
      object_id: '',
      custom_object_name: '',
      booking_date: new Date().toISOString().split('T')[0],
      check_in_time: '09:00',
      check_out_time: '17:00',
      billed_hours: 8.0,
      hourly_rate: '15.50',
      service_type: 'Unterhaltsreinigung',
      notes: ''
    });
  // Sollstunden laden für manuelle Buchung
  const loadScheduleForBooking = async (employeeId, objectId, bookingDate) => {
    if (!employeeId || !objectId || !bookingDate) return;
    try {
      const response = await api.get(`/admin/schedule/${employeeId}/${objectId}/${bookingDate}`);
      if (response.data) {
        const st = response.data.start_time || '09:00';
        const et = response.data.end_time || '17:00';
        const [h1,m1] = st.split(':').map(Number);
        const [h2,m2] = et.split(':').map(Number);
        const bh = Math.round(((h2*60+m2)-(h1*60+m1))/60*100)/100;
        setNewBookingData(prev => ({
          ...prev,
          check_in_time: st,
          check_out_time: et,
          billed_hours: bh,
          hourly_rate: response.data.hourly_rate || prev.hourly_rate
        }));
      }
    } catch (err) {
      setNewBookingData(prev => ({
        ...prev,
        check_in_time: '09:00',
        check_out_time: '17:00',
        billed_hours: 8.0
      }));
    }
  };

    
    // Checkbox State
    const [selectedIds, setSelectedIds] = useState(new Set());

    // Sort kommt aus Props

    useEffect(() => {
      loadBookings();
    }, []);

    useEffect(() => {
      applyFilters();
    }, [bookings, dateFrom, dateTo, selectedEmployee, selectedObject, selectedServiceType, selectedCleaningType, selectedEntryType, sortField, sortDirection]);

    const loadBookings = async () => {
      setLoading(true);
      try {
        const response = await api.get('/admin/bookings/all');
        setBookings(response.data);
      } catch (error) {
        showToast('Fehler beim Laden der Buchungen', 'error');
      } finally {
        setLoading(false);
      }
    };

    const applyFilters = () => {
      let filtered = [...bookings];

      if (dateFrom) {
        filtered = filtered.filter(b => new Date(b.check_in) >= new Date(dateFrom));
      }
      if (dateTo) {
        const toDate = new Date(dateTo);
        toDate.setHours(23, 59, 59);
        filtered = filtered.filter(b => new Date(b.check_in) <= toDate);
      }
      if (selectedEmployee !== 'all') {
        filtered = filtered.filter(b => b.employee_id === parseInt(selectedEmployee));
      }
      if (selectedObject !== 'all') {
        filtered = filtered.filter(b => b.object_id === parseInt(selectedObject));
      }
      if (selectedServiceType === 'Arbeit') {
        filtered = filtered.filter(b => !['Urlaub', 'Krank', 'Abwesenheit'].includes(b.service_type));
      } else if (selectedServiceType !== 'all') {
        filtered = filtered.filter(b => b.service_type === selectedServiceType);
      }
      if (selectedCleaningType && selectedCleaningType !== 'all') {
        filtered = filtered.filter(b => b.service_type === selectedCleaningType);
      }
      if (selectedEntryType !== 'all') {
        const isManual = selectedEntryType === 'manual';
        filtered = filtered.filter(b => b.is_manual_entry === isManual);
      }

      filtered.sort((a, b) => {
        let aVal = a[sortField];
        let bVal = b[sortField];
        
        if (sortField === 'check_in' || sortField === 'check_out') {
          aVal = new Date(aVal);
          bVal = new Date(bVal);
        }
        
        if (sortDirection === 'asc') {
          return aVal > bVal ? 1 : -1;
        } else {
          return aVal < bVal ? 1 : -1;
        }
      });

      setFilteredBookings(filtered);
      setSelectedIds(new Set());
    };

    const toggleSelect = (id) => {
      setSelectedIds(prev => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
    };

    const toggleSelectAll = () => {
      if (selectedIds.size === filteredBookings.length && filteredBookings.length > 0) {
        setSelectedIds(new Set());
      } else {
        setSelectedIds(new Set(filteredBookings.map(b => b.id)));
      }
    };

    const deleteSelected = async () => {
      if (selectedIds.size === 0) return;
      if (!window.confirm(`${selectedIds.size} Buchungen löschen?\n\nZugehörige KM-Fahrten werden ebenfalls gelöscht.`)) return;
      try {
        try {
          await api.post("/admin/bookings/bulk-delete", { ids: Array.from(selectedIds) });
        } catch (bulkErr) {
          const ids = Array.from(selectedIds);
          for (const id of ids) {
            await api.delete(`/admin/bookings/${id}`);
          }
        }
        showToast(`${selectedIds.size} Buchungen gelöscht`, 'success');
        setSelectedIds(new Set());
        loadBookings();
      } catch (error) {
        console.error("Delete Error:", error);
        showToast('Fehler beim Löschen', 'error');
      }
    };

    const handleSort = (field) => {
      if (sortField === field) {
        setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
      } else {
        setSortField(field);
        setSortDirection('desc');
      }
    };

    // Datum-Schnellfilter: setzt Von/Bis und merkt sich den aktiven Button
    const setQuickRange = (key) => {
      const fmt = (d) => d.toISOString().split('T')[0];
      const today = new Date();
      const from = new Date();
      if (key === '7') from.setDate(from.getDate() - 6);
      else if (key === '14') from.setDate(from.getDate() - 13);
      setDateFrom(fmt(from));
      setDateTo(fmt(today));
      setActiveQuick(key);
    };

    const handleEdit = (booking) => {
      setEditingBooking(booking);
      setShowEditModal(true);
    };

    const handleDelete = async (bookingId) => {
      if (!confirm('Buchung löschen?\n\nZugehörige KM-Fahrten werden ebenfalls gelöscht.\nDiese Aktion kann nicht rückgängig gemacht werden!')) {
        return;
      }

      try {
        const res = await api.delete(`/admin/bookings/${bookingId}`);
        const kmInfo = res.data?.km_deleted > 0 ? ` + ${res.data.km_deleted} KM-Fahrt(en)` : '';
        showToast(`Buchung gelöscht${kmInfo}`, 'success');
        loadBookings();
      } catch (error) {
        console.error('Delete Error:', error);
        showToast('Fehler beim Löschen', 'error');
      }
    };

    const handleSaveEdit = async () => {
      try {
        await api.put(`/admin/bookings/${editingBooking.id}`, editingBooking);
        showToast('Buchung aktualisiert', 'success');
        setShowEditModal(false);
        loadBookings();
      } catch (error) {
        showToast('Fehler beim Speichern', 'error');
      }
    };
    const handleSaveNewBooking = async () => {
      try {
        const bookingData = {
          employee_id: parseInt(newBookingData.employee_id),
          object_id: useCustomObject ? null : parseInt(newBookingData.object_id),
          custom_object_name: useCustomObject ? newBookingData.custom_object_name : null,
          check_in: `${newBookingData.booking_date}T${newBookingData.check_in_time}:00`,
          check_out: `${newBookingData.booking_date}T${newBookingData.check_out_time}:00`,
          billed_hours: newBookingData.billed_hours,
          hourly_rate: parseFloat(newBookingData.hourly_rate),
          service_type: newBookingData.service_type,
          notes: newBookingData.notes,
          is_manual_entry: true
        };
        const res = await api.post('/admin/bookings/manual', bookingData);
        setShowNewBookingModal(false);
        loadBookings();

        // KM-Logik: Auto-Buchen wenn Distanz hinterlegt, sonst Popup
        // WICHTIG: showToast() erst NACH der KM-Logik aufrufen, damit der
        // Re-Render die async-Funktion nicht unterbricht
        if (bookingData.service_type !== 'Urlaub') {
          const empName = employees.find(e => e.id === bookingData.employee_id)?.name || '';
          const objName = useCustomObject
            ? newBookingData.custom_object_name
            : (allObjects.find(o => o.id === bookingData.object_id)?.name || '');

          // Prüfe ob KM-Distanz für diesen MA + Objekt hinterlegt ist
          let autoBooked = false;
          if (!useCustomObject && bookingData.object_id) {
            try {
              const kmRes = await api.get(`/admin/km-distances/${bookingData.employee_id}`);
              const match = kmRes.data.find(d => d.object_id === bookingData.object_id);
              if (match && match.distance_km > 0) {
                // Auto-KM buchen
                await api.post('/admin/km/manual', {
                  employee_id: bookingData.employee_id,
                  object_id: bookingData.object_id,
                  date: newBookingData.booking_date,
                  time_entry_id: res.data.id,
                  distance_km: match.distance_km
                });
                const amount = (match.distance_km * 0.30).toFixed(2);
                showToast(`Buchung + KM automatisch gebucht: ${match.distance_km} km (${amount} EUR)`, 'success');
                autoBooked = true;
              }
            } catch (e) {
              console.error('KM-Auto-Check fehlgeschlagen:', e);
            }
          }

          if (!autoBooked) {
            showToast('Buchung erstellt', 'success');
            // Kein Auto-KM → Popup anzeigen
            setKmBookingInfo({
              booking_id: res.data.id,
              employee_id: bookingData.employee_id,
              object_id: bookingData.object_id || null,
              custom_object_name: useCustomObject ? newBookingData.custom_object_name : null,
              date: newBookingData.booking_date,
              employee_name: empName,
              object_name: objName
            });
            setKmDistance('');
            setShowKmModal(true);
          }
        } else {
          showToast('Buchung erstellt', 'success');
        }
      } catch (error) {
        showToast('Fehler beim Erstellen', 'error');
      }
    };

    const exportCSV = () => {
      const csvData = filteredBookings.map(b => ({
        Datum: new Date(b.check_in).toLocaleDateString('de-DE'),
        Mitarbeiter: b.employee_name,
        Objekt: b.object_name,
        'Von': new Date(b.check_in).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }),
        'Bis': b.check_out ? new Date(b.check_out).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : 'Offen',
        Stunden: b.billed_hours?.toFixed(2) || '0.00',
        Stundensatz: `${b.hourly_rate?.toFixed(2) || '0.00'}€`,
        Betrag: `${((b.billed_hours || 0) * (b.hourly_rate || 0)).toFixed(2)}€`,
        Art: b.service_type || 'Arbeit',
        Typ: b.is_manual_entry ? 'Manuell' : 'Auto',
        Notizen: b.notes || ''
      }));

      const csv = [
        Object.keys(csvData[0]).join(';'),
        ...csvData.map(row => Object.values(row).join(';'))
      ].join('\n');

      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `journal_${new Date().toISOString().split('T')[0]}.csv`;
      link.click();
    };

    const calculateTotals = () => {
      const totalHours = filteredBookings.reduce((sum, b) => sum + (b.billed_hours || 0), 0);
      const totalAmount = filteredBookings.reduce((sum, b) => 
        sum + ((b.billed_hours || 0) * (b.hourly_rate || 0)), 0
      );
      return { totalHours, totalAmount };
    };

    const { totalHours, totalAmount } = calculateTotals();

    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold">Buchungsjournal</h2>
            <p className="text-gray-600">{filteredBookings.length} Buchungen gefunden</p>
          </div>
          <button
            onClick={exportCSV}
            disabled={filteredBookings.length === 0}
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2 disabled:bg-gray-300"
          >
            <Download size={20} />
            CSV Export
          </button>
        </div>
          <button
            onClick={() => setShowNewBookingModal(true)}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
          >
            <Plus size={20} />
            Neue Buchung
          </button>

        {/* Filter */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="font-semibold mb-4">Filter</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Von Datum</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setActiveQuick(null); }}
                className="w-full p-2 border rounded-lg"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Bis Datum</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setActiveQuick(null); }}
                className="w-full p-2 border rounded-lg"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Mitarbeiter</label>
              <select
                value={selectedEmployee}
                onChange={(e) => setSelectedEmployee(e.target.value)}
                className="w-full p-2 border rounded-lg"
              >
                <option value="all">Alle</option>
                {employees.map(emp => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Objekt</label>
              <select
                value={selectedObject}
                onChange={(e) => setSelectedObject(e.target.value)}
                className="w-full p-2 border rounded-lg"
              >
                <option value="all">Alle</option>
                {allObjects.map(obj => (
                  <option key={obj.id} value={obj.id}>
                    {obj.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Buchungsart</label>
              <select
                value={selectedServiceType}
                onChange={(e) => setSelectedServiceType(e.target.value)}
                className="w-full p-2 border rounded-lg"
              >
                <option value="Arbeit">Arbeit</option>
                <option value="all">Alle</option>
                <option value="Urlaub">Urlaub</option>
                <option value="Krank">Krank</option>
                <option value="Abwesenheit">Abwesenheit</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Erfassung</label>
              <select
                value={selectedEntryType}
                onChange={(e) => setSelectedEntryType(e.target.value)}
                className="w-full p-2 border rounded-lg"
              >
                <option value="all">Alle</option>
                <option value="manual">Manuell</option>
                <option value="auto">Automatisch</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Reinigungsart</label>
              <select
                value={selectedCleaningType}
                onChange={(e) => setSelectedCleaningType(e.target.value)}
                className="w-full p-2 border rounded-lg"
              >
                <option value="all">Alle</option>
                {cleaningTypes.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {[{k:'today',l:'Heute'},{k:'7',l:'Letzte 7 Tage'},{k:'14',l:'Letzte 14 Tage'}].map(({k,l}) => (
              <button
                key={k}
                onClick={() => setQuickRange(k)}
                className={`px-4 py-2 rounded-lg ${activeQuick === k ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}
              >
                {l}
              </button>
            ))}
            <button
              onClick={() => {
                setDateFrom('');
                setDateTo('');
                setSelectedEmployee('all');
                setSelectedObject('all');
                setSelectedServiceType('all');
                setSelectedCleaningType('all');
                setSelectedEntryType('all');
                setActiveQuick(null);
              }}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
            >
              Filter zurücksetzen
            </button>
          </div>
        </div>

        {/* Summen */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-blue-50 rounded-lg p-4">
            <div className="text-sm text-blue-600">Gesamt Stunden</div>
            <div className="text-2xl font-bold text-blue-700">{totalHours.toFixed(2)}h</div>
          </div>
          <div className="bg-green-50 rounded-lg p-4">
            <div className="text-sm text-green-600">Gesamt Betrag</div>
            <div className="text-2xl font-bold text-green-700">{totalAmount.toFixed(2)}€</div>
          </div>
        </div>

        {/* Auswahl-Aktionsleiste */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-lg p-3">
            <span className="text-sm font-medium text-red-700">{selectedIds.size} ausgewählt</span>
            <button
              onClick={deleteSelected}
              className="inline-flex items-center gap-1 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition text-sm font-medium"
            >
              <Trash2 size={16} />
              Ausgewählte löschen
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-gray-500 hover:text-gray-700 underline"
            >
              Auswahl aufheben
            </button>
          </div>
        )}

        {/* Tabelle */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          {loading ? (
            <div className="p-8 text-center">Lädt...</div>
          ) : filteredBookings.length === 0 ? (
            <div className="p-8 text-center text-gray-500">Keine Buchungen gefunden</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-center text-sm w-10">
                      <input
                        type="checkbox"
                        checked={filteredBookings.length > 0 && selectedIds.size === filteredBookings.length}
                        onChange={toggleSelectAll}
                        className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                      />
                    </th>
                    <th
                      className="px-4 py-3 text-left text-sm font-semibold cursor-pointer hover:bg-gray-100"
                      onClick={() => handleSort('check_in')}
                    >
                      Datum {sortField === 'check_in' && (sortDirection === 'asc' ? '?' : '?')}
                    </th>
                    <th 
                      className="px-4 py-3 text-left text-sm font-semibold cursor-pointer hover:bg-gray-100"
                      onClick={() => handleSort('employee_name')}
                    >
                      Mitarbeiter {sortField === 'employee_name' && (sortDirection === 'asc' ? '?' : '?')}
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-semibold">Objekt</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold">Von - Bis</th>
                    <th className="px-4 py-3 text-center text-sm font-semibold">Pause</th>
                    <th 
                      className="px-4 py-3 text-right text-sm font-semibold cursor-pointer hover:bg-gray-100"
                      onClick={() => handleSort('billed_hours')}
                    >
                      Netto h {sortField === 'billed_hours' && (sortDirection === 'asc' ? '?' : '?')}
                    </th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">Satz</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">Betrag</th>
                    <th
                      className="px-4 py-3 text-center text-sm font-semibold cursor-pointer hover:bg-gray-100"
                      onClick={() => handleSort('service_type')}
                    >
                      Reinigungsart {sortField === 'service_type' && (sortDirection === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="px-4 py-3 text-center text-sm font-semibold">Erfassung</th>
                    <th className="px-4 py-3 text-center text-sm font-semibold">Aktionen</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filteredBookings.map((booking) => (
                    <tr key={booking.id} className={`hover:bg-gray-50 ${selectedIds.has(booking.id) ? 'bg-blue-50' : ''}`}>
                      <td className="px-4 py-3 text-center">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(booking.id)}
                          onChange={() => toggleSelect(booking.id)}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                        />
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {new Date(booking.check_in).toLocaleDateString('de-DE')}
                      </td>
                      <td className="px-4 py-3 text-sm font-medium">
                        {booking.employee_name}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {booking.object_name}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {new Date(booking.check_in).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                        {' - '}
                        {booking.check_out
                          ? new Date(booking.check_out).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
                          : 'Offen'}
                        {booking.sync_delay_minutes >= 5 && (
                          <span
                            className="ml-1 inline-flex items-center gap-0.5 text-[11px] text-slate-500 border border-slate-300 rounded px-1 whitespace-nowrap align-middle"
                            title="Offline gestempelt und verspätet an den Server übertragen (Empfang minus Stempelzeit). Das ist KEINE Mehrarbeit und keine Arbeitszeit."
                          >
                            🕓 offline, {formatDelay(booking.sync_delay_minutes)} verspätet übertragen
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        {booking.pause_minutes > 0 ? (
                          <span className="inline-block px-2 py-0.5 bg-yellow-100 text-yellow-800 rounded text-xs font-medium">
                            {booking.pause_minutes} Min
                          </span>
                        ) : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-right font-medium">
                        {booking.billed_hours?.toFixed(2) || '0.00'}
                      </td>
                      <td className="px-4 py-3 text-sm text-right">
                        {booking.hourly_rate?.toFixed(2) || '0.00'}€
                      </td>
                      <td className="px-4 py-3 text-sm text-right font-semibold text-green-600">
                        {((booking.billed_hours || 0) * (booking.hourly_rate || 0)).toFixed(2)}€
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                          booking.service_type === 'Arbeit' ? 'bg-blue-100 text-blue-800' :
                          booking.service_type === 'Urlaub' ? 'bg-green-100 text-green-800' :
                          'bg-red-100 text-red-800'
                        }`}>
                          {booking.service_type || 'Arbeit'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-block px-2 py-1 rounded text-xs ${
                          booking.is_manual_entry 
                            ? 'bg-purple-100 text-purple-800' 
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {booking.is_manual_entry ? 'Manuell' : 'Auto'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex gap-2 justify-center">
                          <button
                            onClick={() => handleEdit(booking)}
                            className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                            title="Bearbeiten"
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            onClick={() => handleDelete(booking.id)}
                            className="p-1 text-red-600 hover:bg-red-50 rounded"
                            title="Löschen"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Edit Modal */}
        {showEditModal && editingBooking && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg w-full max-w-md max-h-[90vh] flex flex-col">
              <div className="p-6 pb-3">
                <h3 className="text-lg font-bold">Buchung bearbeiten</h3>
              </div>

              <div className="overflow-y-auto flex-1 px-6">
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Datum</label>
                    <input
                      type="date"
                      value={editingBooking.check_in?.split('T')[0] || ''}
                      onChange={(e) => {
                        const newDate = e.target.value;
                        const oldTime = editingBooking.check_in.split('T')[1];
                        setEditingBooking({
                          ...editingBooking,
                          check_in: `${newDate}T${oldTime}`
                        });
                      }}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Von</label>
                    <input
                      type="time"
                      value={editingBooking.check_in?.split('T')[1]?.substring(0, 5) || ''}
                      onChange={(e) => {
                        const date = editingBooking.check_in.split('T')[0];
                        const newCheckIn = `${date}T${e.target.value}:00`;
                        const checkOut = editingBooking.check_out;
                        let bh = editingBooking.billed_hours;
                        if (checkOut) {
                          const ci = new Date(newCheckIn);
                          const co = new Date(checkOut);
                          bh = Math.round(((co - ci) / 3600000) * 100) / 100;
                        }
                        setEditingBooking({
                          ...editingBooking,
                          check_in: newCheckIn,
                          billed_hours: bh
                        });
                      }}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Bis</label>
                    <input
                      type="time"
                      value={editingBooking.check_out?.split('T')[1]?.substring(0, 5) || ''}
                      onChange={(e) => {
                        const date = editingBooking.check_in.split('T')[0];
                        const newCheckOut = `${date}T${e.target.value}:00`;
                        const ci = new Date(editingBooking.check_in);
                        const co = new Date(newCheckOut);
                        const bh = Math.round(((co - ci) / 3600000) * 100) / 100;
                        setEditingBooking({
                          ...editingBooking,
                          check_out: newCheckOut,
                          billed_hours: bh
                        });
                      }}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Stunden</label>
                    <input
                      type="number"
                      step="0.25"
                      value={editingBooking.billed_hours ?? ''}
                      onChange={(e) => setEditingBooking({
                        ...editingBooking,
                        billed_hours: parseFloat(e.target.value) || 0
                      })}
                      className="w-full p-2 border rounded-lg"
                    />
                    <p className="text-xs text-gray-500 mt-1">Wird automatisch aus Von/Bis berechnet. Kann manuell überschrieben werden.</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Mitarbeiter</label>
                    <select
                      value={editingBooking.employee_id}
                      onChange={(e) => setEditingBooking({
                        ...editingBooking,
                        employee_id: parseInt(e.target.value)
                      })}
                      className="w-full p-2 border rounded-lg"
                    >
                      {employees.map(emp => (
                        <option key={emp.id} value={emp.id}>
                          {emp.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Art</label>
                    <select
                      value={editingBooking.service_type || 'Unterhaltsreinigung'}
                      onChange={(e) => setEditingBooking({
                        ...editingBooking,
                        service_type: e.target.value
                      })}
                      className="w-full p-2 border rounded-lg"
                    >
                      <option value="Unterhaltsreinigung">Unterhaltsreinigung</option>
                      <option value="Fensterreinigung">Fensterreinigung</option>
                      <option value="Grundreinigung">Grundreinigung</option>
                      <option value="Sonderreinigung">Sonderreinigung</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Objekt</label>
                    <select
                      value={editingBooking.object_id}
                      onChange={(e) => setEditingBooking({
                        ...editingBooking,
                        object_id: parseInt(e.target.value)
                      })}
                      className="w-full p-2 border rounded-lg"
                    >
                      {allObjects.map(obj => (
                        <option key={obj.id} value={obj.id}>
                          {obj.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Stundensatz (€)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={editingBooking.hourly_rate || '15.50'}
                      onChange={(e) => setEditingBooking({
                        ...editingBooking,
                        hourly_rate: parseFloat(e.target.value)
                      })}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Notizen</label>
                    <textarea
                      value={editingBooking.notes || ''}
                      onChange={(e) => setEditingBooking({
                        ...editingBooking,
                        notes: e.target.value
                      })}
                      className="w-full p-2 border rounded-lg"
                      rows="3"
                    />
                  </div>
                  {editingBooking.server_received_at && (
                    <div className="bg-gray-50 rounded p-3 text-sm text-gray-600">
                      <div>Gestempelt: {new Date(editingBooking.check_out || editingBooking.check_in).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: undefined, hour: '2-digit', minute: '2-digit' })}</div>
                      <div>Empfangen: {new Date(editingBooking.server_received_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: undefined, hour: '2-digit', minute: '2-digit' })}</div>
                      {editingBooking.sync_delay_minutes >= 5 && (
                        <div className="text-slate-600 font-medium">
                          🕓 Offline gestempelt, {formatDelay(editingBooking.sync_delay_minutes)} verspätet übertragen (keine Mehrarbeit)
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex gap-3 p-6 pt-4 border-t border-gray-200 mt-2">
                <button
                  onClick={() => setShowEditModal(false)}
                  className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleSaveEdit}
                  className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
                >
                  Speichern
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Neue Buchung Modal */}
        {showNewBookingModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              <h3 className="text-lg font-bold mb-4">Neue Buchung erstellen</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Mitarbeiter *</label>
                  <select
                    value={newBookingData.employee_id}
                    onChange={(e) => {
                      const val = e.target.value;
                      setNewBookingData(prev => ({...prev, employee_id: val}));
                      loadScheduleForBooking(val, newBookingData.object_id, newBookingData.booking_date);
                    }}
                    className="w-full p-2 border rounded-lg"
                  >
                    <option value="">Bitte wählen...</option>
                    {employees.map(emp => (
                      <option key={emp.id} value={emp.id}>{emp.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="flex items-center gap-2 mb-2">
                    <input
                      type="checkbox"
                      checked={useCustomObject}
                      onChange={(e) => setUseCustomObject(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm font-medium">Einmaliger Kunde (nicht in DB)</span>
                  </label>

                  {useCustomObject ? (
                    <input
                      type="text"
                      placeholder="Kundenname eingeben..."
                      value={newBookingData.custom_object_name}
                      onChange={(e) => setNewBookingData({...newBookingData, custom_object_name: e.target.value})}
                      className="w-full p-2 border rounded-lg"
                    />
                  ) : (
                    <select
                      value={newBookingData.object_id}
                      onChange={(e) => {
                        const val = e.target.value;
                        setNewBookingData(prev => ({...prev, object_id: val}));
                        loadScheduleForBooking(newBookingData.employee_id, val, newBookingData.booking_date);
                      }}
                      className="w-full p-2 border rounded-lg"
                    >
                      <option value="">Bitte wählen...</option>
                      {allObjects.map(obj => (
                        <option key={obj.id} value={obj.id}>{obj.name}</option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Datum *</label>
                    <input
                      type="date"
                      value={newBookingData.booking_date}
                      onChange={(e) => {
                        const val = e.target.value;
                        setNewBookingData(prev => ({...prev, booking_date: val}));
                        loadScheduleForBooking(newBookingData.employee_id, newBookingData.object_id, val);
                      }}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Von *</label>
                    <input
                      type="time"
                      value={newBookingData.check_in_time}
                      onChange={(e) => {
                        const v = e.target.value;
                        const [h1,m1] = v.split(':').map(Number);
                        const [h2,m2] = newBookingData.check_out_time.split(':').map(Number);
                        const bh = Math.round(((h2*60+m2)-(h1*60+m1))/60*100)/100;
                        setNewBookingData({...newBookingData, check_in_time: v, billed_hours: bh});
                      }}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Bis *</label>
                    <input
                      type="time"
                      value={newBookingData.check_out_time}
                      onChange={(e) => {
                        const v = e.target.value;
                        const [h1,m1] = newBookingData.check_in_time.split(':').map(Number);
                        const [h2,m2] = v.split(':').map(Number);
                        const bh = Math.round(((h2*60+m2)-(h1*60+m1))/60*100)/100;
                        setNewBookingData({...newBookingData, check_out_time: v, billed_hours: bh});
                      }}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">Stunden</label>
                  <input
                    type="number"
                    step="0.25"
                    value={newBookingData.billed_hours ?? ''}
                    onChange={(e) => setNewBookingData({...newBookingData, billed_hours: parseFloat(e.target.value) || 0})}
                    className="w-full p-2 border rounded-lg"
                  />
                  <p className="text-xs text-gray-500 mt-1">Wird automatisch aus Von/Bis berechnet. Kann manuell überschrieben werden.</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Stundensatz (€) *</label>
                    <input
                      type="number"
                      step="0.01"
                      value={newBookingData.hourly_rate}
                      onChange={(e) => setNewBookingData({...newBookingData, hourly_rate: e.target.value})}
                      className="w-full p-2 border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Art *</label>
                    <select
                      value={newBookingData.service_type}
                      onChange={(e) => setNewBookingData({...newBookingData, service_type: e.target.value})}
                      className="w-full p-2 border rounded-lg"
                    >
                      <option value="Unterhaltsreinigung">Unterhaltsreinigung</option>
                      <option value="Fensterreinigung">Fensterreinigung</option>
                      <option value="Grundreinigung">Grundreinigung</option>
                      <option value="Sonderreinigung">Sonderreinigung</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">Notizen</label>
                  <textarea
                    value={newBookingData.notes}
                    onChange={(e) => setNewBookingData({...newBookingData, notes: e.target.value})}
                    className="w-full p-2 border rounded-lg"
                    rows="3"
                    placeholder="Zusätzliche Informationen..."
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowNewBookingModal(false)}
                  className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
                >
                  Abbrechen
                </button>
                <button
                  onClick={handleSaveNewBooking}
                  disabled={!newBookingData.employee_id || (!useCustomObject && !newBookingData.object_id) || (useCustomObject && !newBookingData.custom_object_name)}
                  className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300"
                >
                  Buchung erstellen
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    );
  });

const AdminDashboard = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('overview');

  // Rollen-basierte Tab-Filterung
  const userRole = localStorage.getItem('userRole') || 'mitarbeiter';
  const isAdmin = userRole === 'admin';

  const ALLOWED_TABS_OBJEKTLEITER = [
    'overview', 'schedule', 'journal', 'genehmigungen',
    'employees', 'customers', 'ma-objekte',
    'urlaub-verwaltung', 'km-journal',
    'offene-punkte', 'krankmeldungen', 'monatsbestaetigung',
    'posteingang', 'abrechnungen', 'audit-log',
  ];
  const isTabAllowed = (tab) => isAdmin || ALLOWED_TABS_OBJEKTLEITER.includes(tab);
  const [showPwChange, setShowPwChange] = useState(false);
  const [pwOld, setPwOld] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [pwConfirm, setPwConfirm] = useState('');
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwLoading, setPwLoading] = useState(false);
  const [employees, setEmployees] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [liveStatus, setLiveStatus] = useState({ active: [], upcoming: [], active_count: 0, upcoming_count: 0 });
  
  const [stats, setStats] = useState({
    active_employees: 0,
    paused_employees: 0,
    offline_employees: 0,
    total_employees: 0,
    total_hours_today: 0
  });
  
  // Offene Genehmigungen Badge
  const [pendingCount, setPendingCount] = useState(0);

  // Modal States
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [showNewCustomerModal, setShowNewCustomerModal] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [editingCustomer, setEditingCustomer] = useState(null);

  // KM-Modal States (auf Hauptebene, damit Re-Render den State nicht zurücksetzt)
  const [showKmModal, setShowKmModal] = useState(false);
  const [kmBookingInfo, setKmBookingInfo] = useState(null);
  const [kmDistance, setKmDistance] = useState('');

  const handleSaveKm = async () => {
    if (!kmBookingInfo || !kmDistance || parseFloat(kmDistance) <= 0) {
      setShowKmModal(false);
      return;
    }
    try {
      await api.post('/admin/km/manual', {
        employee_id: kmBookingInfo.employee_id,
        object_id: kmBookingInfo.object_id,
        custom_object_name: kmBookingInfo.custom_object_name,
        date: kmBookingInfo.date,
        time_entry_id: kmBookingInfo.booking_id,
        distance_km: parseFloat(kmDistance)
      });
      showToast(`KM-Fahrt gespeichert: ${kmDistance} km`, 'success');
    } catch (error) {
      showToast('Fehler beim KM-Speichern', 'error');
    }
    setShowKmModal(false);
  };

  // Form States
  const [employeeForm, setEmployeeForm] = useState({
    personal_nr: '',
    first_name: '',
    last_name: '',
    email: '',
    hourly_rate: '',
    tracking_mode: 'C',
    enforce_min_duration: false
  });
  
  const [customerForm, setCustomerForm] = useState({
    name: '',
    address: '',
    hourly_rate: ''
  });
  
  // Filter States
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState('all');
  
  // Toast
  const [toast, setToast] = useState(null);
  
  // Badge Counts fuer Mehr-Menue
  const [badgeCounts, setBadgeCounts] = useState({});

  // Kunden Filter
  const [showInactiveCustomers, setShowInactiveCustomers] = useState(false);
  // Kunden: Expandierte Zeile + Objekt-Bearbeitung
  const [expandedCustomerId, setExpandedCustomerId] = useState(null);
  const [editingObject, setEditingObject] = useState(null);
  const [objectForm, setObjectForm] = useState({ name: '', address: '' });
  const [sollstundenForm, setSollstundenForm] = useState([]);
  const [showObjectModal, setShowObjectModal] = useState(false);

  // Journal Filter State (auf Parent-Ebene, damit Filter bei Remount erhalten bleiben)
  const _jToday = new Date();
  const _jFirst = new Date(_jToday.getFullYear(), _jToday.getMonth(), 1);
  const _jLast = new Date(_jToday.getFullYear(), _jToday.getMonth() + 1, 0);
  const [journalEmployee, setJournalEmployee] = useState('all');
  const [journalDateFrom, setJournalDateFrom] = useState(
    `${_jFirst.getFullYear()}-${String(_jFirst.getMonth() + 1).padStart(2, '0')}-01`
  );
  const [journalDateTo, setJournalDateTo] = useState(
    `${_jLast.getFullYear()}-${String(_jLast.getMonth() + 1).padStart(2, '0')}-${String(_jLast.getDate()).padStart(2, '0')}`
  );
  const [journalObject, setJournalObject] = useState('all');
  const [journalServiceType, setJournalServiceType] = useState('Arbeit');
  const [journalCleaningType, setJournalCleaningType] = useState('all');
  const [journalEntryType, setJournalEntryType] = useState('all');
  const [journalSortField, setJournalSortField] = useState('check_in');
  const [journalSortDir, setJournalSortDir] = useState('desc');

  // KM-Journal Filter State (auf Parent-Ebene, damit Filter bei Remount erhalten bleiben)
  const [kmJournalEmployee, setKmJournalEmployee] = useState('all');
  const [kmJournalDateFrom, setKmJournalDateFrom] = useState(
    `${_jFirst.getFullYear()}-${String(_jFirst.getMonth() + 1).padStart(2, '0')}-01`
  );
  const [kmJournalDateTo, setKmJournalDateTo] = useState(
    `${_jLast.getFullYear()}-${String(_jLast.getMonth() + 1).padStart(2, '0')}-${String(_jLast.getDate()).padStart(2, '0')}`
  );
  const [kmJournalObject, setKmJournalObject] = useState('all');

  // Bottom Navigation
  const [showMoreMenu, setShowMoreMenu] = useState(false);

  const showToast = useCallback((message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  useEffect(() => {
    loadEmployees();
    loadCustomers();
    loadStats();
    loadLiveStatus();
    loadBadgeCounts();

    const interval = setInterval(() => {
      loadStats();
      loadLiveStatus();
      loadBadgeCounts();
    }, 600000); // 10 Minuten
    
    return () => clearInterval(interval);
  }, []);

  const loadEmployees = async () => {
    try {
      const response = await api.get('/admin/employees-with-categories?include_inactive=true');
      if (response.data) {
        setEmployees(response.data.filter(emp => !emp.personal_nr?.startsWith('A')));
      }
    } catch (error) {
      console.error('Fehler beim Laden der Mitarbeiter:', error);
    }
  };

  const loadBadgeCounts = async () => {
    try {
      const response = await api.get('/admin/badge-counts');
      if (response.data) setBadgeCounts(response.data);
    } catch (error) {
      console.error('Fehler beim Laden der Badge-Counts:', error);
    }
    try {
      const res = await api.get('/admin/pending-bookings/count');
      setPendingCount(res.data.count || 0);
    } catch (e) {}
  };

  const loadCustomers = async () => {
    try {
      const response = await api.get('/admin/customers');
      if (response.data) {
        setCustomers(response.data);
      }
    } catch (error) {
      console.error('Fehler beim Laden der Kunden:', error);
    }
  };

  const loadStats = async () => {
    try {
      const response = await api.get('/admin/dashboard/stats');
      if (response.data) {
        setStats(response.data);
      }
    } catch (error) {
      console.error('Fehler beim Laden der Stats:', error);
    }
  };

  const loadLiveStatus = async () => {
    try {
      const response = await api.get('/admin/live-status');
      if (response.data) {
        setLiveStatus(response.data);
      }
    } catch (error) {
      console.error('Fehler beim Laden des Live-Status:', error);
      setLiveStatus({ active: [], upcoming: [], active_count: 0, upcoming_count: 0 });
    }
  };

  const handleSaveEmployee = async () => {
    try {
      if (editingEmployee) {
        await api.put(`/admin/employees/${editingEmployee.id}`, employeeForm);
        showToast('Mitarbeiter aktualisiert', 'success');
      } else {
        await api.post('/admin/employees', employeeForm);
        showToast('Mitarbeiter erstellt', 'success');
      }
      setShowNewEmployeeModal(false);
      loadEmployees();
    } catch (error) {
      showToast('Fehler beim Speichern', 'error');
    }
  };

  const handleSaveCustomer = async () => {
    try {
      if (editingCustomer) {
        await api.put(`/admin/customers/${editingCustomer.id}`, customerForm);
        showToast('Kunde aktualisiert', 'success');
      } else {
        await api.post('/admin/customers', customerForm);
        showToast('Kunde erstellt', 'success');
      }
      setShowNewCustomerModal(false);
      loadCustomers();
    } catch (error) {
      showToast('Fehler beim Speichern', 'error');
    }
  };

  const WEEKDAY_NAMES = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
  const WEEKDAY_SHORT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

  const openObjectEditor = async (obj) => {
    setEditingObject(obj);
    setObjectForm({ name: obj.name, address: obj.address || '' });
    // Sollstunden laden
    try {
      const resp = await api.get(`/admin/objects/${obj.id}/standard-times`);
      const existing = resp.data || [];
      // 7 Wochentage initialisieren
      const form = Array.from({ length: 7 }, (_, i) => {
        const match = existing.find(e => e.weekday === i);
        if (match) {
          return { weekday: i, start_time: match.start_time || '', end_time: match.end_time || '', standard_hours: match.standard_hours || '', active: true };
        }
        // Fallback: Eintraege ohne weekday (alt) auf alle Tage anwenden
        const fallback = existing.find(e => e.weekday === null || e.weekday === undefined);
        if (fallback && i < 5) {
          return { weekday: i, start_time: fallback.start_time || '', end_time: fallback.end_time || '', standard_hours: fallback.standard_hours || '', active: true };
        }
        return { weekday: i, start_time: '', end_time: '', standard_hours: '', active: false };
      });
      setSollstundenForm(form);
    } catch (e) {
      setSollstundenForm(Array.from({ length: 7 }, (_, i) => ({ weekday: i, start_time: '', end_time: '', standard_hours: '', active: false })));
    }
    setShowObjectModal(true);
  };

  const calcHoursFromTimes = (start, end) => {
    if (!start || !end) return '';
    const [sh, sm] = start.split(':').map(Number);
    const [eh, em] = end.split(':').map(Number);
    let mins = (eh * 60 + em) - (sh * 60 + sm);
    if (mins < 0) mins += 24 * 60;
    return (mins / 60).toFixed(2);
  };

  const handleSaveObject = async () => {
    if (!editingObject) return;
    try {
      // Objekt-Daten speichern
      await api.put(`/admin/objects/${editingObject.id}`, objectForm);
      // Sollstunden speichern (nur aktive Tage)
      const activeDays = sollstundenForm.filter(d => d.active && d.start_time && d.end_time);
      await api.put(`/admin/objects/${editingObject.id}/standard-times`, activeDays.map(d => ({
        weekday: d.weekday,
        start_time: d.start_time,
        end_time: d.end_time,
        standard_hours: parseFloat(d.standard_hours) || parseFloat(calcHoursFromTimes(d.start_time, d.end_time)) || 0,
      })));
      showToast('Objekt + Sollstunden gespeichert', 'success');
      setShowObjectModal(false);
      loadCustomers();
    } catch (e) {
      showToast('Fehler beim Speichern', 'error');
    }
  };

  const getCategoryBadge = (category) => {
    const badges = {
      'A': { color: 'bg-green-100 text-green-800', icon: '🔄', label: 'Auto' },
      'B': { color: 'bg-blue-100 text-blue-800', icon: '👆', label: 'Button' },
      'C': { color: 'bg-orange-100 text-orange-800', icon: '👤', label: 'Normal' }
    };
    return badges[category] || badges['C'];
  };

  const [showInactive, setShowInactive] = useState(false);

  const filteredEmployees = employees.filter(emp => {
    const matchesSearch = emp.first_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         emp.last_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         emp.personal_nr?.includes(searchTerm) ||
                         emp.name?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filterCategory === 'all' || emp.tracking_mode === filterCategory;
    const matchesActive = showInactive || emp.is_active !== false;
    return matchesSearch && matchesFilter && matchesActive;
  });

  // Nur aktive MA fuer Dropdowns in Journal, KM-Journal, Dienstplan etc.
  const activeEmployees = useMemo(() => employees.filter(e => e.is_active !== false), [employees]);

  // Nur aktive Kunden fuer CustomersTab Filter
  const filteredCustomers = customers.filter(c => showInactiveCustomers || c.is_active !== false);

  // ==================== TAB COMPONENTS ====================
  
  const OverviewTab = () => (
    <div className="space-y-6">
      {/* Haupt-KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-500 uppercase">Eingestempelt</p>
              <p className="text-2xl font-bold text-green-600">{stats.active_employees}</p>
            </div>
            <Activity className="text-green-400" size={28} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-500 uppercase">Offline</p>
              <p className="text-2xl font-bold text-gray-600">{stats.offline_employees}</p>
            </div>
            <Users className="text-gray-400" size={28} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-500 uppercase">Stunden heute</p>
              <p className="text-2xl font-bold text-blue-600">{stats.total_hours_today?.toFixed(1) || '0.0'}h</p>
            </div>
            <Clock className="text-blue-400" size={28} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-500 uppercase">Schichten heute</p>
              <p className="text-2xl font-bold text-indigo-600">{stats.today_schedules || 0}</p>
            </div>
            <Calendar className="text-indigo-400" size={28} />
          </div>
        </div>
      </div>

      {/* Offene Punkte */}
      {(stats.pending_sick > 0 || stats.pending_vacation > 0 || stats.new_messages > 0 || stats.open_pushes > 0) && (
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase">Handlungsbedarf</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {stats.pending_sick > 0 && (
              <button onClick={() => setActiveTab('krankmeldungen')} className="p-3 bg-red-50 rounded-lg text-left hover:bg-red-100 transition-colors">
                <p className="text-lg font-bold text-red-600">{stats.pending_sick}</p>
                <p className="text-xs text-red-700">Krankmeldungen offen</p>
              </button>
            )}
            {stats.pending_vacation > 0 && (
              <button onClick={() => setActiveTab('urlaub-verwaltung')} className="p-3 bg-blue-50 rounded-lg text-left hover:bg-blue-100 transition-colors">
                <p className="text-lg font-bold text-blue-600">{stats.pending_vacation}</p>
                <p className="text-xs text-blue-700">Urlaubsantraege offen</p>
              </button>
            )}
            {stats.new_messages > 0 && (
              <button onClick={() => setActiveTab('posteingang')} className="p-3 bg-orange-50 rounded-lg text-left hover:bg-orange-100 transition-colors">
                <p className="text-lg font-bold text-orange-600">{stats.new_messages}</p>
                <p className="text-xs text-orange-700">Neue Nachrichten</p>
              </button>
            )}
            {stats.open_pushes > 0 && (
              <button onClick={() => setActiveTab('offene-punkte')} className="p-3 bg-yellow-50 rounded-lg text-left hover:bg-yellow-100 transition-colors">
                <p className="text-lg font-bold text-yellow-600">{stats.open_pushes}</p>
                <p className="text-xs text-yellow-700">Push unbeantwort.</p>
              </button>
            )}
          </div>
        </div>
      )}

      {/* Live-Status */}
      <LiveTab />
    </div>
  );

  const EmployeesTab = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div className="flex gap-4">
          <input
            type="text"
            placeholder="Suche nach Name oder Pers.-Nr..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="px-4 py-2 border rounded-lg w-64"
          />
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="px-4 py-2 border rounded-lg"
          >
            <option value="all">Alle Kategorien</option>
            <option value="A">Kategorie A</option>
            <option value="B">Kategorie B</option>
            <option value="C">Kategorie C</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="rounded"
            />
            Deaktivierte anzeigen
          </label>
        </div>
        <button
          onClick={() => {
            setEditingEmployee(null);
            setEmployeeForm({ personal_nr: '', first_name: '', last_name: '', email: '', hourly_rate: '', tracking_mode: 'C', enforce_min_duration: false });
            setShowNewEmployeeModal(true);
          }}
          className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
        >
          <Plus size={20} />
          Neuer Mitarbeiter
        </button>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold">Pers.-Nr</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Name</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Email</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Kategorie</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">Stundensatz</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">Status</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">Aktionen</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {filteredEmployees.map((emp) => {
              const badge = getCategoryBadge(emp.tracking_mode);
              return (
                <tr key={emp.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium">{emp.personal_nr}</td>
                  <td className="px-4 py-3 text-sm">{emp.name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{emp.email}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${badge.color}`}>
                      {badge.icon} {badge.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-right">{emp.hourly_rate?.toFixed(2) || '0.00'}€</td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={async () => {
                        const newActive = !(emp.is_active !== false);
                        const label = newActive ? 'aktivieren' : 'deaktivieren';
                        if (!window.confirm(`${emp.name} wirklich ${label}?`)) return;
                        try {
                          await api.put(`/admin/employees/${emp.id}`, { is_active: newActive });
                          showToast(`Mitarbeiter ${newActive ? 'aktiviert' : 'deaktiviert'}`, 'success');
                          loadEmployees();
                        } catch (e) {
                          showToast('Fehler', 'error');
                        }
                      }}
                      className={`px-3 py-1.5 rounded-full text-xs font-bold cursor-pointer border-2 transition-all ${emp.is_active !== false ? 'bg-green-100 text-green-700 border-green-300 hover:bg-red-100 hover:text-red-700 hover:border-red-300' : 'bg-red-100 text-red-700 border-red-300 hover:bg-green-100 hover:text-green-700 hover:border-green-300'}`}
                      title={emp.is_active !== false ? 'Klicken zum Deaktivieren' : 'Klicken zum Aktivieren'}
                    >
                      {emp.is_active !== false ? '● Aktiv' : '○ Deaktiviert'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => {
                        setEditingEmployee(emp);
                        setEmployeeForm({
                          personal_nr: emp.personal_nr,
                          first_name: emp.first_name,
                          last_name: emp.last_name,
                          email: emp.email,
                          hourly_rate: emp.hourly_rate?.toString() || '',
                          tracking_mode: emp.tracking_mode,
                          enforce_min_duration: emp.enforce_min_duration || false
                        });
                        setShowNewEmployeeModal(true);
                      }}
                      className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                    >
                      <Edit2 size={16} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );

  const CustomersTab = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-bold">Kunden & Objekte</h2>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={showInactiveCustomers}
              onChange={(e) => setShowInactiveCustomers(e.target.checked)}
              className="rounded"
            />
            Deaktivierte anzeigen
          </label>
        </div>
        <button
          onClick={() => {
            setEditingCustomer(null);
            setCustomerForm({ name: '', address: '', hourly_rate: '' });
            setShowNewCustomerModal(true);
          }}
          className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
        >
          <Plus size={20} />
          Neuer Kunde
        </button>
      </div>

      <div className="space-y-3">
        {filteredCustomers.map((cust) => (
          <div key={cust.id} className={`bg-white rounded-lg shadow overflow-hidden ${cust.is_active === false ? 'opacity-50' : ''}`}>
            {/* Kunden-Zeile */}
            <div
              className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50"
              onClick={() => setExpandedCustomerId(expandedCustomerId === cust.id ? null : cust.id)}
            >
              <ChevronDown size={18} className={`text-gray-400 transition-transform ${expandedCustomerId === cust.id ? 'rotate-180' : ''}`} />
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm">{cust.name}</div>
                <div className="text-xs text-gray-500">{cust.objects?.filter(o => o.is_active).length || 0} Objekte</div>
              </div>
              {isAdmin && (
                <div className="text-right text-xs mr-2">
                  {cust.yearly_revenue > 0 && (
                    <span className="text-green-600 font-medium">{new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(cust.yearly_revenue)}</span>
                  )}
                </div>
              )}
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  const newActive = !(cust.is_active !== false);
                  const label = newActive ? 'aktivieren' : 'deaktivieren';
                  const extra = !newActive ? '\n\nAlle Objekte des Kunden werden ebenfalls deaktiviert!' : '';
                  if (!window.confirm(`${cust.name} wirklich ${label}?${extra}`)) return;
                  try {
                    await api.put(`/admin/customers/${cust.id}`, { is_active: newActive });
                    showToast(`Kunde ${newActive ? 'aktiviert' : 'deaktiviert'}`, 'success');
                    loadCustomers();
                  } catch (e2) { showToast('Fehler', 'error'); }
                }}
                className={`px-3 py-1.5 rounded-full text-xs font-bold cursor-pointer border-2 transition-all ${cust.is_active !== false ? 'bg-green-100 text-green-700 border-green-300 hover:bg-red-100 hover:text-red-700 hover:border-red-300' : 'bg-red-100 text-red-700 border-red-300 hover:bg-green-100 hover:text-green-700 hover:border-green-300'}`}
                title={cust.is_active !== false ? 'Klicken zum Deaktivieren' : 'Klicken zum Aktivieren'}
              >
                {cust.is_active !== false ? '● Aktiv' : '○ Inaktiv'}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setEditingCustomer(cust);
                  setCustomerForm({ name: cust.name, address: cust.address, hourly_rate: cust.hourly_rate?.toString() || '' });
                  setShowNewCustomerModal(true);
                }}
                className="p-1 text-blue-600 hover:bg-blue-50 rounded"
              >
                <Edit2 size={16} />
              </button>
            </div>

            {/* Expandierter Objekt-Bereich */}
            {expandedCustomerId === cust.id && (
              <div className="border-t bg-gray-50 px-4 py-3">
                {(cust.objects || []).length === 0 ? (
                  <p className="text-sm text-gray-400 italic">Keine Objekte vorhanden</p>
                ) : (
                  <div className="space-y-2">
                    {cust.objects.map((obj) => (
                      <div key={obj.id} className={`flex items-center gap-3 p-3 bg-white rounded-lg border ${!obj.is_active ? 'opacity-50' : ''}`}>
                        <Building2 size={16} className="text-gray-400 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{obj.name}</p>
                          {obj.address && <p className="text-xs text-gray-500 truncate">{obj.address}</p>}
                        </div>
                        <button
                          onClick={async () => {
                            const newActive = !obj.is_active;
                            const label = newActive ? 'aktivieren' : 'deaktivieren';
                            if (!window.confirm(`Objekt "${obj.name}" wirklich ${label}?`)) return;
                            try {
                              await api.put(`/admin/objects/${obj.id}`, { is_active: newActive });
                              showToast(`Objekt ${newActive ? 'aktiviert' : 'deaktiviert'}`, 'success');
                              loadCustomers();
                            } catch (e) { showToast('Fehler', 'error'); }
                          }}
                          className={`px-2 py-1 rounded-full text-xs font-bold cursor-pointer border transition-all ${obj.is_active ? 'bg-green-50 text-green-600 border-green-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200' : 'bg-red-50 text-red-600 border-red-200 hover:bg-green-50 hover:text-green-600 hover:border-green-200'}`}
                          title={obj.is_active ? 'Klicken zum Deaktivieren' : 'Klicken zum Aktivieren'}
                        >
                          {obj.is_active ? '●' : '○'}
                        </button>
                        <button
                          onClick={() => openObjectEditor(obj)}
                          className="px-3 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-xs font-medium hover:bg-blue-100 flex items-center gap-1"
                        >
                          <Edit2 size={14} />
                          Bearbeiten
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );

  const LiveTab = () => {
    const { active = [], upcoming = [], active_count = 0, upcoming_count = 0,
            stamped_in = [], stamped_in_count = 0,
            today_booked = [], today_booked_count = 0 } = liveStatus || {};
    return (
      <div className="space-y-4">
        {/* Jetzt eingestempelt (live) */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-orange-100 rounded-full p-3">
              <Activity className="text-orange-600" size={28} />
            </div>
            <div>
              <p className="text-3xl font-bold text-orange-600">{stamped_in_count}</p>
              <p className="text-sm text-gray-500">Jetzt eingestempelt</p>
            </div>
            <button onClick={loadLiveStatus} className="ml-auto p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100" title="Aktualisieren">
              <Clock size={20} />
            </button>
          </div>
          {stamped_in.length > 0 ? (
            <div className="space-y-2">
              {stamped_in.map((s, idx) => (
                <div key={idx} className="flex items-center gap-3 p-3 bg-orange-50 rounded-lg border border-orange-100">
                  <div className="w-2 h-2 bg-orange-500 rounded-full animate-pulse"></div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate">{s.employee_name}</p>
                    <p className="text-xs text-gray-600 truncate">{s.object_name}</p>
                  </div>
                  <div className="text-right text-xs whitespace-nowrap">
                    <p className="text-gray-500">seit {s.check_in}</p>
                    <p className="text-orange-600 font-medium">{Math.floor(s.minutes_since / 60)}h {s.minutes_since % 60}m</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-4 text-gray-400">
              <p className="text-sm">Niemand eingestempelt</p>
            </div>
          )}
        </div>

        {/* Heute gestempelt/gebucht */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-green-100 rounded-full p-3">
              <CheckCircle className="text-green-600" size={28} />
            </div>
            <div>
              <p className="text-3xl font-bold text-green-600">{today_booked_count}</p>
              <p className="text-sm text-gray-500">Heute gebucht</p>
            </div>
          </div>
          {today_booked.length > 0 ? (
            <div className="space-y-2">
              {today_booked.map((s, idx) => (
                <div key={idx} className="flex items-center gap-3 p-3 bg-green-50 rounded-lg border border-green-100">
                  <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate">{s.employee_name}</p>
                    <p className="text-xs text-gray-600 truncate">{s.object_name}</p>
                  </div>
                  <div className="text-right text-xs whitespace-nowrap">
                    <p className="text-gray-500">{s.check_in} - {s.check_out}</p>
                    <p className="text-green-600 font-medium">{s.billed_hours}h</p>
                  </div>
                  {s.is_manual && <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">M</span>}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center py-4 text-gray-400 text-sm">Heute noch keine Buchungen</p>
          )}
        </div>

        {/* Aktive Dienstplan-Schichten */}
        {active_count > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-blue-100 rounded-full p-3">
              <Calendar className="text-blue-600" size={28} />
            </div>
            <div>
              <p className="text-3xl font-bold text-blue-600">{active_count}</p>
              <p className="text-sm text-gray-500">Dienstplan aktiv</p>
            </div>
          </div>
          <div className="space-y-2">
            {active.map((s, idx) => (
              <div key={idx} className="flex items-center gap-3 p-3 bg-blue-50 rounded-lg border border-blue-100">
                <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm truncate">{s.employee_name}</p>
                  <p className="text-xs text-gray-600 truncate">{s.object_name}</p>
                </div>
                <div className="text-right text-xs text-gray-500 whitespace-nowrap">
                  <p>{s.start_time} - {s.end_time}</p>
                </div>
                {s.is_driver && <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">Fahrer</span>}
              </div>
            ))}
          </div>
        </div>
        )}

        {/* Kommende Schichten */}
        {upcoming_count > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-gray-100 rounded-full p-3">
              <Clock className="text-gray-600" size={28} />
            </div>
            <div>
              <p className="text-3xl font-bold text-gray-600">{upcoming_count}</p>
              <p className="text-sm text-gray-500">Schichten kommen noch</p>
            </div>
          </div>
          <div className="space-y-2">
            {upcoming.map((s, idx) => (
              <div key={idx} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <div className="w-2 h-2 bg-gray-400 rounded-full"></div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{s.employee_name}</p>
                  <p className="text-xs text-gray-600 truncate">{s.object_name}</p>
                </div>
                <div className="text-right text-xs text-gray-500 whitespace-nowrap">
                  {s.start_time} - {s.end_time}
                </div>
              </div>
            ))}
          </div>
        </div>
        )}
      </div>
    );
  };

  const ReportsTab = () => (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold">Berichte & Auswertungen</h2>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">
          Bericht generieren
        </button>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <FileText className="text-blue-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">Monatsabrechnung</h3>
          <p className="text-sm text-gray-600">
            Detaillierte Stundenübersicht pro Mitarbeiter für den aktuellen Monat
          </p>
        </div>
        
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <Building2 className="text-green-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">Objektauswertung</h3>
          <p className="text-sm text-gray-600">
            Geleistete Stunden pro Kunde/Objekt mit Kostenübersicht
          </p>
        </div>
        
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <Download className="text-purple-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">Excel-Export</h3>
          <p className="text-sm text-gray-600">
            Vollständiger Datenexport für externe Lohnabrechnungssysteme
          </p>
        </div>
        
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <Shield className="text-orange-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">DSGVO-Bericht</h3>
          <p className="text-sm text-gray-600">
            Datenschutzkonforme Aufbereitung der Arbeitszeitdaten
          </p>
        </div>
      </div>
    </div>
  );


  // ==================== BOTTOM NAVIGATION ====================
  
  const BottomNav = () => {
    return (
      <>
        {/* Bottom Navigation Bar */}
        <div style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          backgroundColor: 'white',
          borderTop: '2px solid #e0e0e0',
          display: 'flex',
          justifyContent: 'space-around',
          padding: '8px 0',
          zIndex: 1000,
          boxShadow: '0 -2px 10px rgba(0,0,0,0.1)'
        }}>
          {/* Tab 1: Übersicht */}
          <button
            onClick={() => {
              setActiveTab('overview');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'overview' ? '#3b82f6' : '#666',
              fontWeight: activeTab === 'overview' ? 'bold' : 'normal'
            }}
          >
            <Activity size={24} />
            <span style={{ fontSize: '11px' }}>Übersicht</span>
          </button>

          {/* Tab 2: Dienstplan */}
          <button
            onClick={() => {
              setActiveTab('schedule');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'schedule' ? '#3b82f6' : '#666',
              fontWeight: activeTab === 'schedule' ? 'bold' : 'normal'
            }}
          >
            <Calendar size={24} />
            <span style={{ fontSize: '11px' }}>Dienstplan</span>
          </button>

          {/* Tab 3: Journal */}
          <button
            onClick={() => {
              setActiveTab('journal');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'journal' ? '#3b82f6' : '#666',
              fontWeight: activeTab === 'journal' ? 'bold' : 'normal'
            }}
          >
            <BookOpen size={24} />
            <span style={{ fontSize: '11px' }}>Journal</span>
          </button>

          {/* Tab 4: Genehmigungen */}
          <button
            onClick={() => {
              setActiveTab('genehmigungen');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'genehmigungen' ? '#3b82f6' : '#666',
              fontWeight: activeTab === 'genehmigungen' ? 'bold' : 'normal',
              position: 'relative'
            }}
          >
            <div style={{ position: 'relative', display: 'inline-flex' }}>
              <CheckCircle size={24} />
              {pendingCount > 0 && (
                <span style={{
                  position: 'absolute', top: '-6px', right: '-10px',
                  background: '#ef4444', color: 'white', borderRadius: '10px',
                  padding: '1px 5px', fontSize: '10px', fontWeight: 'bold', minWidth: '16px', textAlign: 'center'
                }}>
                  {pendingCount}
                </span>
              )}
            </div>
            <span style={{ fontSize: '11px' }}>Freigabe</span>
          </button>

          {/* Tab 5: Mehr */}
          <button
            onClick={() => setShowMoreMenu(!showMoreMenu)}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: showMoreMenu || ['employees', 'customers', 'live', 'abrechnungen', 'km-journal', 'km-verwaltung', 'offene-punkte', 'audit-log', 'login-log', 'ma-objekte', 'push-verwaltung', 'telegram-log', 'stamm-dienstplan', 'kunden-umsaetze', 'statistiken', 'lohn-uebersicht', 'krankmeldungen', 'posteingang', 'urlaub-verwaltung', 'monatsbestaetigung', 'genehmigungen'].includes(activeTab) ? '#3b82f6' : '#666',
              fontWeight: showMoreMenu || ['employees', 'customers', 'live', 'abrechnungen', 'km-journal', 'km-verwaltung', 'offene-punkte', 'audit-log', 'login-log', 'ma-objekte', 'push-verwaltung', 'telegram-log', 'stamm-dienstplan', 'kunden-umsaetze', 'statistiken', 'lohn-uebersicht', 'krankmeldungen', 'posteingang', 'urlaub-verwaltung', 'monatsbestaetigung', 'genehmigungen'].includes(activeTab) ? 'bold' : 'normal'
            }}
          >
            <Menu size={24} />
            <span style={{ fontSize: '11px' }}>Mehr</span>
          </button>
        </div>

        {/* Mehr-Overlay */}
        {showMoreMenu && (
          <div
            onClick={() => setShowMoreMenu(false)}
            style={{
              position: 'fixed',
              bottom: 0,
              left: 0,
              right: 0,
              top: 0,
              backgroundColor: 'rgba(0,0,0,0.5)',
              zIndex: 999,
              display: 'flex',
              alignItems: 'flex-end'
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: 'white',
                width: '100%',
                borderTopLeftRadius: '16px',
                borderTopRightRadius: '16px',
                padding: '20px',
                paddingBottom: '100px',
                boxShadow: '0 -4px 20px rgba(0,0,0,0.2)'
              }}
            >
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px'
              }}>
                <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1f2937' }}>Weitere Optionen</h3>
                <button
                  onClick={() => setShowMoreMenu(false)}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    padding: '8px'
                  }}
                >
                  <X size={24} color="#666" />
                </button>
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '70vh', overflowY: 'auto' }}>
                {/* GRUPPE: Uebersicht */}
                <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '1px', padding: '4px 8px' }}>Uebersicht</div>
                {[
                ].map(item => (
                  <button key={item.tab} onClick={() => { setActiveTab(item.tab); setShowMoreMenu(false); }}
                    style={{ width: '100%', padding: '14px 16px', backgroundColor: activeTab === item.tab ? '#3b82f6' : '#f3f4f6', color: activeTab === item.tab ? 'white' : '#333', border: 'none', borderRadius: '12px', fontSize: '15px', fontWeight: 'bold', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {item.icon} {item.label}
                    {liveStatus?.active_count > 0 && (
                      <span style={{ background: activeTab === item.tab ? 'white' : '#22c55e', color: activeTab === item.tab ? '#3b82f6' : 'white', borderRadius: '10px', padding: '2px 8px', fontSize: '12px', fontWeight: 'bold', marginLeft: 'auto' }}>
                        {liveStatus.active_count} aktiv
                      </span>
                    )}
                  </button>
                ))}

                {/* GRUPPE: Verwaltung */}
                <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '1px', padding: '12px 8px 4px' }}>Verwaltung</div>
                {[
                  { tab: 'employees', icon: <Users size={22} />, label: 'Mitarbeiter' },
                  { tab: 'customers', icon: <Building2 size={22} />, label: 'Kunden & Objekte' },
                  { tab: 'ma-objekte', icon: <Users size={22} />, label: 'MA-Objekt-Zuweisungen' },
                ].filter(item => isTabAllowed(item.tab)).map(item => (
                  <button key={item.tab} onClick={() => { setActiveTab(item.tab); setShowMoreMenu(false); }}
                    style={{ width: '100%', padding: '14px 16px', backgroundColor: activeTab === item.tab ? '#3b82f6' : '#f3f4f6', color: activeTab === item.tab ? 'white' : '#333', border: 'none', borderRadius: '12px', fontSize: '15px', fontWeight: 'bold', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {item.icon}
                    <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
                    {item.badgeKey && badgeCounts[item.badgeKey] > 0 && (
                      <span style={{ background: activeTab === item.tab ? 'white' : '#ef4444', color: activeTab === item.tab ? '#3b82f6' : 'white', borderRadius: '10px', padding: '2px 8px', fontSize: '12px', fontWeight: 'bold', minWidth: '22px', textAlign: 'center' }}>
                        {badgeCounts[item.badgeKey]}
                      </span>
                    )}
                  </button>
                ))}

                {/* GRUPPE: Finanzen */}
                <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '1px', padding: '12px 8px 4px' }}>Finanzen</div>
                {[
                  { tab: 'statistiken', icon: <TrendingUp size={22} />, label: 'BWA / Statistik' },
                  { tab: 'lohn-uebersicht', icon: <Calculator size={22} />, label: 'Lohnuebersicht' },
                  { tab: 'abrechnungen', icon: <FileText size={22} />, label: 'Abrechnungen' },
                  { tab: 'kunden-umsaetze', icon: <Building2 size={22} />, label: 'Kunden-Umsaetze' },
                  { tab: 'km-journal', icon: <BookOpen size={22} />, label: 'KM-Journal' },
                  { tab: 'km-verwaltung', icon: <TrendingUp size={22} />, label: 'KM-Verwaltung' },
                ].filter(item => isTabAllowed(item.tab)).map(item => (
                  <button key={item.tab} onClick={() => { setActiveTab(item.tab); setShowMoreMenu(false); }}
                    style={{ width: '100%', padding: '14px 16px', backgroundColor: activeTab === item.tab ? '#3b82f6' : '#f3f4f6', color: activeTab === item.tab ? 'white' : '#333', border: 'none', borderRadius: '12px', fontSize: '15px', fontWeight: 'bold', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {item.icon}
                    <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
                    {item.badgeKey && badgeCounts[item.badgeKey] > 0 && (
                      <span style={{ background: activeTab === item.tab ? 'white' : '#ef4444', color: activeTab === item.tab ? '#3b82f6' : 'white', borderRadius: '10px', padding: '2px 8px', fontSize: '12px', fontWeight: 'bold', minWidth: '22px', textAlign: 'center' }}>
                        {badgeCounts[item.badgeKey]}
                      </span>
                    )}
                  </button>
                ))}

                {/* GRUPPE: Kommunikation (mit Badges) */}
                <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '1px', padding: '12px 8px 4px' }}>Kommunikation</div>
                {/* Genehmigungen - eigener Button mit pendingCount */}
                <button onClick={() => { setActiveTab('genehmigungen'); setShowMoreMenu(false); }}
                  style={{ width: '100%', padding: '14px 16px', backgroundColor: activeTab === 'genehmigungen' ? '#3b82f6' : '#f3f4f6', color: activeTab === 'genehmigungen' ? 'white' : '#333', border: 'none', borderRadius: '12px', fontSize: '15px', fontWeight: 'bold', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px', position: 'relative' }}>
                  <CheckCircle size={22} />
                  <span style={{ flex: 1, textAlign: 'left' }}>Genehmigungen</span>
                  {pendingCount > 0 && (
                    <span style={{ background: activeTab === 'genehmigungen' ? 'white' : '#ef4444', color: activeTab === 'genehmigungen' ? '#3b82f6' : 'white', borderRadius: '10px', padding: '2px 8px', fontSize: '12px', fontWeight: 'bold', minWidth: '22px', textAlign: 'center' }}>
                      {pendingCount}
                    </span>
                  )}
                </button>

                {[
                  { tab: 'offene-punkte', icon: <Bell size={22} />, label: 'Offene Punkte', badgeKey: 'offene_punkte' },
                  { tab: 'krankmeldungen', icon: <AlertCircle size={22} />, label: 'Krankmeldungen', badgeKey: 'krankmeldungen' },
                  { tab: 'posteingang', icon: <Mail size={22} />, label: 'Posteingang', badgeKey: 'posteingang' },
                  { tab: 'urlaub-verwaltung', icon: <Calendar size={22} />, label: 'Urlaubsverwaltung', badgeKey: 'urlaub' },
                  { tab: 'monatsbestaetigung', icon: <Check size={22} />, label: 'Monatsbestätigungen', badgeKey: 'monatsbestaetigung' },
                ].filter(item => isTabAllowed(item.tab)).map(item => (
                  <button key={item.tab} onClick={() => { setActiveTab(item.tab); setShowMoreMenu(false); }}
                    style={{ width: '100%', padding: '14px 16px', backgroundColor: activeTab === item.tab ? '#3b82f6' : '#f3f4f6', color: activeTab === item.tab ? 'white' : '#333', border: 'none', borderRadius: '12px', fontSize: '15px', fontWeight: 'bold', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px', position: 'relative' }}>
                    {item.icon}
                    <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
                    {badgeCounts[item.badgeKey] > 0 && (
                      <span style={{ background: activeTab === item.tab ? 'white' : '#ef4444', color: activeTab === item.tab ? '#3b82f6' : 'white', borderRadius: '10px', padding: '2px 8px', fontSize: '12px', fontWeight: 'bold', minWidth: '22px', textAlign: 'center' }}>
                        {badgeCounts[item.badgeKey]}
                      </span>
                    )}
                  </button>
                ))}

                {/* GRUPPE: System */}
                {isAdmin && <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '1px', padding: '12px 8px 4px' }}>System</div>}
                {[
                  { tab: 'stamm-dienstplan', icon: <Calendar size={22} />, label: 'Stamm-Dienstplan' },
                  { tab: 'push-verwaltung', icon: <Smartphone size={22} />, label: 'Telegram-Verwaltung', badgeKey: 'telegram' },
                  { tab: 'telegram-log', icon: <MessageSquare size={22} />, label: 'Telegram-Log' },
                  { tab: 'audit-log', icon: <ClipboardList size={22} />, label: 'Audit-Log' },
                  { tab: 'login-log', icon: <LogIn size={22} />, label: 'Login-Protokoll' },
                ].filter(item => isTabAllowed(item.tab)).map(item => (
                  <button key={item.tab} onClick={() => { setActiveTab(item.tab); setShowMoreMenu(false); }}
                    style={{ width: '100%', padding: '14px 16px', backgroundColor: activeTab === item.tab ? '#3b82f6' : '#f3f4f6', color: activeTab === item.tab ? 'white' : '#333', border: 'none', borderRadius: '12px', fontSize: '15px', fontWeight: 'bold', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {item.icon}
                    <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
                    {item.badgeKey && badgeCounts[item.badgeKey] > 0 && (
                      <span style={{ background: activeTab === item.tab ? 'white' : '#ef4444', color: activeTab === item.tab ? '#3b82f6' : 'white', borderRadius: '10px', padding: '2px 8px', fontSize: '12px', fontWeight: 'bold', minWidth: '22px', textAlign: 'center' }}>
                        {badgeCounts[item.badgeKey]}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Spacer für Bottom Nav */}
        <div style={{ height: '80px' }}></div>
      </>
    );
  };

  // ==================== MAIN RETURN ====================

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">SEDA24 {isAdmin ? 'Admin' : 'Objektleitung'}</h1>
              <p className="text-sm text-gray-600">
                Verwaltungszentrale - {new Date().toLocaleDateString('de-DE', { 
                  weekday: 'long', 
                  year: 'numeric', 
                  month: 'long', 
                  day: 'numeric' 
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => navigate('/dashboard')}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
                title="Zur Stempel-Ansicht"
              >
                <Clock size={20} />
                <span className="hidden sm:inline">Stempeln</span>
              </button>
              <button
                onClick={() => { setShowPwChange(true); setPwOld(''); setPwNew(''); setPwConfirm(''); setPwError(''); setPwSuccess(''); }}
                className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 flex items-center gap-2"
                title="Passwort ändern"
              >
                <Lock size={20} />
              </button>
              <button
                onClick={() => {
                  localStorage.clear();
                  window.location.href = '/login';
                }}
                className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2"
              >
                <LogOut size={20} />
                Abmelden
              </button>
            </div>
          </div>
        </div>
      </div>



      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && <OverviewTab />}
        {activeTab === 'employees' && <EmployeesTab />}
        {activeTab === 'customers' && <CustomersTab />}
        {activeTab === 'schedule' && <ScheduleTab />}
        {/* hours tab removed - Sollstunden jetzt in Kundenverwaltung integriert */}
        {activeTab === 'journal' && <JournalTab employees={activeEmployees} customers={customers} showToast={showToast} setShowKmModal={setShowKmModal} setKmBookingInfo={setKmBookingInfo} setKmDistance={setKmDistance}
          selectedEmployee={journalEmployee} setSelectedEmployee={setJournalEmployee}
          dateFrom={journalDateFrom} setDateFrom={setJournalDateFrom}
          dateTo={journalDateTo} setDateTo={setJournalDateTo}
          selectedObject={journalObject} setSelectedObject={setJournalObject}
          selectedServiceType={journalServiceType} setSelectedServiceType={setJournalServiceType}
          selectedCleaningType={journalCleaningType} setSelectedCleaningType={setJournalCleaningType}
          selectedEntryType={journalEntryType} setSelectedEntryType={setJournalEntryType}
          sortField={journalSortField} setSortField={setJournalSortField}
          sortDirection={journalSortDir} setSortDirection={setJournalSortDir}
        />}
        {/* reports tab removed */}
        {activeTab === 'abrechnungen' && <AbrechnungenTab />}
        {activeTab === 'km-journal' && <KmJournalTab employees={activeEmployees} customers={customers} showToast={showToast}
          selectedEmployee={kmJournalEmployee} setSelectedEmployee={setKmJournalEmployee}
          dateFrom={kmJournalDateFrom} setDateFrom={setKmJournalDateFrom}
          dateTo={kmJournalDateTo} setDateTo={setKmJournalDateTo}
          selectedObject={kmJournalObject} setSelectedObject={setKmJournalObject}
        />}
        {activeTab === 'km-verwaltung' && <KmVerwaltungTab showToast={showToast} />}
        {activeTab === 'lohn-uebersicht' && <LohnUebersichtTab />}
        {activeTab === 'offene-punkte' && <OffenePunkteTab />}
        {activeTab === 'audit-log' && <AuditLogTab />}
        {activeTab === 'login-log' && <LoginLogTab />}
        {activeTab === 'ma-objekte' && <MitarbeiterObjekteTab />}
        {activeTab === 'push-verwaltung' && <PushVerwaltungTab />}
        {activeTab === 'telegram-log' && <TelegramLogTab employees={activeEmployees} />}
        {activeTab === 'urlaub-verwaltung' && <UrlaubVerwaltungTab />}
        {activeTab === 'krankmeldungen' && <KrankmeldungTab employees={activeEmployees} />}
        {activeTab === 'posteingang' && <PosteingangTab employees={activeEmployees} />}
        {activeTab === 'monatsbestaetigung' && <MonatsbestaetigungenTab showToast={showToast} />}
        {activeTab === 'stamm-dienstplan' && <StammDienstplanTab employees={activeEmployees} showToast={showToast} />}
        {activeTab === 'kunden-umsaetze' && <KundenUmsaetzeTab showToast={showToast} />}
        {activeTab === 'statistiken' && <StatistikenTab />}
        {activeTab === 'genehmigungen' && <GenehmigungenTab showToast={showToast} />}
      </div>

      {/* Toast Notification */}
      {toast && (
        <div className={`
          fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 z-50
          ${toast.type === 'success' ? 'bg-green-500 text-white' : ''}
          ${toast.type === 'error' ? 'bg-red-500 text-white' : ''}
          ${toast.type === 'info' ? 'bg-blue-500 text-white' : ''}
        `}>
          {toast.type === 'success' && <Check size={20} />}
          {toast.type === 'error' && <X size={20} />}
          {toast.type === 'info' && <AlertCircle size={20} />}
          {toast.message}
        </div>
      )}

      {/* Objekt + Sollstunden Modal */}
      {showObjectModal && editingObject && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-bold">Objekt bearbeiten</h3>
              <button onClick={() => setShowObjectModal(false)} className="p-1 hover:bg-gray-100 rounded">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-5">
              {/* Objekt-Name + Adresse */}
              <div className="space-y-3">
                <div>
                  <label className="text-sm font-medium text-gray-700">Name</label>
                  <input
                    type="text"
                    value={objectForm.name}
                    onChange={(e) => setObjectForm({...objectForm, name: e.target.value})}
                    className="w-full mt-1 p-2 border rounded-lg"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700">Adresse</label>
                  <input
                    type="text"
                    value={objectForm.address}
                    onChange={(e) => setObjectForm({...objectForm, address: e.target.value})}
                    className="w-full mt-1 p-2 border rounded-lg"
                  />
                </div>
              </div>

              {/* Sollstunden pro Wochentag */}
              <div>
                <label className="text-sm font-bold text-gray-700 block mb-2">Sollstunden pro Wochentag</label>
                <div className="space-y-2">
                  {sollstundenForm.map((day, idx) => (
                    <div key={idx} className={`flex items-center gap-2 p-2 rounded-lg ${day.active ? 'bg-blue-50 border border-blue-200' : 'bg-gray-50 border border-gray-200'}`}>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={day.active}
                          onChange={(e) => {
                            const updated = [...sollstundenForm];
                            updated[idx] = { ...updated[idx], active: e.target.checked };
                            setSollstundenForm(updated);
                          }}
                          className="rounded"
                        />
                        <span className={`text-sm font-medium w-8 ${day.active ? 'text-blue-700' : 'text-gray-400'}`}>{WEEKDAY_SHORT[idx]}</span>
                      </label>
                      {day.active ? (
                        <>
                          <input
                            type="time"
                            value={day.start_time}
                            onChange={(e) => {
                              const updated = [...sollstundenForm];
                              updated[idx] = { ...updated[idx], start_time: e.target.value };
                              updated[idx].standard_hours = calcHoursFromTimes(e.target.value, updated[idx].end_time);
                              setSollstundenForm(updated);
                            }}
                            className="p-1.5 border rounded text-sm w-24"
                          />
                          <span className="text-gray-400">-</span>
                          <input
                            type="time"
                            value={day.end_time}
                            onChange={(e) => {
                              const updated = [...sollstundenForm];
                              updated[idx] = { ...updated[idx], end_time: e.target.value };
                              updated[idx].standard_hours = calcHoursFromTimes(updated[idx].start_time, e.target.value);
                              setSollstundenForm(updated);
                            }}
                            className="p-1.5 border rounded text-sm w-24"
                          />
                          <span className="text-sm text-gray-500 ml-auto whitespace-nowrap">
                            = <span className="font-bold text-blue-700">{day.standard_hours || '0'}h</span>
                          </span>
                        </>
                      ) : (
                        <span className="text-xs text-gray-400 italic ml-2">Kein Einsatz</span>
                      )}
                    </div>
                  ))}
                </div>
                {/* Wochensumme */}
                <div className="mt-2 text-right text-sm text-gray-600">
                  Woche gesamt: <span className="font-bold">
                    {sollstundenForm.filter(d => d.active).reduce((sum, d) => sum + (parseFloat(d.standard_hours) || 0), 0).toFixed(2)}h
                  </span>
                </div>
              </div>
            </div>

            <div className="sticky bottom-0 bg-white border-t px-6 py-4 flex gap-3">
              <button onClick={() => setShowObjectModal(false)} className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300">
                Abbrechen
              </button>
              <button onClick={handleSaveObject} className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Employee Modal */}
      {showNewEmployeeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">
              {editingEmployee ? 'Mitarbeiter bearbeiten' : 'Neuer Mitarbeiter'}
            </h3>
            
            <div className="space-y-4">
              <input
                type="text"
                placeholder="Personal-Nr"
                value={employeeForm.personal_nr}
                onChange={(e) => setEmployeeForm({...employeeForm, personal_nr: e.target.value})}
                className="w-full p-2 border rounded-lg"
              />
              <input
                type="text"
                placeholder="Vorname"
                value={employeeForm.first_name}
                onChange={(e) => setEmployeeForm({...employeeForm, first_name: e.target.value})}
                className="w-full p-2 border rounded-lg"
              />
              <input
                type="text"
                placeholder="Nachname"
                value={employeeForm.last_name}
                onChange={(e) => setEmployeeForm({...employeeForm, last_name: e.target.value})}
                className="w-full p-2 border rounded-lg"
              />
              <input
                type="email"
                placeholder="Email"
                value={employeeForm.email}
                onChange={(e) => setEmployeeForm({...employeeForm, email: e.target.value})}
                className="w-full p-2 border rounded-lg"
              />
              <input
                type="number"
                step="0.01"
                placeholder="Stundensatz"
                value={employeeForm.hourly_rate}
                onChange={(e) => setEmployeeForm({...employeeForm, hourly_rate: e.target.value})}
                className="w-full p-2 border rounded-lg"
              />
              <select
                value={employeeForm.tracking_mode}
                onChange={(e) => setEmployeeForm({...employeeForm, tracking_mode: e.target.value})}
                className="w-full p-2 border rounded-lg"
              >
                <option value="A">Kategorie A</option>
                <option value="B">Kategorie B</option>
                <option value="C">Kategorie C</option>
              </select>
              <label className="flex items-center gap-2 p-2 border rounded-lg cursor-pointer hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={employeeForm.enforce_min_duration}
                  onChange={(e) => setEmployeeForm({...employeeForm, enforce_min_duration: e.target.checked})}
                  className="rounded"
                />
                <span className="text-sm">Mindest-Stempeldauer (Bie2)</span>
              </label>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowNewEmployeeModal(false)}
                className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
              <button
                onClick={handleSaveEmployee}
                className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Customer Modal */}
      {showNewCustomerModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">
              {editingCustomer ? 'Kunde bearbeiten' : 'Neuer Kunde'}
            </h3>
            
            <div className="space-y-4">
              <input
                type="text"
                placeholder="Name"
                value={customerForm.name}
                onChange={(e) => setCustomerForm({...customerForm, name: e.target.value})}
                className="w-full p-2 border rounded-lg"
              />
              <input
                type="text"
                placeholder="Adresse"
                value={customerForm.address}
                onChange={(e) => setCustomerForm({...customerForm, address: e.target.value})}
                className="w-full p-2 border rounded-lg"
              />
              {isAdmin && (
                <input
                  type="number"
                  step="0.01"
                  placeholder="Stundensatz"
                  value={customerForm.hourly_rate}
                  onChange={(e) => setCustomerForm({...customerForm, hourly_rate: e.target.value})}
                  className="w-full p-2 border rounded-lg"
                />
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowNewCustomerModal(false)}
                className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
              <button
                onClick={handleSaveCustomer}
                className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bottom Navigation */}
      <BottomNav />

      {/* Passwort ändern Modal */}
      {showPwChange && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={() => setShowPwChange(false)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold">Passwort ändern</h3>
              <button onClick={() => setShowPwChange(false)} className="p-1 hover:bg-gray-100 rounded"><X size={20} /></button>
            </div>

            {pwError && <div className="bg-red-50 text-red-600 p-3 rounded-lg mb-3 text-sm">{pwError}</div>}
            {pwSuccess && <div className="bg-green-50 text-green-600 p-3 rounded-lg mb-3 text-sm">{pwSuccess}</div>}

            {!pwSuccess ? (
              <form onSubmit={async (e) => {
                e.preventDefault();
                setPwError('');
                if (pwNew !== pwConfirm) { setPwError('Neue Passwörter stimmen nicht überein!'); return; }
                if (pwNew.length < 6) { setPwError('Neues Passwort muss mindestens 6 Zeichen haben!'); return; }
                setPwLoading(true);
                try {
                  await api.post('/auth/change-password', { new_password: pwNew, old_password: pwOld });
                  setPwSuccess('Passwort erfolgreich geändert!');
                } catch (err) {
                  setPwError(err.response?.data?.detail || 'Fehler beim Ändern');
                } finally {
                  setPwLoading(false);
                }
              }}>
                <input type="password" placeholder="Altes Passwort" value={pwOld} onChange={e => setPwOld(e.target.value)} required
                  className="w-full px-4 py-3 mb-3 border rounded-lg focus:outline-none focus:border-blue-500" />
                <input type="password" placeholder="Neues Passwort" value={pwNew} onChange={e => setPwNew(e.target.value)} autoComplete="new-password" required
                  className="w-full px-4 py-3 mb-3 border rounded-lg focus:outline-none focus:border-blue-500" />
                <input type="password" placeholder="Neues Passwort bestätigen" value={pwConfirm} onChange={e => setPwConfirm(e.target.value)} autoComplete="new-password" required
                  className="w-full px-4 py-3 mb-3 border rounded-lg focus:outline-none focus:border-blue-500" />
                <button type="submit" disabled={pwLoading}
                  className="w-full py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-semibold disabled:opacity-50">
                  {pwLoading ? 'Speichere...' : 'Passwort ändern'}
                </button>
              </form>
            ) : (
              <button onClick={() => setShowPwChange(false)}
                className="w-full py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-semibold">
                Schliessen
              </button>
            )}
          </div>
        </div>
      )}

      {/* KM-Popup nach manueller Buchung (auf Hauptebene, damit Tab-Wechsel den State nicht zurücksetzt) */}
      {showKmModal && kmBookingInfo && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <div className="flex items-center gap-2 mb-4">
              <MapPin className="w-5 h-5 text-blue-500" />
              <h3 className="text-lg font-bold">KM-Fahrt eintragen?</h3>
            </div>

            <div className="bg-blue-50 p-3 rounded-lg mb-4 text-sm">
              <p><strong>{kmBookingInfo.employee_name}</strong></p>
              <p>{kmBookingInfo.object_name} - {new Date(kmBookingInfo.date).toLocaleDateString('de-DE')}</p>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium mb-1">Kilometer (einfache Strecke)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={kmDistance}
                onChange={(e) => setKmDistance(e.target.value)}
                className="w-full p-2 border rounded-lg text-lg"
                placeholder="z.B. 25.5"
                autoFocus
              />
              {kmDistance > 0 && (
                <p className="text-sm text-gray-500 mt-1">= {(parseFloat(kmDistance) * 0.30).toFixed(2)} EUR (0,30 EUR/km)</p>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowKmModal(false)}
                className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Ohne KM
              </button>
              <button
                onClick={handleSaveKm}
                disabled={!kmDistance || parseFloat(kmDistance) <= 0}
                className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300"
              >
                KM speichern
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDashboard;