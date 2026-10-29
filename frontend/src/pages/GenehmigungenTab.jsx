import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Clock, User, Building, Calendar, Car, Edit2, ChevronDown, ChevronUp } from 'lucide-react';
import api from '../services/api';

const GenehmigungenTab = ({ showToast }) => {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('offen');
  const [expandedId, setExpandedId] = useState(null);

  // Bearbeitbare Felder pro Buchung
  const [editData, setEditData] = useState({});

  useEffect(() => {
    loadBookings();
  }, [statusFilter]);

  const loadBookings = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/pending-bookings?status_filter=${statusFilter}`);
      setBookings(res.data);
      // Edit-Daten initialisieren
      const ed = {};
      res.data.forEach(b => {
        ed[b.id] = {
          approved_hours: b.requested_hours,
          hourly_rate: b.suggested_rate || 15.0,
          start_time: b.start_time,
          end_time: b.end_time,
          service_type: b.service_type,
          admin_notes: '',
          override_km: null, // null = auto, wird nur gesendet wenn Admin ändert
          km_display: b.is_driver && b.km_distance ? b.km_distance : '',
        };
      });
      setEditData(ed);
    } catch (e) {
      console.error('Fehler:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (id, force = false) => {
    const data = editData[id];
    if (!data) return;
    try {
      const payload = { ...data };
      // override_km nur senden wenn Admin den Wert geändert hat
      if (payload.override_km !== null) {
        payload.override_km = parseFloat(payload.override_km) || 0;
      }
      delete payload.km_display;
      if (force) payload.force = true;
      const res = await api.post(`/admin/pending-bookings/${id}/approve`, payload);
      showToast(`Eingetragen: ${res.data.hours}h, ${res.data.brutto} EUR${res.data.km_booked ? ` + ${res.data.km_booked} km` : ''}`, 'success');
      loadBookings();
    } catch (e) {
      if (e.response?.status === 409) {
        if (window.confirm(e.response.data.detail)) {
          handleApprove(id, true);
        }
      } else {
        showToast(e.response?.data?.detail || 'Fehler', 'error');
      }
    }
  };

  const handleReject = async (id) => {
    const data = editData[id];
    try {
      await api.post(`/admin/pending-bookings/${id}/reject`, { admin_notes: data?.admin_notes || '' });
      showToast('Rückfrage gestellt', 'info');
      loadBookings();
    } catch (e) {
      showToast(e.response?.data?.detail || 'Fehler', 'error');
    }
  };

  const handleClose = async (id) => {
    if (!window.confirm(
      'Diesen Antrag STILL erledigen?\n\nDer Mitarbeiter wird NICHT benachrichtigt (kein Telegram, keine Mail).\n' +
      'Der Eintrag verschwindet aus der offenen Liste, bleibt aber in der Historie.'
    )) return;
    const data = editData[id];
    try {
      await api.post(`/admin/pending-bookings/${id}/close`, { admin_notes: data?.admin_notes || '' });
      showToast('Still erledigt (ohne Benachrichtigung)', 'info');
      loadBookings();
    } catch (e) {
      showToast(e.response?.data?.detail || 'Fehler', 'error');
    }
  };

  const updateEdit = (id, field, value) => {
    setEditData(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value }
    }));
  };

  // Stunden auto-berechnen wenn Zeiten geaendert werden
  const recalcHours = (id, startTime, endTime) => {
    if (!startTime || !endTime) return;
    const [sh, sm] = startTime.split(':').map(Number);
    const [eh, em] = endTime.split(':').map(Number);
    const diff = (eh * 60 + em) - (sh * 60 + sm);
    if (diff > 0) {
      updateEdit(id, 'approved_hours', (diff / 60).toFixed(2));
    }
  };

  const statusBadge = (status) => {
    const styles = {
      'offen': 'bg-yellow-100 text-yellow-800',
      'genehmigt': 'bg-green-100 text-green-800',
      'abgelehnt': 'bg-orange-100 text-orange-800',
      'erledigt': 'bg-gray-100 text-gray-600',
    };
    const labels = {
      'offen': 'Offen',
      'genehmigt': 'Eingetragen',
      'abgelehnt': 'Rückfrage',
      'erledigt': 'Erledigt',
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-bold inline-flex items-center gap-1 ${styles[status] || ''}`}>
        {status === 'offen' && <Clock size={16} />}
        {status === 'genehmigt' && <CheckCircle size={16} />}
        {status === 'abgelehnt' && <XCircle size={16} />}
        {status === 'erledigt' && <Clock size={16} />}
        {labels[status] || status}
      </span>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Genehmigungen</h2>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border rounded-lg text-sm"
        >
          <option value="offen">Offen</option>
          <option value="genehmigt">Eingetragen</option>
          <option value="abgelehnt">Rückfrage</option>
          <option value="erledigt">Erledigt</option>
          <option value="alle">Alle</option>
        </select>
      </div>

      {loading ? (
        <div className="text-center py-8 text-gray-500">Lade...</div>
      ) : bookings.length === 0 ? (
        <div className="text-center py-12">
          <CheckCircle size={48} className="mx-auto text-green-300 mb-3" />
          <p className="text-gray-500">Keine {statusFilter === 'offen' ? 'offenen' : ''} Nachträge</p>
        </div>
      ) : (
        <div className="space-y-3">
          {bookings.map(b => {
            const ed = editData[b.id] || {};
            const isExpanded = expandedId === b.id;
            const kmAmount = b.km_distance ? (b.km_distance * 0.30).toFixed(2) : null;
            const brutto = ((ed.approved_hours || b.requested_hours) * (ed.hourly_rate || 15)).toFixed(2);
            const isMehrzeit = b.reason === 'mehrzeit_dienstplan';
            const shiftDur = (() => {
              const [sh, sm] = (b.start_time || '0:0').split(':').map(Number);
              const [eh, em] = (b.end_time || '0:0').split(':').map(Number);
              const d = (eh * 60 + em) - (sh * 60 + sm);
              return d > 0 ? d / 60 : 0;
            })();
            const projectedTotal = (b.related_billed_hours || 0) + (parseFloat(ed.approved_hours ?? b.requested_hours) || 0);

            return (
              <div key={b.id} className="bg-white border rounded-xl shadow-sm overflow-hidden">
                {/* Header - immer sichtbar */}
                <div
                  className="p-3 cursor-pointer hover:bg-gray-50"
                  onClick={() => setExpandedId(isExpanded ? null : b.id)}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm">{b.employee_name}</span>
                      <span className="text-xs text-gray-400">{b.personal_nr}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {statusBadge(b.status)}
                      {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-600">
                    <span className="flex items-center gap-1"><Building size={12} /> {b.object_name}</span>
                    <span className="flex items-center gap-1"><Calendar size={12} /> {new Date(b.date).toLocaleDateString('de-DE')}</span>
                    <span>{b.start_time}-{b.end_time}</span>
                    <span className="font-bold text-blue-600">{isMehrzeit ? `+${b.requested_hours}h Mehrzeit` : `${b.requested_hours}h`}</span>
                    {b.is_driver && b.km_distance && (
                      <span className="flex items-center gap-1 text-green-600"><Car size={12} /> {b.km_distance}km</span>
                    )}
                  </div>
                  {b.service_type !== 'Unterhaltsreinigung' && (
                    <span className="inline-block mt-1 px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">{b.service_type}</span>
                  )}
                  {b.catch_up_type === 'zeit_korrektur' && (
                    <span className="inline-block mt-1 px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-bold">
                      Korrektur ({b.correction_field === 'kommen' ? 'Kommen' : b.correction_field === 'gehen' ? 'Gehen' : 'Beides'})
                    </span>
                  )}
                  {b.reason && (
                    <span className={`inline-block mt-1 ml-1 px-2 py-0.5 rounded text-xs font-medium ${
                      b.reason === 'technisch' ? 'bg-blue-100 text-blue-700' :
                      b.reason === 'vergessen' ? 'bg-gray-100 text-gray-600' :
                      'bg-purple-100 text-purple-600'
                    }`}>
                      {b.reason === 'technisch' ? 'Technisch' : b.reason === 'vergessen' ? 'Vergessen' : 'Sonstiges'}
                    </span>
                  )}
                </div>

                {/* Expanded: Bearbeitungsbereich */}
                {isExpanded && b.status === 'offen' && (
                  <div className="border-t px-3 pb-3 pt-2 bg-gray-50 space-y-3">
                    {/* Alt/Neu-Vergleich bei Korrekturen */}
                    {b.catch_up_type === 'zeit_korrektur' && b.original_start_time && (
                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                        <div className="text-xs font-bold text-amber-800 mb-2">Zeitkorrektur-Vergleich</div>
                        <div className="flex items-center gap-3 text-sm">
                          <div>
                            <span className="text-xs text-gray-500">Alt:</span>
                            <div className="line-through text-red-600 font-mono">{b.original_start_time}–{b.original_end_time}</div>
                          </div>
                          <span className="text-gray-400">→</span>
                          <div>
                            <span className="text-xs text-gray-500">Neu:</span>
                            <div className="font-bold text-green-700 font-mono">{b.start_time}–{b.end_time}</div>
                          </div>
                          {(() => {
                            const [oh, om] = (b.original_start_time || '00:00').split(':').map(Number);
                            const [oeh, oem] = (b.original_end_time || '00:00').split(':').map(Number);
                            const [nh, nm] = (b.start_time || '00:00').split(':').map(Number);
                            const [neh, nem] = (b.end_time || '00:00').split(':').map(Number);
                            const oldMin = (oeh * 60 + oem) - (oh * 60 + om);
                            const newMin = (neh * 60 + nem) - (nh * 60 + nm);
                            const diff = newMin - oldMin;
                            return (
                              <div className="ml-auto text-right">
                                <span className="text-xs text-gray-500">Differenz:</span>
                                <div className={`font-bold text-sm ${diff > 0 ? 'text-green-700' : diff < 0 ? 'text-red-600' : 'text-gray-600'}`}>
                                  {diff > 0 ? '+' : ''}{diff} Min
                                </div>
                              </div>
                            );
                          })()}
                        </div>
                      </div>
                    )}

                    {/* Mehrzeit-Infokarte: gestempelt vs. Plan + beantragte Mehrzeit + Vorschau */}
                    {isMehrzeit && (
                      <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 space-y-2">
                        <div className="text-xs font-bold text-orange-800">Mehrzeit-Antrag</div>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <div>
                            <div className="text-xs text-gray-500">Gestempelt (tatsächlich)</div>
                            <div className="font-mono font-bold text-gray-900">
                              {(b.related_check_in || '?')}–{(b.related_check_out || '?')}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-gray-500">Plan (Dienstplan)</div>
                            <div className="font-mono text-gray-600">{b.start_time}–{b.end_time}</div>
                          </div>
                        </div>
                        <div className="text-sm">
                          <span className="text-xs text-gray-500">Beantragte Mehrzeit: </span>
                          <span className="font-bold text-orange-700">
                            {Math.round((parseFloat(ed.approved_hours ?? b.requested_hours) || 0) * 60)} Minuten
                          </span>
                          <span className="text-xs text-gray-400 ml-1">
                            ({(parseFloat(ed.approved_hours ?? b.requested_hours) || 0).toFixed(4)} h)
                          </span>
                        </div>
                        {b.notes && (
                          <div className="text-sm">
                            <span className="text-xs text-gray-500">Begründung: </span>
                            <span className="text-gray-800 italic">{b.notes}</span>
                          </div>
                        )}
                        {(() => {
                          const rate = parseFloat(ed.hourly_rate ?? b.hourly_rate ?? 0) || 0;
                          const vor = (b.related_billed_hours || 0);
                          const nach = projectedTotal;
                          return (
                            <div className="border-t border-orange-200 pt-2 text-sm">
                              <div className="text-xs text-gray-500 mb-0.5">Nach dem Eintragen gilt:</div>
                              <div className="flex justify-between">
                                <span>Stunden:</span>
                                <span className="font-bold">{vor.toFixed(4)} h → <span className="text-green-700">{nach.toFixed(4)} h</span></span>
                              </div>
                              <div className="flex justify-between">
                                <span>Brutto:</span>
                                <span className="font-bold">{(vor * rate).toFixed(2)} € → <span className="text-green-700">{(nach * rate).toFixed(2)} €</span></span>
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    )}

                    {/* Zeiten anpassen */}
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="text-xs text-gray-500">Von</label>
                        <input
                          type="time"
                          value={ed.start_time || b.start_time}
                          onChange={(e) => {
                            updateEdit(b.id, 'start_time', e.target.value);
                            if (!isMehrzeit) recalcHours(b.id, e.target.value, ed.end_time || b.end_time);
                          }}
                          className="w-full p-1.5 border rounded text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">Bis</label>
                        <input
                          type="time"
                          value={ed.end_time || b.end_time}
                          onChange={(e) => {
                            updateEdit(b.id, 'end_time', e.target.value);
                            if (!isMehrzeit) recalcHours(b.id, ed.start_time || b.start_time, e.target.value);
                          }}
                          className="w-full p-1.5 border rounded text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">{isMehrzeit ? 'Mehrzeit (Std.)' : 'Stunden'}</label>
                        <input
                          type="number"
                          step="0.25"
                          value={ed.approved_hours}
                          onChange={(e) => updateEdit(b.id, 'approved_hours', e.target.value)}
                          className="w-full p-1.5 border rounded text-sm"
                        />
                      </div>
                    </div>

                    {/* Satz + Art */}
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-xs text-gray-500">Stundensatz</label>
                        <input
                          type="number"
                          step="0.50"
                          value={ed.hourly_rate}
                          onChange={(e) => updateEdit(b.id, 'hourly_rate', e.target.value)}
                          className="w-full p-1.5 border rounded text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">Reinigungsart</label>
                        <select
                          value={ed.service_type || b.service_type}
                          onChange={(e) => {
                            updateEdit(b.id, 'service_type', e.target.value);
                            // Satz auto-anpassen
                            if (e.target.value === 'Fensterreinigung') {
                              updateEdit(b.id, 'hourly_rate', 20.0);
                            } else if (e.target.value === 'Sonderreinigung') {
                              updateEdit(b.id, 'hourly_rate', 20.0);
                            } else {
                              updateEdit(b.id, 'hourly_rate', b.suggested_rate || 15.0);
                            }
                          }}
                          className="w-full p-1.5 border rounded text-sm"
                        >
                          <option value="Unterhaltsreinigung">Unterhaltsreinigung</option>
                          <option value="Fensterreinigung">Fensterreinigung</option>
                          <option value="Sonderreinigung">Sonderreinigung</option>
                        </select>
                      </div>
                    </div>

                    {/* KM anpassen - nur wenn Fahrer */}
                    {b.is_driver && b.km_distance > 0 && (
                      <div>
                        <label className="text-xs text-gray-500">KM (Auto: {b.km_distance} km)</label>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            step="0.1"
                            value={ed.override_km !== null ? ed.override_km : b.km_distance}
                            onChange={(e) => updateEdit(b.id, 'override_km', e.target.value)}
                            className="flex-1 p-1.5 border rounded text-sm"
                          />
                          <span className="text-xs text-gray-400">km</span>
                          {ed.override_km !== null && (
                            <button
                              onClick={() => updateEdit(b.id, 'override_km', null)}
                              className="text-xs text-blue-500 hover:underline whitespace-nowrap"
                            >Auto</button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Brutto + KM Vorschau */}
                    <div className="bg-blue-50 rounded-lg p-2 text-sm">
                      <div className="flex justify-between">
                        <span>{isMehrzeit ? 'Mehrzeit-Betrag (nur Zuschlag):' : 'Brutto:'}</span>
                        <span className="font-bold text-blue-700">{brutto} EUR</span>
                      </div>
                      {b.is_driver && b.km_distance > 0 && (() => {
                        const kmVal = ed.override_km !== null ? parseFloat(ed.override_km) || 0 : b.km_distance;
                        const kmEur = (kmVal * 0.30).toFixed(2);
                        return kmVal > 0 ? (
                          <div className="flex justify-between text-green-700">
                            <span>KM ({kmVal} km):</span>
                            <span className="font-bold">{kmEur} EUR</span>
                          </div>
                        ) : (
                          <div className="flex justify-between text-gray-400 line-through">
                            <span>KM storniert</span>
                            <span>0.00 EUR</span>
                          </div>
                        );
                      })()}
                    </div>

                    {/* Admin-Notiz */}
                    <input
                      type="text"
                      placeholder="Grund für Ablehnung (empfohlen)"
                      value={ed.admin_notes || ''}
                      onChange={(e) => updateEdit(b.id, 'admin_notes', e.target.value)}
                      className="w-full p-1.5 rounded text-sm"
                      style={{ border: !ed.admin_notes ? '2px solid #f97316' : '1px solid #e5e7eb' }}
                    />

                    {/* Buttons */}
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleReject(b.id)}
                        className="flex-1 px-3 py-2 bg-red-100 text-red-700 rounded-lg text-sm font-bold hover:bg-red-200 flex items-center justify-center gap-1"
                      >
                        <XCircle size={16} /> Rückfrage stellen
                      </button>
                      <button
                        onClick={() => handleApprove(b.id)}
                        className="flex-2 px-3 py-2 bg-green-500 text-white rounded-lg text-sm font-bold hover:bg-green-600 flex items-center justify-center gap-1"
                        style={{ flex: 2 }}
                      >
                        <CheckCircle size={16} /> Eintragen
                      </button>
                    </div>

                    {/* Dritter, unauffaelliger Weg: still erledigen ohne Benachrichtigung */}
                    <button
                      onClick={() => handleClose(b.id)}
                      className="w-full px-3 py-1.5 text-xs text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg flex items-center justify-center gap-1"
                    >
                      <Clock size={14} /> Still erledigen (ohne Benachrichtigung)
                    </button>
                  </div>
                )}

                {/* Expanded: Bereits bearbeitet */}
                {isExpanded && b.status !== 'offen' && (
                  <div className="border-t px-3 pb-3 pt-2 bg-gray-50 text-sm text-gray-600">
                    {b.approved_hours && <p>Genehmigte Stunden: <strong>{b.approved_hours}h</strong></p>}
                    {b.hourly_rate && <p>Stundensatz: <strong>{b.hourly_rate} EUR</strong></p>}
                    {b.admin_notes && <p>Notiz: {b.admin_notes}</p>}
                    {b.approved_at && <p>Bearbeitet: {new Date(b.approved_at).toLocaleString('de-DE')}</p>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default GenehmigungenTab;
