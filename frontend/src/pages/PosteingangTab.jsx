import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Mail, Send, Check, X, Clock, Eye, MessageCircle, Image, ChevronLeft, Users, Megaphone } from 'lucide-react';

const PosteingangTab = ({ employees = [] }) => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [selectedMsg, setSelectedMsg] = useState(null);
  const [msgDetail, setMsgDetail] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [replying, setReplying] = useState(false);
  const [activeView, setActiveView] = useState('inbox');
  const [toast, setToast] = useState(null);

  // Broadcast Form
  const [broadcastBody, setBroadcastBody] = useState('');
  const [broadcastSubject, setBroadcastSubject] = useState('');
  const [broadcastRecipients, setBroadcastRecipients] = useState([]);
  const [sendingBroadcast, setSendingBroadcast] = useState(false);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    if (activeView === 'inbox') loadMessages();
  }, [filterStatus, activeView]);

  const loadMessages = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/messages/admin/inbox${filterStatus ? `?status=${filterStatus}` : ''}`);
      setMessages(res.data);
    } catch (error) {
      console.error('Fehler:', error);
    } finally {
      setLoading(false);
    }
  };

  const openDetail = async (msgId) => {
    try {
      const res = await api.get(`/messages/admin/message/${msgId}`);
      setMsgDetail(res.data);
      setSelectedMsg(msgId);
      setReplyText('');
      loadMessages();
    } catch (error) {
      showToast('Fehler beim Laden', 'error');
    }
  };

  const sendReply = async () => {
    if (!replyText.trim()) return;
    setReplying(true);
    try {
      await api.post(`/messages/admin/reply/${selectedMsg}`, { body: replyText });
      showToast('Antwort gesendet', 'success');
      setReplyText('');
      openDetail(selectedMsg);
    } catch (error) {
      showToast('Fehler beim Senden', 'error');
    } finally {
      setReplying(false);
    }
  };

  const viewPhoto = async (msgId) => {
    try {
      const res = await api.get(`/messages/admin/message/${msgId}/photo`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      window.open(url, '_blank');
    } catch (error) {
      showToast('Foto nicht verf\u00FCgbar', 'error');
    }
  };

  const sendBroadcast = async () => {
    if (!broadcastBody.trim()) {
      showToast('Bitte Nachricht eingeben', 'error');
      return;
    }
    setSendingBroadcast(true);
    try {
      const res = await api.post('/messages/admin/broadcast', {
        subject: broadcastSubject || 'Firmen-Mitteilung',
        body: broadcastBody,
        recipient_employee_ids: broadcastRecipients.length > 0 ? broadcastRecipients : [],
      });
      showToast(`Mitteilung an ${res.data.sent_count} MA gesendet`, 'success');
      setBroadcastBody('');
      setBroadcastSubject('');
      setBroadcastRecipients([]);
    } catch (error) {
      showToast('Fehler beim Senden', 'error');
    } finally {
      setSendingBroadcast(false);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const getCategoryLabel = (cat) => {
    return { material: 'Material fehlt', reklamation: 'Reklamation', problem: 'Problem', sonstiges: 'Sonstiges' }[cat] || cat;
  };

  const getCategoryColor = (cat) => {
    return { material: 'bg-orange-100 text-orange-800', reklamation: 'bg-red-100 text-red-800', problem: 'bg-yellow-100 text-yellow-800', sonstiges: 'bg-blue-100 text-blue-800' }[cat] || 'bg-gray-100 text-gray-800';
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'neu': return { bg: 'bg-red-100', text: 'text-red-800', label: 'Neu' };
      case 'gelesen': return { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Gelesen' };
      case 'beantwortet': return { bg: 'bg-green-100', text: 'text-green-800', label: 'Beantwortet' };
      default: return { bg: 'bg-gray-100', text: 'text-gray-800', label: status };
    }
  };

  const newCount = messages.filter(m => m.status === 'neu').length;

  // Detail-Ansicht
  if (selectedMsg && msgDetail) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => { setSelectedMsg(null); setMsgDetail(null); }}
          className="flex items-center gap-2 text-blue-600 hover:text-blue-800"
        >
          <ChevronLeft size={20} />
          Zur{'\u00FC'}ck zum Posteingang
        </button>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <span className={`px-2 py-1 rounded-full text-xs font-medium ${getCategoryColor(msgDetail.category)}`}>
              {getCategoryLabel(msgDetail.category)}
            </span>
            <span className="text-sm text-gray-500">{formatDate(msgDetail.created_at)}</span>
          </div>
          <div className="mb-4">
            <h3 className="font-bold text-lg">{msgDetail.employee_name}</h3>
            <p className="text-sm text-gray-500">{msgDetail.personal_nr}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-4 mb-4">
            <p className="text-gray-700 whitespace-pre-wrap">{msgDetail.body}</p>
          </div>
          {msgDetail.has_photo && (
            <button
              onClick={() => viewPhoto(msgDetail.id)}
              className="mb-4 px-3 py-2 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 flex items-center gap-2 text-sm"
            >
              <Image size={16} />
              Foto ansehen
            </button>
          )}

          {/* Antworten */}
          {msgDetail.replies?.length > 0 && (
            <div className="space-y-3 mb-4">
              <h4 className="font-medium text-gray-700">Antworten:</h4>
              {msgDetail.replies.map((reply) => (
                <div key={reply.id} className={`p-3 rounded-lg ${reply.is_admin ? 'bg-blue-50 border-l-4 border-blue-400' : 'bg-gray-50'}`}>
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>{reply.sender_name}</span>
                    <span>{formatDate(reply.created_at)}</span>
                  </div>
                  <p className="text-sm text-gray-700">{reply.body}</p>
                </div>
              ))}
            </div>
          )}

          {/* Antwort-Formular */}
          <div className="border-t pt-4">
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              className="w-full p-3 border rounded-lg text-sm mb-3"
              rows={3}
              placeholder="Antwort schreiben..."
            />
            <button
              onClick={sendReply}
              disabled={replying || !replyText.trim()}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300 flex items-center gap-2"
            >
              {replying ? 'Sende...' : <><Send size={16} /> Antworten</>}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Kommunikation</h2>
          {newCount > 0 && (
            <p className="text-red-600 font-medium">{newCount} neue Nachrichten</p>
          )}
        </div>
        <div className="flex bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setActiveView('inbox')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeView === 'inbox' ? 'bg-white shadow text-blue-600' : 'text-gray-600'}`}
          >
            Posteingang
          </button>
          <button
            onClick={() => setActiveView('broadcast')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeView === 'broadcast' ? 'bg-white shadow text-blue-600' : 'text-gray-600'}`}
          >
            Mitteilung
          </button>
        </div>
      </div>

      {/* Posteingang */}
      {activeView === 'inbox' && (
        <>
          {/* Filter */}
          <div className="flex gap-2 flex-wrap">
            {[
              { value: '', label: 'Alle' },
              { value: 'neu', label: 'Neu' },
              { value: 'gelesen', label: 'Gelesen' },
              { value: 'beantwortet', label: 'Beantwortet' },
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

          {/* Liste */}
          <div className="bg-white rounded-lg shadow overflow-hidden">
            {loading ? (
              <div className="p-8 text-center text-gray-500">Lade...</div>
            ) : messages.length === 0 ? (
              <div className="p-8 text-center text-gray-500">Keine Nachrichten</div>
            ) : (
              <div className="divide-y">
                {messages.map((msg) => {
                  const badge = getStatusBadge(msg.status);
                  return (
                    <button
                      key={msg.id}
                      onClick={() => openDetail(msg.id)}
                      className={`w-full p-4 text-left hover:bg-gray-50 transition-colors ${msg.status === 'neu' ? 'bg-red-50/30' : ''}`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0 mr-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-sm">{msg.employee_name}</span>
                            <span className="text-xs text-gray-400">{msg.personal_nr}</span>
                          </div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${getCategoryColor(msg.category)}`}>
                              {getCategoryLabel(msg.category)}
                            </span>
                            {msg.has_photo && <Image size={14} className="text-gray-400" />}
                            {msg.replies_count > 0 && (
                              <span className="text-xs text-green-600">{msg.replies_count} Antwort{msg.replies_count > 1 ? 'en' : ''}</span>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 truncate">{msg.body}</p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${badge.bg} ${badge.text}`}>
                            {badge.label}
                          </span>
                          <p className="text-xs text-gray-400 mt-1">{formatDate(msg.created_at)}</p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      {/* Firmen-Mitteilung */}
      {activeView === 'broadcast' && (
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Megaphone size={22} className="text-blue-500" />
            Firmen-Mitteilung senden
          </h3>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Betreff</label>
            <input
              type="text"
              value={broadcastSubject}
              onChange={(e) => setBroadcastSubject(e.target.value)}
              className="w-full p-2 border rounded-lg"
              placeholder="Firmen-Mitteilung"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nachricht</label>
            <textarea
              value={broadcastBody}
              onChange={(e) => setBroadcastBody(e.target.value)}
              className="w-full p-3 border rounded-lg"
              rows={5}
              placeholder="Nachricht an alle Mitarbeiter..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Empf{'\u00E4'}nger ({broadcastRecipients.length > 0 ? `${broadcastRecipients.length} ausgew\u00E4hlt` : 'Alle Mitarbeiter'})
            </label>
            <div className="max-h-48 overflow-y-auto border rounded-lg p-2 space-y-1">
              {employees.map(emp => (
                <label key={emp.id} className="flex items-center gap-2 p-1.5 hover:bg-gray-50 rounded cursor-pointer">
                  <input
                    type="checkbox"
                    checked={broadcastRecipients.includes(emp.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setBroadcastRecipients([...broadcastRecipients, emp.id]);
                      } else {
                        setBroadcastRecipients(broadcastRecipients.filter(id => id !== emp.id));
                      }
                    }}
                    className="w-4 h-4 rounded border-gray-300"
                  />
                  <span className="text-sm">{emp.name}</span>
                  <span className="text-xs text-gray-400">{emp.personal_nr}</span>
                </label>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Keine Auswahl = alle aktiven Mitarbeiter
            </p>
          </div>

          <button
            onClick={sendBroadcast}
            disabled={sendingBroadcast || !broadcastBody.trim()}
            className="w-full py-3 bg-blue-500 text-white rounded-lg font-bold hover:bg-blue-600 disabled:bg-gray-300 flex items-center justify-center gap-2"
          >
            {sendingBroadcast ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Wird gesendet...
              </>
            ) : (
              <>
                <Send size={18} />
                Mitteilung senden
              </>
            )}
          </button>
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

export default PosteingangTab;
