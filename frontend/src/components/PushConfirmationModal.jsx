import React, { useState } from 'react';
import { CheckCircle, XCircle, Edit3, X, Users, Clock, Building } from 'lucide-react';
import { respondToNotification } from '../services/pushService';

const PushConfirmationModal = ({ notification, employees, onClose, onResponded, onConfirmDirect }) => {
  const [showReasonInput, setShowReasonInput] = useState(false);
  const [absenceType, setAbsenceType] = useState('privat');
  const [reason, setReason] = useState('');
  const [showCorrectionOptions, setShowCorrectionOptions] = useState(false);
  const [correctionType, setCorrectionType] = useState('');
  const [colleagueId, setColleagueId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const data = notification.data || {};

  const handleConfirm = async () => {
    setLoading(true);
    setError('');
    try {
      if (notification.id) {
        // Push vorhanden -> ueber Push-API antworten
        const result = await respondToNotification(notification.id, 'confirmed');
        onResponded(result);
      } else if (onConfirmDirect) {
        // Kein Push -> direkt buchen
        await onConfirmDirect(notification._shift_object_id, notification.id);
      }
    } catch (e) {
      setError('Fehler beim Bestaetigen');
    }
    setLoading(false);
  };

  const handleNotPresent = async () => {
    if (!showReasonInput) {
      setShowReasonInput(true);
      setShowCorrectionOptions(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await respondToNotification(notification.id, 'not_present', {
        absence_type: absenceType,
        reason: reason,
      });
      onResponded(result);
    } catch (e) {
      setError('Fehler beim Senden');
    }
    setLoading(false);
  };

  const handleCorrection = async () => {
    if (!showCorrectionOptions) {
      setShowCorrectionOptions(true);
      setShowReasonInput(false);
      return;
    }

    if (correctionType === 'with_colleague' && !colleagueId) {
      setError('Bitte Kollegen auswaehlen');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const correctionData = { type: correctionType };
      if (correctionType === 'with_colleague') {
        correctionData.colleague_id = parseInt(colleagueId);
      }
      const result = await respondToNotification(notification.id, 'correction', correctionData);
      onResponded(result);
    } catch (e) {
      setError('Fehler beim Senden');
    }
    setLoading(false);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="bg-blue-500 text-white p-4 rounded-t-xl flex justify-between items-center">
          <h3 className="text-lg font-bold">Schicht-Bestaetigung</h3>
          <button onClick={onClose} className="text-white hover:text-gray-200">
            <X size={24} />
          </button>
        </div>

        {/* Schicht-Details */}
        <div className="p-4 border-b">
          <div className="flex items-center gap-2 mb-2">
            <Building size={18} className="text-gray-500" />
            <span className="font-semibold">{data.object_name || 'Objekt'}</span>
          </div>
          <div className="flex items-center gap-2 mb-2">
            <Clock size={18} className="text-gray-500" />
            <span>{data.start_time} - {data.end_time}</span>
          </div>
          <div className="text-sm text-gray-600">
            {data.date} | {data.planned_hours}h geplant
          </div>
        </div>

        {/* Aktions-Buttons */}
        <div className="p-4 space-y-3">
          {error && (
            <div className="bg-red-50 text-red-700 p-2 rounded text-sm">{error}</div>
          )}

          {/* Bestaetigen */}
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="w-full bg-green-500 hover:bg-green-600 text-white py-3 px-4 rounded-lg flex items-center justify-center gap-2 font-semibold disabled:opacity-50"
          >
            <CheckCircle size={20} />
            Ja, war anwesend
          </button>

          {/* Nicht anwesend */}
          <button
            onClick={handleNotPresent}
            disabled={loading}
            className="w-full bg-red-500 hover:bg-red-600 text-white py-3 px-4 rounded-lg flex items-center justify-center gap-2 font-semibold disabled:opacity-50"
          >
            <XCircle size={20} />
            War nicht da
          </button>

          {showReasonInput && (
            <div className="bg-red-50 p-3 rounded-lg space-y-2">
              <label className="block text-sm font-medium text-gray-700">Grund:</label>
              <select
                value={absenceType}
                onChange={(e) => setAbsenceType(e.target.value)}
                className="w-full border rounded p-2"
              >
                <option value="krank">Krank</option>
                <option value="privat">Privat</option>
                <option value="anderes">Anderes</option>
              </select>
              {absenceType === 'anderes' && (
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Bitte Grund eingeben..."
                  className="w-full border rounded p-2"
                  rows={2}
                />
              )}
              <button
                onClick={handleNotPresent}
                disabled={loading}
                className="w-full bg-red-600 text-white py-2 rounded font-medium disabled:opacity-50"
              >
                {loading ? 'Wird gesendet...' : 'Absenden'}
              </button>
            </div>
          )}

          {/* Korrektur */}
          <button
            onClick={handleCorrection}
            disabled={loading}
            className="w-full bg-orange-500 hover:bg-orange-600 text-white py-3 px-4 rounded-lg flex items-center justify-center gap-2 font-semibold disabled:opacity-50"
          >
            <Edit3 size={20} />
            Korrektur
          </button>

          {showCorrectionOptions && (
            <div className="bg-orange-50 p-3 rounded-lg space-y-2">
              <label className="block text-sm font-medium text-gray-700">Art der Korrektur:</label>
              <select
                value={correctionType}
                onChange={(e) => setCorrectionType(e.target.value)}
                className="w-full border rounded p-2"
              >
                <option value="">Bitte waehlen...</option>
                <option value="with_colleague">War mit Kollege</option>
                <option value="different_object_time">Anderes Objekt / andere Zeit</option>
              </select>

              {correctionType === 'with_colleague' && employees && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mt-2">Kollege:</label>
                  <select
                    value={colleagueId}
                    onChange={(e) => setColleagueId(e.target.value)}
                    className="w-full border rounded p-2"
                  >
                    <option value="">Bitte waehlen...</option>
                    {employees.map(emp => (
                      <option key={emp.id} value={emp.id}>
                        {emp.name || `${emp.first_name} ${emp.last_name}`}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <button
                onClick={handleCorrection}
                disabled={loading || !correctionType}
                className="w-full bg-orange-600 text-white py-2 rounded font-medium disabled:opacity-50"
              >
                {loading ? 'Wird gesendet...' : 'Korrektur einreichen'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PushConfirmationModal;
