// ScheduleTab.jsx - Vollständig editierbarer Dienstplan mit Add- und Edit-Modal
// Speichern unter: /root/zeiterfassung/frontend/src/components/ScheduleTab.jsx

import React, { useState, useEffect } from 'react';
import { Calendar, Clock, Users, Copy, AlertCircle, Check, X, Edit2, UserPlus, Coffee } from 'lucide-react';
import api from "../services/api";

const ScheduleTab = () => {
  const [weekOffset, setWeekOffset] = useState(0);
  const [weekData, setWeekData] = useState(null);
  const [editingCell, setEditingCell] = useState(null);
  const [conflicts, setConflicts] = useState([]);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [unsavedChanges, setUnsavedChanges] = useState([]);
  
  // States für das Add-Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [newShiftData, setNewShiftData] = useState({
    dayIndex: null,
    weekday: null,
    employee_id: '',
    object_id: '',
    start_time: '06:00',
    end_time: '14:00'
  });

  // States für das Edit-Modal
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState(null);

  // Weekday Namen für Anzeige
  const WEEKDAY_NAMES = {
    0: 'Montag',
    1: 'Dienstag',
    2: 'Mittwoch',
    3: 'Donnerstag',
    4: 'Freitag',
    5: 'Samstag',
    6: 'Sonntag'
  };

  // Farben für verschiedene Status
  const statusColors = {
    normal: 'bg-green-100 border-green-300',
    urlaub: 'bg-yellow-100 border-yellow-300',
    krank: 'bg-red-100 border-red-300',
    vertretung: 'bg-blue-100 border-blue-300'
  };

  const statusIcons = {
    normal: null,
    urlaub: '🏖️',
    krank: '🤒',
    vertretung: '↔️'
  };

  // Lade Wochendaten
  const loadWeekData = async () => {
    setLoading(true);
    try {
      const response = await api.get(`/admin/schedules/week?week_offset=${weekOffset}`);
      setWeekData(response.data);
      
      // Prüfe auf Konflikte
      const conflictResponse = await api.get(`/admin/schedules/conflicts?week_offset=${weekOffset}`);
      setConflicts(conflictResponse.data.conflicts || []);
    } catch (error) {
      console.error('Fehler beim Laden der Wochendaten:', error);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadWeekData();
  }, [weekOffset]);

  // Funktion zum Öffnen des Add-Modals
  const openAddShiftModal = (dayIndex, weekday) => {
    setNewShiftData({
      dayIndex,
      weekday,
      employee_id: '',
      object_id: '',
      start_time: '06:00',
      end_time: '14:00'
    });
    setShowAddModal(true);
  };

  // Neue Schicht speichern - MIT STATUS FIX
  const saveNewShift = async () => {
    if (!newShiftData.employee_id || !newShiftData.object_id) {
      alert('Bitte Mitarbeiter und Objekt auswählen');
      return;
    }
    
    try {
      await api.post('/admin/schedules/quick-assign', {
        employee_id: parseInt(newShiftData.employee_id),
        object_id: parseInt(newShiftData.object_id),
        weekday: newShiftData.weekday,
        start_time: newShiftData.start_time,
        end_time: newShiftData.end_time,
        status: 'normal'  // WICHTIG: Status hinzugefügt!
      });
      
      setShowAddModal(false);
      await loadWeekData();
    } catch (error) {
      console.error('Fehler beim Hinzufügen:', error);
      alert('Fehler beim Hinzufügen der Schicht');
    }
  };

  // Edit-Modal öffnen - MIT STATUS FIX
  const openEditModal = (schedule, dayIndex) => {
    setEditingSchedule({
      ...schedule,
      dayIndex,
      employee_id: schedule.employee_id,
      object_id: schedule.object_id,
      start_time: schedule.start_time,
      end_time: schedule.end_time,
      status: schedule.status || 'normal'  // Status wird korrekt geladen
    });
    setShowEditModal(true);
  };

  // Bearbeitete Schicht speichern
  const saveEditedShift = async () => {
    try {
      await api.post('/admin/schedules/bulk-update', [{
        id: editingSchedule.id,
        employee_id: parseInt(editingSchedule.employee_id),
        object_id: parseInt(editingSchedule.object_id),
        start_time: editingSchedule.start_time,
        end_time: editingSchedule.end_time,
        status: editingSchedule.status  // Status wird mitgesendet
      }]);
      
      setShowEditModal(false);
      await loadWeekData();
    } catch (error) {
      console.error('Fehler beim Speichern:', error);
      alert('Fehler beim Speichern der Änderungen');
    }
  };

  // Schicht löschen
  const deleteShift = async (scheduleId) => {
    if (confirm('Schicht wirklich löschen?')) {
      try {
        await api.delete(`/admin/schedules/${scheduleId}`);
        await loadWeekData();
      } catch (error) {
        console.error('Fehler beim Löschen:', error);
      }
    }
  };

  // Woche kopieren
  const copyWeek = async (targetWeekOffset) => {
    try {
      const sourceDate = new Date();
      sourceDate.setDate(sourceDate.getDate() - sourceDate.getDay() + 1); // Montag
      sourceDate.setDate(sourceDate.getDate() + (weekOffset * 7));
      
      const targetDate = new Date();
      targetDate.setDate(targetDate.getDate() - targetDate.getDay() + 1);
      targetDate.setDate(targetDate.getDate() + (targetWeekOffset * 7));
      
      await api.post('/admin/schedules/copy-week', {
        source_week: sourceDate.toISOString(),
        target_week: targetDate.toISOString()
      });
      
      setWeekOffset(targetWeekOffset);
      setShowCopyModal(false);
    } catch (error) {
      console.error('Fehler beim Kopieren:', error);
    }
  };

  if (loading && !weekData) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!weekData) {
    return <div>Keine Daten verfügbar</div>;
  }

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      {/* Header mit Wochennavigation */}
      <div className="bg-white rounded-lg shadow-md p-4 mb-6">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setWeekOffset(weekOffset - 1)}
              className="p-2 hover:bg-gray-100 rounded"
            >
              ←
            </button>
            <h2 className="text-xl font-bold">
              KW {weekData.week_number} / {weekData.year}
            </h2>
            <button
              onClick={() => setWeekOffset(weekOffset + 1)}
              className="p-2 hover:bg-gray-100 rounded"
            >
              →
            </button>
            <button
              onClick={() => setWeekOffset(0)}
              className="text-sm text-blue-500 hover:underline"
            >
              Heute
            </button>
          </div>
          
          <div className="flex gap-2">
            <button
              onClick={() => setShowCopyModal(true)}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 flex items-center gap-2"
            >
              <Copy size={16} />
              Woche kopieren
            </button>
            <button
              onClick={loadWeekData}
              className="px-4 py-2 border rounded hover:bg-gray-50"
            >
              Aktualisieren
            </button>
          </div>
        </div>
      </div>

      {/* Konflikte Anzeige */}
      {conflicts.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-2 text-red-700 font-semibold mb-2">
            <AlertCircle size={20} />
            {conflicts.length} Konflikte gefunden
          </div>
          <ul className="text-sm text-red-600 space-y-1">
            {conflicts.slice(0, 3).map((conflict, i) => (
              <li key={i}>
                • {conflict.type === 'zeitüberschneidung' 
                    ? `${conflict.employee} hat überlappende Schichten am ${conflict.weekday}`
                    : `${conflict.object} hat keine Zuweisung am ${conflict.weekday}`}
              </li>
            ))}
            {conflicts.length > 3 && (
              <li>... und {conflicts.length - 3} weitere</li>
            )}
          </ul>
        </div>
      )}

      {/* Wochenplan Grid */}
      <div className="bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-100">
              <tr>
                {weekData.days.map((day, index) => (
                  <th key={index} className="border p-2 text-center">
                    <div className="font-bold">{day.weekday}</div>
                    <div className="text-xs text-gray-500">
                      {new Date(day.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {weekData.days.map((day, dayIndex) => (
                  <td key={dayIndex} className="border p-2 align-top min-w-[200px]">
                    <div className="space-y-2">
                      {/* Klickbare Schichten */}
                      {day.schedules.map((schedule) => (
                        <div
                          key={schedule.id}
                          className={`p-2 rounded border-2 ${statusColors[schedule.status || 'normal']} relative cursor-pointer hover:shadow-lg transition-shadow`}
                          onClick={() => openEditModal(schedule, dayIndex)}
                        >
                          {/* Status Icon */}
                          {statusIcons[schedule.status] && (
                            <span className="absolute top-1 right-1 text-lg">
                              {statusIcons[schedule.status]}
                            </span>
                          )}
                          
                          {/* Mitarbeiter Name */}
                          <div className="font-semibold text-sm">
                            {schedule.employee_name}
                          </div>
                          
                          {/* Objekt */}
                          <div className="text-xs text-gray-600">
                            {schedule.object_name}
                          </div>
                          
                          {/* Zeit */}
                          <div className="text-xs mt-1 flex items-center gap-1">
                            <Clock size={12} />
                            <span>{schedule.start_time} - {schedule.end_time}</span>
                            <span className="ml-2">({schedule.planned_hours}h)</span>
                          </div>
                          
                          {/* Vertretung Info */}
                          {schedule.replacement_for && (
                            <div className="text-xs text-blue-600 mt-1">
                              Vertretung für MA-{schedule.replacement_for}
                            </div>
                          )}
                        </div>
                      ))}
                      
                      {/* Neue Schicht Button */}
                      <button
                        onClick={() => openAddShiftModal(dayIndex, day.weekday_index)}
                        className="w-full p-2 border-2 border-dashed border-gray-300 rounded text-gray-400 hover:border-gray-400 hover:text-gray-600 text-xs"
                      >
                        + Schicht hinzufügen
                      </button>
                    </div>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Legende */}
      <div className="mt-6 bg-white rounded-lg shadow p-4">
        <h3 className="font-semibold mb-2">Legende</h3>
        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-green-100 border-2 border-green-300 rounded"></div>
            <span>Normal</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-yellow-100 border-2 border-yellow-300 rounded"></div>
            <span>Urlaub</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-red-100 border-2 border-red-300 rounded"></div>
            <span>Krank</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-blue-100 border-2 border-blue-300 rounded"></div>
            <span>Vertretung</span>
          </div>
        </div>
      </div>

      {/* Copy Week Modal */}
      {showCopyModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 className="text-lg font-semibold mb-4">Woche kopieren</h3>
            <p className="mb-4">
              Kopiere KW {weekData.week_number} in welche Woche?
            </p>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => copyWeek(weekOffset + 1)}
                className="p-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                Nächste Woche
              </button>
              <button
                onClick={() => copyWeek(weekOffset + 2)}
                className="p-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                In 2 Wochen
              </button>
              <button
                onClick={() => copyWeek(weekOffset + 3)}
                className="p-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                In 3 Wochen
              </button>
              <button
                onClick={() => copyWeek(weekOffset + 4)}
                className="p-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                In 4 Wochen
              </button>
            </div>
            <button
              onClick={() => setShowCopyModal(false)}
              className="mt-4 w-full p-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {/* Add Shift Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 className="text-lg font-semibold mb-4">
              Neue Schicht hinzufügen - {WEEKDAY_NAMES[newShiftData.dayIndex]}
            </h3>
            
            <div className="space-y-4">
              {/* Mitarbeiter Dropdown */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Mitarbeiter auswählen
                </label>
                <select
                  value={newShiftData.employee_id}
                  onChange={(e) => setNewShiftData({...newShiftData, employee_id: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">-- Mitarbeiter wählen --</option>
                  {weekData?.employees.map(emp => (
                    <option key={emp.id} value={emp.id}>
                      {emp.personal_nr} - {emp.name}
                    </option>
                  ))}
                </select>
              </div>
              
              {/* Objekt Dropdown */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Objekt auswählen
                </label>
                <select
                  value={newShiftData.object_id}
                  onChange={(e) => setNewShiftData({...newShiftData, object_id: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">-- Objekt wählen --</option>
                  {weekData?.objects.map(obj => (
                    <option key={obj.id} value={obj.id}>
                      {obj.name} {obj.customer_name && `(${obj.customer_name})`}
                    </option>
                  ))}
                </select>
              </div>
              
              {/* Zeitauswahl */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Von
                  </label>
                  <input
                    type="time"
                    value={newShiftData.start_time}
                    onChange={(e) => setNewShiftData({...newShiftData, start_time: e.target.value})}
                    className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Bis
                  </label>
                  <input
                    type="time"
                    value={newShiftData.end_time}
                    onChange={(e) => setNewShiftData({...newShiftData, end_time: e.target.value})}
                    className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              
              {/* Stunden-Vorschau */}
              <div className="bg-gray-100 p-3 rounded">
                <span className="text-sm text-gray-600">Geplante Stunden: </span>
                <span className="font-semibold">
                  {(() => {
                    const start = newShiftData.start_time.split(':');
                    const end = newShiftData.end_time.split(':');
                    const hours = (parseInt(end[0]) - parseInt(start[0])) + 
                                 (parseInt(end[1]) - parseInt(start[1])) / 60;
                    return hours.toFixed(1) + 'h';
                  })()}
                </span>
              </div>
            </div>
            
            {/* Buttons */}
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Abbrechen
              </button>
              <button
                onClick={saveNewShift}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Schicht hinzufügen
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Shift Modal */}
      {showEditModal && editingSchedule && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 className="text-lg font-semibold mb-4">
              Schicht bearbeiten - {WEEKDAY_NAMES[editingSchedule.dayIndex]}
            </h3>
            
            <div className="space-y-4">
              {/* Mitarbeiter Dropdown */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Mitarbeiter
                </label>
                <select
                  value={editingSchedule.employee_id}
                  onChange={(e) => setEditingSchedule({...editingSchedule, employee_id: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {weekData?.employees.map(emp => (
                    <option key={emp.id} value={emp.id}>
                      {emp.personal_nr} - {emp.name}
                    </option>
                  ))}
                </select>
              </div>
              
              {/* Objekt Dropdown */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Objekt
                </label>
                <select
                  value={editingSchedule.object_id}
                  onChange={(e) => setEditingSchedule({...editingSchedule, object_id: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {weekData?.objects.map(obj => (
                    <option key={obj.id} value={obj.id}>
                      {obj.name} {obj.customer_name && `(${obj.customer_name})`}
                    </option>
                  ))}
                </select>
              </div>
              
              {/* Status */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Status
                </label>
                <select
                  value={editingSchedule.status}
                  onChange={(e) => setEditingSchedule({...editingSchedule, status: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="normal">Normal</option>
                  <option value="urlaub">Urlaub</option>
                  <option value="krank">Krank</option>
                  <option value="vertretung">Vertretung</option>
                </select>
              </div>
              
              {/* Zeitauswahl */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Von
                  </label>
                  <input
                    type="time"
                    value={editingSchedule.start_time}
                    onChange={(e) => setEditingSchedule({...editingSchedule, start_time: e.target.value})}
                    className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Bis
                  </label>
                  <input
                    type="time"
                    value={editingSchedule.end_time}
                    onChange={(e) => setEditingSchedule({...editingSchedule, end_time: e.target.value})}
                    className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              
              {/* Stunden-Vorschau */}
              <div className="bg-gray-100 p-3 rounded">
                <span className="text-sm text-gray-600">Geplante Stunden: </span>
                <span className="font-semibold">
                  {(() => {
                    const start = editingSchedule.start_time.split(':');
                    const end = editingSchedule.end_time.split(':');
                    const hours = (parseInt(end[0]) - parseInt(start[0])) + 
                                 (parseInt(end[1]) - parseInt(start[1])) / 60;
                    return hours.toFixed(1) + 'h';
                  })()}
                </span>
              </div>
            </div>
            
            {/* Buttons */}
            <div className="flex justify-between mt-6">
              <button
                onClick={async () => {
                  if (confirm('Schicht wirklich löschen?')) {
                    await deleteShift(editingSchedule.id);
                    setShowEditModal(false);
                  }
                }}
                className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600"
              >
                Löschen
              </button>
              
              <div className="flex gap-3">
                <button
                  onClick={() => setShowEditModal(false)}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  Abbrechen
                </button>
                <button
                  onClick={saveEditedShift}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
                >
                  Speichern
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ScheduleTab;