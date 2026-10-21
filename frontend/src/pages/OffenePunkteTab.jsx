import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { AlertCircle, CheckCircle, XCircle, Clock, User, Bell, RefreshCw, Smartphone, WifiOff, Zap, ChevronDown, ChevronUp, MessageSquare, BookOpen, Ban, FileText, Send } from 'lucide-react';

const OffenePunkteTab = () => {
  const [openItems, setOpenItems] = useState([]);
  const [pendingConfirmations, setPendingConfirmations] = useState([]);
  const [resolvedItems, setResolvedItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState('');
  const [showResolved, setShowResolved] = useState(false);
  const [noteModal, setNoteModal] = useState(null); // {type, id, note}

  const currentYear = new Date().getFullYear();
  const currentMonth = new Date().getMonth() + 1;

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [itemsRes, confRes, resolvedRes] = await Promise.all([
        api.get('/admin/open-items').catch(() => ({ data: [] })),
        api.get(`/confirmations/admin/pending-confirmations?year=${currentYear}&month=${currentMonth}`).catch(() => ({ data: { confirmations: [] } })),
        api.get('/admin/open-items/resolved').catch(() => ({ data: [] })),
      ]);
      setOpenItems(itemsRes.data || []);
      setPendingConfirmations(confRes.data?.confirmations || []);
      setResolvedItems(resolvedRes.data || []);
    } catch (error) {
      console.error('Fehler:', error);
    }
    setLoading(false);
  };

  const showMessage = (msg) => {
    setActionMessage(msg);
    setTimeout(() => setActionMessage(''), 3000);
  };

  const resolveItem = async (itemType, itemId, action, note = '') => {
    try {
      await api.put(`/admin/open-items/${itemType}/${itemId}/resolve`, { action, note });
      showMessage('Erledigt');
      loadData();
    } catch (error) {
      showMessage('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'));
    }
  };

  const triggerMonthlyConfirmations = async () => {
    try {
      const res = await api.post(`/confirmations/admin/trigger-confirmations/${currentYear}/${currentMonth}`);
      showMessage(`Push an ${res.data.sent_count} Mitarbeiter gesendet`);
      loadData();
    } catch (error) {
      showMessage('Fehler beim Ausloesen');
    }
  };

  const resendMonthlyConfirmation = async (employeeId, year, month) => {
    try {
      const res = await api.post(`/admin/resend-monthly-confirmation/${employeeId}`, { year, month });
      showMessage(`Neue Bestaetigung gesendet (${res.data.shifts} Schichten, ${res.data.hours?.toFixed(1)}h)`);
      loadData();
    } catch (error) {
      showMessage('Fehler: ' + (error.response?.data?.detail || 'Unbekannt'));
    }
  };

  const ActionButtons = ({ itemType, itemId, actions }) => (
    <div className="flex flex-wrap gap-2 mt-2">
      {actions.map(({ label, action, color, icon: Icon }) => (
        <button
          key={action}
          onClick={() => resolveItem(itemType, itemId, action)}
          className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${color}`}
        >
          {Icon && <Icon size={14} />}
          {label}
        </button>
      ))}
      <button
        onClick={() => setNoteModal({ type: itemType, id: itemId, note: '' })}
        className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 text-gray-700 hover:bg-gray-200"
      >
        <MessageSquare size={14} />
        Notiz
      </button>
    </div>
  );

  const ACTION_MAP = {
    noted: 'Zur Kenntnis',
    booked: 'Gebucht',
    rejected: 'Abgelehnt',
    not_book: 'Nicht gebucht',
    resolved: 'Erledigt',
    approved: 'Genehmigt',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const expiredPushes = openItems.filter(i => i.type === 'expired_push');
  const notPresent = openItems.filter(i => i.type === 'not_present');
  const corrections = openItems.filter(i => i.type === 'correction');
  const shiftChanges = openItems.filter(i => i.type === 'shift_change');
  const telegramNotConnected = openItems.filter(i => i.type === 'telegram_not_connected');
  const autoBooked = openItems.filter(i => i.type === 'auto_booked');
  const telegramCorrections = openItems.filter(i => i.type === 'telegram_correction');
  const monthDisputes = openItems.filter(i => i.type === 'month_dispute');

  const MONATSNAMEN = ['', 'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

  const pendingConfsOpen = pendingConfirmations.filter(c => c.status !== 'confirmed').length;
  const totalOpen = expiredPushes.length + notPresent.length + corrections.length +
    shiftChanges.length + pendingConfsOpen + telegramCorrections.length + monthDisputes.length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">
          Offene Punkte
          {totalOpen > 0 && (
            <span className="ml-2 bg-red-500 text-white text-sm px-2 py-1 rounded-full">
              {totalOpen}
            </span>
          )}
        </h2>
        <button onClick={loadData} className="text-gray-500 hover:text-blue-500">
          <RefreshCw size={20} />
        </button>
      </div>

      {actionMessage && (
        <div className="bg-blue-50 text-blue-700 p-3 rounded">{actionMessage}</div>
      )}

      {totalOpen === 0 && telegramNotConnected.length === 0 && autoBooked.length === 0 && (
        <div className="bg-green-50 text-green-700 p-6 rounded-lg text-center">
          <CheckCircle size={48} className="mx-auto mb-2 text-green-500" />
          <p className="font-semibold">Alles erledigt!</p>
          <p className="text-sm">Keine offenen Punkte.</p>
        </div>
      )}

      {/* Telegram nicht verbunden (Kat-B) */}
      {telegramNotConnected.length > 0 && (
        <div>
          <h3 className="font-bold text-orange-600 mb-2 flex items-center gap-2">
            <WifiOff size={18} />
            Nicht per Telegram verbunden ({telegramNotConnected.length})
          </h3>
          <div className="space-y-2">
            {telegramNotConnected.map(item => (
              <div key={`tg-${item.id}`} className="bg-white border border-orange-200 rounded-lg p-3">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <Smartphone size={16} className="text-orange-400" />
                    <span className="font-medium">{item.employee_name}</span>
                    <span className="text-xs text-gray-500">({item.personal_nr})</span>
                  </div>
                  <span className="text-xs bg-orange-100 text-orange-700 px-2 py-1 rounded">
                    Kat. B - kein Telegram
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Auto-gebucht (48h) */}
      {autoBooked.length > 0 && (
        <div>
          <h3 className="font-bold text-yellow-600 mb-2 flex items-center gap-2">
            <Zap size={18} />
            Auto-gebucht 48h ({autoBooked.length})
          </h3>
          <div className="space-y-2">
            {autoBooked.map(item => (
              <div key={`ab-${item.id}`} className="bg-white border border-yellow-200 rounded-lg p-3">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-semibold">{item.employee_name}</p>
                    <p className="text-sm text-gray-600">{item.details}</p>
                  </div>
                  <span className="text-xs text-gray-400">
                    {item.created_at ? new Date(item.created_at).toLocaleString('de-DE') : ''}
                  </span>
                </div>
                <ActionButtons itemType="auto_booked" itemId={item.id} actions={[
                  { label: 'Zur Kenntnis', action: 'noted', color: 'bg-green-100 text-green-700 hover:bg-green-200', icon: CheckCircle },
                ]} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Telegram-Korrekturen */}
      {telegramCorrections.length > 0 && (
        <div>
          <h3 className="font-bold text-purple-600 mb-2 flex items-center gap-2">
            <AlertCircle size={18} />
            Korrekturen aus Telegram ({telegramCorrections.length})
          </h3>
          <div className="space-y-2">
            {telegramCorrections.map(item => {
              let responseInfo = '';
              try {
                const data = JSON.parse(item.response_data || '{}');
                if (data.type === 'andere_zeiten') responseInfo = 'Andere Zeiten gewuenscht';
                else if (data.type === 'mit_kollege') responseInfo = 'Stunden mit Kollege teilen';
              } catch (e) {}
              return (
                <div key={`tc-${item.id}`} className="bg-white border border-purple-200 rounded-lg p-3">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-semibold">{item.employee_name}</p>
                      <p className="text-sm text-gray-600">{item.title}</p>
                      {responseInfo && (
                        <p className="text-sm text-purple-600 mt-1">{responseInfo}</p>
                      )}
                    </div>
                    <span className="text-xs text-gray-400">
                      {item.responded_at ? new Date(item.responded_at).toLocaleString('de-DE') : ''}
                    </span>
                  </div>
                  <ActionButtons itemType="telegram_correction" itemId={item.id} actions={[
                    { label: 'Zeiten uebernehmen', action: 'booked', color: 'bg-blue-100 text-blue-700 hover:bg-blue-200', icon: BookOpen },
                    { label: 'Zur Kenntnis', action: 'noted', color: 'bg-green-100 text-green-700 hover:bg-green-200', icon: CheckCircle },
                    { label: 'Nicht buchen', action: 'not_book', color: 'bg-red-100 text-red-700 hover:bg-red-200', icon: Ban },
                  ]} />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Abgelaufene Push-Notifications */}
      {expiredPushes.length > 0 && (
        <div>
          <h3 className="font-bold text-red-600 mb-2 flex items-center gap-2">
            <AlertCircle size={18} />
            Abgelaufene Bestaetigungen ({expiredPushes.length})
          </h3>
          <div className="space-y-2">
            {expiredPushes.map(push => (
              <div key={`ep-${push.id}`} className="bg-white border border-red-200 rounded-lg p-3">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-semibold">{push.employee_name}</p>
                    <p className="text-sm text-gray-500">{push.title}</p>
                    <p className="text-xs text-gray-400">
                      Erstellt: {push.created_at ? new Date(push.created_at).toLocaleString('de-DE') : '?'}
                    </p>
                  </div>
                </div>
                <ActionButtons itemType="expired_push" itemId={push.id} actions={[
                  { label: 'Zeiten buchen', action: 'booked', color: 'bg-blue-100 text-blue-700 hover:bg-blue-200', icon: BookOpen },
                  { label: 'Zur Kenntnis', action: 'noted', color: 'bg-green-100 text-green-700 hover:bg-green-200', icon: CheckCircle },
                  { label: 'Nicht buchen', action: 'not_book', color: 'bg-red-100 text-red-700 hover:bg-red-200', icon: Ban },
                ]} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Nicht anwesend */}
      {notPresent.length > 0 && (
        <div>
          <h3 className="font-bold text-gray-600 mb-2 flex items-center gap-2">
            <XCircle size={18} />
            Nicht anwesend ({notPresent.length})
          </h3>
          <div className="space-y-2">
            {notPresent.map(item => (
              <div key={`np-${item.id}`} className="bg-white border border-gray-200 rounded-lg p-3">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-semibold">{item.employee_name}</p>
                    <p className="text-sm text-gray-500">{item.title}</p>
                  </div>
                  <span className="text-xs text-gray-400">
                    {item.responded_at ? new Date(item.responded_at).toLocaleString('de-DE') : ''}
                  </span>
                </div>
                <ActionButtons itemType="not_present" itemId={item.id} actions={[
                  { label: 'Zur Kenntnis', action: 'noted', color: 'bg-green-100 text-green-700 hover:bg-green-200', icon: CheckCircle },
                  { label: 'Manuell buchen', action: 'booked', color: 'bg-blue-100 text-blue-700 hover:bg-blue-200', icon: BookOpen },
                ]} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Offene Korrekturen */}
      {corrections.length > 0 && (
        <div>
          <h3 className="font-bold text-blue-600 mb-2 flex items-center gap-2">
            <Clock size={18} />
            Offene Korrekturen ({corrections.length})
          </h3>
          <div className="space-y-2">
            {corrections.map(item => (
              <div key={`co-${item.id}`} className="bg-white border border-blue-200 rounded-lg p-3">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-semibold">{item.employee_name}</p>
                    <p className="text-sm text-gray-600">{item.reason}</p>
                  </div>
                  <span className="text-xs text-gray-400">
                    {item.created_at ? new Date(item.created_at).toLocaleString('de-DE') : ''}
                  </span>
                </div>
                <ActionButtons itemType="correction" itemId={item.id} actions={[
                  { label: 'Annehmen + buchen', action: 'booked', color: 'bg-green-100 text-green-700 hover:bg-green-200', icon: CheckCircle },
                  { label: 'Ablehnen', action: 'rejected', color: 'bg-red-100 text-red-700 hover:bg-red-200', icon: XCircle },
                ]} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Schichtaenderungen / Abwesenheitsmeldungen */}
      {shiftChanges.length > 0 && (
        <div>
          <h3 className="font-bold text-indigo-600 mb-2 flex items-center gap-2">
            <AlertCircle size={18} />
            Abwesenheitsmeldungen ({shiftChanges.length})
          </h3>
          <div className="space-y-2">
            {shiftChanges.map(item => {
              const isSick = item.reason?.toLowerCase().includes('krank');
              const borderColor = isSick ? 'border-red-300' : 'border-indigo-200';
              const bgColor = isSick ? 'bg-red-50' : 'bg-white';
              return (
                <div key={`sc-${item.id}`} className={`${bgColor} border ${borderColor} rounded-lg p-4`}>
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <p className="font-semibold text-gray-900">{item.employee_name}</p>
                      {item.object_name && (
                        <p className="text-sm text-gray-600 flex items-center gap-1">
                          <span>{item.object_name}</span>
                          {item.date && (
                            <span className="text-gray-400 ml-1">
                              {new Date(item.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })}
                            </span>
                          )}
                          {item.start_time && item.end_time && (
                            <span className="text-gray-400 ml-1">{item.start_time}-{item.end_time}</span>
                          )}
                        </p>
                      )}
                      <p className="text-sm mt-1">
                        <span className={`font-medium ${isSick ? 'text-red-600' : 'text-indigo-600'}`}>
                          {item.reason}
                        </span>
                      </p>
                    </div>
                    <span className="text-xs text-gray-400 whitespace-nowrap ml-2">
                      {item.created_at ? new Date(item.created_at).toLocaleString('de-DE') : ''}
                    </span>
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={async () => {
                        try {
                          await api.put(`/admin/shift-requests/${item.id}`, { status: 'resolved', admin_response: 'Vertretung eingetragen' });
                          showMessage('Vertretung eingetragen');
                          loadData();
                        } catch (e) { showMessage('Fehler'); }
                      }}
                      className="flex-1 bg-green-500 text-white text-sm py-2 px-3 rounded-lg hover:bg-green-600 font-medium flex items-center justify-center gap-1"
                    >
                      <CheckCircle size={14} /> Vertretung eingetragen
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          await api.put(`/admin/shift-requests/${item.id}`, { status: 'noted', admin_response: 'Notiert' });
                          showMessage('Notiert');
                          loadData();
                        } catch (e) { showMessage('Fehler'); }
                      }}
                      className="flex-1 bg-gray-100 text-gray-700 text-sm py-2 px-3 rounded-lg hover:bg-gray-200 font-medium border flex items-center justify-center gap-1"
                    >
                      <FileText size={14} /> Notiert
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Monatskorrekturen (disputed) */}
      {monthDisputes.length > 0 && (
        <div>
          <h3 className="font-bold text-red-600 mb-2 flex items-center gap-2">
            <XCircle size={18} />
            Monatskorrekturen ({monthDisputes.length})
          </h3>
          <div className="space-y-2">
            {monthDisputes.map(item => (
              <div key={`md-${item.id}`} className="bg-white border border-red-200 rounded-lg p-4">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-semibold">{item.employee_name}</p>
                    <p className="text-sm text-gray-600">
                      {MONATSNAMEN[item.month] || item.month} {item.year}
                    </p>
                    {item.dispute_reason && (
                      <p className="text-sm text-red-600 mt-1 bg-red-50 p-2 rounded">
                        "{item.dispute_reason}"
                      </p>
                    )}
                  </div>
                  <span className="text-xs text-gray-400">
                    {item.created_at ? new Date(item.created_at).toLocaleString('de-DE') : ''}
                  </span>
                </div>
                <div className="flex gap-2 mt-3">
                  <button
                    onClick={() => resendMonthlyConfirmation(item.employee_id, item.year, item.month)}
                    className="flex-1 bg-blue-500 text-white text-sm py-2 px-3 rounded-lg hover:bg-blue-600 font-medium flex items-center justify-center gap-1"
                  >
                    <Send size={14} /> Erneut zur Bestaetigung senden
                  </button>
                  <button
                    onClick={() => resolveItem('month_dispute', item.id, 'noted')}
                    className="bg-gray-100 text-gray-700 text-sm py-2 px-3 rounded-lg hover:bg-gray-200 font-medium border flex items-center justify-center gap-1"
                  >
                    <CheckCircle size={14} /> Erledigt
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Monatsbestaetigungen */}
      <div>
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-bold text-orange-600 flex items-center gap-2">
            <Clock size={18} />
            Monatsbestaetigungen {MONATSNAMEN[currentMonth]} {currentYear} ({pendingConfsOpen} offen)
          </h3>
          <button
            onClick={triggerMonthlyConfirmations}
            className="bg-blue-500 text-white text-xs px-3 py-1 rounded hover:bg-blue-600 flex items-center gap-1"
          >
            <Bell size={14} />
            Push ausloesen
          </button>
        </div>
        {pendingConfirmations.length > 0 && (
          <div className="space-y-2">
            {pendingConfirmations.map(conf => {
              let statusBadge;
              let borderColor = 'border-gray-200';
              if (conf.status === 'confirmed') {
                statusBadge = (
                  <span className="text-xs px-2 py-1 rounded bg-green-100 text-green-700 flex items-center gap-1">
                    <CheckCircle size={12} />
                    Bestaetigt {conf.confirmed_at ? `am ${new Date(conf.confirmed_at).toLocaleDateString('de-DE')}` : ''}
                  </span>
                );
                borderColor = 'border-green-200';
              } else if (conf.status === 'disputed') {
                statusBadge = (
                  <span className="text-xs px-2 py-1 rounded bg-red-100 text-red-700 flex items-center gap-1">
                    <XCircle size={12} />
                    Korrektur angefragt {conf.confirmed_at ? `am ${new Date(conf.confirmed_at).toLocaleDateString('de-DE')}` : ''}
                  </span>
                );
                borderColor = 'border-red-200';
              } else if (conf.sent_at) {
                statusBadge = (
                  <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-700 flex items-center gap-1">
                    <Clock size={12} />
                    Gesendet am {new Date(conf.sent_at).toLocaleDateString('de-DE')} - wartet
                  </span>
                );
                borderColor = 'border-blue-200';
              } else {
                statusBadge = (
                  <span className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-600 flex items-center gap-1">
                    &#10134; Noch nicht gesendet
                  </span>
                );
                borderColor = 'border-gray-300';
              }

              return (
                <div key={conf.employee_id} className={`bg-white border ${borderColor} rounded-lg p-3`}>
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <User size={16} className="text-gray-400" />
                      <span className="font-medium">{conf.name}</span>
                      <span className="text-xs text-gray-500">({conf.personal_nr})</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {statusBadge}
                      {(conf.status === 'disputed' || (conf.status === 'pending' && !conf.sent_at)) && (
                        <button
                          onClick={() => resendMonthlyConfirmation(conf.employee_id, currentYear, currentMonth)}
                          className="text-xs bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600 flex items-center gap-1"
                        >
                          <Send size={12} /> {conf.status === 'disputed' ? 'Erneut senden' : 'Jetzt senden'}
                        </button>
                      )}
                    </div>
                  </div>
                  {conf.dispute_reason && (
                    <p className="text-sm text-red-600 mt-1 bg-red-50 p-2 rounded">Grund: "{conf.dispute_reason}"</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Erledigt-Bereich */}
      <div className="border-t pt-4">
        <button
          onClick={() => setShowResolved(!showResolved)}
          className="flex items-center gap-2 text-gray-500 hover:text-gray-700 font-medium text-sm"
        >
          {showResolved ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          Erledigt ({resolvedItems.length})
        </button>
        {showResolved && (
          <div className="mt-3 space-y-2">
            {resolvedItems.length === 0 ? (
              <p className="text-sm text-gray-400">Keine erledigten Punkte in den letzten 7 Tagen.</p>
            ) : (
              resolvedItems.map((item, idx) => (
                <div key={`res-${item.type}-${item.id}-${idx}`} className="bg-gray-50 border border-gray-200 rounded-lg p-3 opacity-70">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <CheckCircle size={14} className="text-green-500" />
                      <span className="text-sm font-medium">{item.employee_name}</span>
                      <span className="text-xs text-gray-500">{item.title}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                        {ACTION_MAP[item.action] || item.action}
                      </span>
                      <span className="text-xs text-gray-400">
                        {item.resolved_at ? new Date(item.resolved_at).toLocaleString('de-DE') : ''}
                      </span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Notiz-Modal */}
      {noteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">Notiz hinzufuegen</h3>
            <textarea
              value={noteModal.note}
              onChange={(e) => setNoteModal({ ...noteModal, note: e.target.value })}
              className="w-full p-3 border rounded-lg"
              rows="3"
              placeholder="Notiz eingeben..."
              autoFocus
            />
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => setNoteModal(null)}
                className="flex-1 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Abbrechen
              </button>
              <button
                onClick={() => {
                  resolveItem(noteModal.type, noteModal.id, 'noted', noteModal.note);
                  setNoteModal(null);
                }}
                className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OffenePunkteTab;
