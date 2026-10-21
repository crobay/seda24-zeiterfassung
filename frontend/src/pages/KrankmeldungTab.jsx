import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Check, X, Clock, Image, Plus, AlertCircle, Edit2, Ban, Trash2 } from 'lucide-react';

const KrankmeldungTab = ({ employees = [] }) => {
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingNote, setEditingNote] = useState(null);
  const [showPhotoModal, setShowPhotoModal] = useState(false);
  const [selectedPhoto, setSelectedPhoto] = useState(null);
  const [toast, setToast] = useState(null);
  const [createForm, setCreateForm] = useState({
    employee_id: '',
    start_date: new Date().toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    notes: '',
  });

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    loadNotes();
  }, [filterStatus]);

  const loadNotes = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/sick-notes${filterStatus ? `?status=${filterStatus}` : ''}`);
      setNotes(res.data);
    } catch (error) {
      console.error('Fehler:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = async (noteId, status) => {
    const labels = {
      confirmed: 'best\u00E4tigen (mit Lohnfortzahlung)',
      rejected: 'ablehnen',
      cancelled: 'stornieren (Buchungen werden r\u00FCckg\u00E4ngig gemacht)',
    };
    if (!window.confirm(`Krankmeldung wirklich ${labels[status]}?`)) return;
    try {
      await api.put(`/admin/sick-notes/${noteId}`, { status });
      const statusLabels = { confirmed: 'best\u00E4tigt', rejected: 'abgelehnt', cancelled: 'storniert' };
      showToast(`Krankmeldung ${statusLabels[status]}`, 'success');
      loadNotes();
    } catch (error) {
      showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
    }
  };

  const handleDelete = async (noteId) => {
    if (!window.confirm('Krankmeldung wirklich l\u00F6schen? Best\u00E4tigte Buchungen werden r\u00FCckg\u00E4ngig gemacht.')) return;
    try {
      await api.delete(`/admin/sick-notes/${noteId}`);
      showToast('Krankmeldung gel\u00F6scht', 'success');
      loadNotes();
    } catch (error) {
      showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
    }
  };

  const handleCreate = async () => {
    if (!createForm.employee_id || !createForm.start_date || !createForm.end_date) {
      showToast('Bitte alle Felder ausf\u00FCllen', 'error');
      return;
    }
    try {
      const res = await api.post('/admin/sick-notes', createForm);
      showToast(`Krankmeldung erstellt (${res.data.working_days} Tage)`, 'success');
      setShowCreateModal(false);
      loadNotes();
    } catch (error) {
      showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
    }
  };

  const openEditModal = (note) => {
    setEditingNote({
      id: note.id,
      employee_name: note.employee_name,
      start_date: note.start_date,
      end_date: note.end_date,
      notes: note.notes || '',
      status: note.status,
      working_days: note.working_days,
    });
    setShowEditModal(true);
  };

  const handleEditSave = async () => {
    if (!editingNote) return;
    try {
      const payload = {
        start_date: editingNote.start_date,
        end_date: editingNote.end_date,
        notes: editingNote.notes,
      };
      const res = await api.put(`/admin/sick-notes/${editingNote.id}`, payload);
      showToast(`Krankmeldung aktualisiert (${res.data.working_days} Tage)`, 'success');
      setShowEditModal(false);
      setEditingNote(null);
      loadNotes();
    } catch (error) {
      showToast('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'), 'error');
    }
  };

  const viewPhoto = async (noteId) => {
    try {
      const res = await api.get(`/admin/sick-notes/${noteId}/photo`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      setSelectedPhoto(url);
      setShowPhotoModal(true);
    } catch (error) {
      showToast('Foto konnte nicht geladen werden', 'error');
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending':
        return { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Offen' };
      case 'confirmed':
        return { bg: 'bg-green-100', text: 'text-green-800', label: 'Best\u00E4tigt' };
      case 'rejected':
        return { bg: 'bg-red-100', text: 'text-red-800', label: 'Abgelehnt' };
      case 'cancelled':
        return { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Storniert' };
      default:
        return { bg: 'bg-gray-100', text: 'text-gray-800', label: status };
    }
  };

  const pendingCount = notes.filter(n => n.status === 'pending').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Krankmeldungen</h2>
          {pendingCount > 0 && (
            <p className="text-orange-600 font-medium">{pendingCount} offene Meldungen</p>
          )}
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
        >
          <Plus size={20} />
          Neue Krankmeldung
        </button>
      </div>

      {/* Filter */}
      <div className="flex gap-2 flex-wrap">
        {[
          { value: '', label: 'Alle' },
          { value: 'pending', label: 'Offen' },
          { value: 'confirmed', label: 'Best\u00E4tigt' },
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

      {/* Tabelle */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Lade...</div>
        ) : notes.length === 0 ? (
          <div className="p-8 text-center text-gray-500">Keine Krankmeldungen</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Mitarbeiter</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Zeitraum</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">Tage</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">AU-Foto</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Notizen</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Gemeldet</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">Aktion</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {notes.map((note) => {
                  const badge = getStatusBadge(note.status);
                  return (
                    <tr key={note.id} className={`hover:bg-gray-50 ${note.status === 'pending' ? 'bg-yellow-50/50' : ''} ${note.status === 'cancelled' ? 'opacity-60' : ''}`}>
                      <td className="px-4 py-3">
                        <div className="text-sm font-medium">{note.employee_name}</div>
                        <div className="text-xs text-gray-500">{note.personal_nr}</div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {formatDate(note.start_date)} - {formatDate(note.end_date)}
                      </td>
                      <td className="px-4 py-3 text-center text-sm font-medium">{note.working_days}</td>
                      <td className="px-4 py-3 text-center">
                        {note.has_au_photo ? (
                          <button
                            onClick={() => viewPhoto(note.id)}
                            className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200"
                          >
                            <Image size={14} />
                            Ansehen
                          </button>
                        ) : (
                          <span className="text-xs text-gray-400">Kein Foto</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${badge.bg} ${badge.text}`}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-600 max-w-[150px] truncate" title={note.notes || ''}>
                        {note.notes || '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {formatDate(note.created_at)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex gap-1 justify-center flex-wrap">
                          {note.status === 'pending' && (
                            <>
                              <button
                                onClick={() => handleDecision(note.id, 'confirmed')}
                                className="p-1.5 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition-colors"
                                title="Best\u00E4tigen (mit Lohnfortzahlung)"
                              >
                                <Check size={16} />
                              </button>
                              <button
                                onClick={() => handleDecision(note.id, 'rejected')}
                                className="p-1.5 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors"
                                title="Ablehnen"
                              >
                                <X size={16} />
                              </button>
                            </>
                          )}
                          {(note.status === 'pending' || note.status === 'confirmed') && (
                            <button
                              onClick={() => openEditModal(note)}
                              className="p-1.5 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition-colors"
                              title="Bearbeiten"
                            >
                              <Edit2 size={16} />
                            </button>
                          )}
                          {note.status === 'confirmed' && (
                            <button
                              onClick={() => handleDecision(note.id, 'cancelled')}
                              className="p-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
                              title="Stornieren"
                            >
                              <Ban size={16} />
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(note.id)}
                            className="p-1.5 bg-red-50 text-red-400 rounded-lg hover:bg-red-100 hover:text-red-600 transition-colors"
                            title="Löschen"
                          >
                            <Trash2 size={16} />
                          </button>
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

      {/* Erstellen-Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-bold mb-4">Neue Krankmeldung</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Mitarbeiter</label>
                <select
                  value={createForm.employee_id}
                  onChange={(e) => setCreateForm({ ...createForm, employee_id: e.target.value })}
                  className="w-full p-2 border rounded-lg"
                >
                  <option value="">-- Ausw{'\u00E4'}hlen --</option>
                  {employees.map(emp => (
                    <option key={emp.id} value={emp.id}>{emp.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Von</label>
                  <input
                    type="date"
                    value={createForm.start_date}
                    onChange={(e) => setCreateForm({ ...createForm, start_date: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                  <input
                    type="date"
                    value={createForm.end_date}
                    onChange={(e) => setCreateForm({ ...createForm, end_date: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notizen</label>
                <textarea
                  value={createForm.notes}
                  onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
                  className="w-full p-2 border rounded-lg"
                  rows={2}
                  placeholder="Optional..."
                />
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
                <AlertCircle size={16} className="inline mr-1" />
                Bei Best{'\u00E4'}tigung werden automatisch Lohnfortzahlungs-Buchungen erstellt.
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                className="flex-1 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
              <button
                onClick={handleCreate}
                className="flex-1 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Erstellen + Best{'\u00E4'}tigen
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit-Modal */}
      {showEditModal && editingNote && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-bold mb-4">Krankmeldung bearbeiten</h3>
            <div className="mb-3 text-sm text-gray-600">
              <span className="font-medium">{editingNote.employee_name}</span>
              <span className={`ml-2 inline-block px-2 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(editingNote.status).bg} ${getStatusBadge(editingNote.status).text}`}>
                {getStatusBadge(editingNote.status).label}
              </span>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Von</label>
                  <input
                    type="date"
                    value={editingNote.start_date}
                    onChange={(e) => setEditingNote({ ...editingNote, start_date: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                  <input
                    type="date"
                    value={editingNote.end_date}
                    onChange={(e) => setEditingNote({ ...editingNote, end_date: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notizen</label>
                <textarea
                  value={editingNote.notes}
                  onChange={(e) => setEditingNote({ ...editingNote, notes: e.target.value })}
                  className="w-full p-2 border rounded-lg"
                  rows={2}
                  placeholder="Optional..."
                />
              </div>
              {editingNote.status === 'confirmed' && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-700">
                  <AlertCircle size={16} className="inline mr-1" />
                  Bei Datums{'\u00E4'}nderung werden bestehende Krank-Buchungen angepasst.
                </div>
              )}
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => { setShowEditModal(false); setEditingNote(null); }}
                className="flex-1 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
              <button
                onClick={handleEditSave}
                className="flex-1 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Photo Modal */}
      {showPhotoModal && selectedPhoto && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50" onClick={() => { setShowPhotoModal(false); URL.revokeObjectURL(selectedPhoto); }}>
          <div className="max-w-2xl max-h-[80vh] p-2" onClick={(e) => e.stopPropagation()}>
            <img src={selectedPhoto} alt="AU-Foto" className="max-w-full max-h-[75vh] rounded-lg shadow-2xl" />
            <button
              onClick={() => { setShowPhotoModal(false); URL.revokeObjectURL(selectedPhoto); }}
              className="mt-3 w-full py-2 bg-white text-gray-700 rounded-lg font-medium"
            >
              Schlie{'\u00DF'}en
            </button>
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
          {toast.message}
        </div>
      )}
    </div>
  );
};

export default KrankmeldungTab;
