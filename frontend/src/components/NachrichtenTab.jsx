import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Send, MessageCircle, Clock, CheckCircle, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';

const NachrichtenTab = () => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState('');
  const [body, setBody] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState(null);
  const [expandedMsg, setExpandedMsg] = useState(null);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    loadMessages();
  }, []);

  const loadMessages = async () => {
    setLoading(true);
    try {
      const res = await api.get('/messages/my-messages');
      setMessages(res.data);
    } catch (error) {
      console.error('Fehler:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!category) {
      showToast('Bitte Kategorie w\u00E4hlen', 'error');
      return;
    }
    if (!body.trim()) {
      showToast('Bitte Nachricht eingeben', 'error');
      return;
    }
    setSubmitting(true);
    try {
      await api.post('/messages/send', { category, body });
      showToast('Nachricht gesendet!', 'success');
      setCategory('');
      setBody('');
      loadMessages();
    } catch (error) {
      showToast('Fehler beim Senden', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const getCategoryLabel = (cat) => {
    const labels = {
      material: 'Material fehlt',
      reklamation: 'Reklamation',
      problem: 'Problem',
      sonstiges: 'Sonstiges',
    };
    return labels[cat] || cat;
  };

  const getCategoryColor = (cat) => {
    const colors = {
      material: 'bg-orange-100 text-orange-800',
      reklamation: 'bg-red-100 text-red-800',
      problem: 'bg-yellow-100 text-yellow-800',
      sonstiges: 'bg-blue-100 text-blue-800',
    };
    return colors[cat] || 'bg-gray-100 text-gray-800';
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'neu': return <Clock size={14} className="text-yellow-500" />;
      case 'gelesen': return <CheckCircle size={14} className="text-blue-500" />;
      case 'beantwortet': return <MessageCircle size={14} className="text-green-500" />;
      default: return null;
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="space-y-5 p-4">
      {/* Formular */}
      <div className="bg-white rounded-xl shadow-sm border p-5">
        <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
          <Send className="text-blue-500" size={20} />
          Nachricht an Verwaltung
        </h3>

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Was m{'\u00F6'}chtest du melden?</label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'material', label: 'Material fehlt', emoji: '\U0001F4E6' },
                { value: 'reklamation', label: 'Reklamation', emoji: '\u26A0\uFE0F' },
                { value: 'problem', label: 'Problem', emoji: '\u2757' },
                { value: 'sonstiges', label: 'Sonstiges', emoji: '\U0001F4AC' },
              ].map((cat) => (
                <button
                  key={cat.value}
                  onClick={() => setCategory(cat.value)}
                  className={`p-3 rounded-lg border-2 text-sm font-medium transition-colors text-left ${
                    category === cat.value
                      ? 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                  }`}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nachricht</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full p-3 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              rows={4}
              placeholder="Beschreibe dein Anliegen..."
            />
          </div>

          <button
            onClick={handleSend}
            disabled={submitting || !category || !body.trim()}
            className="w-full py-3 bg-blue-500 text-white rounded-lg font-bold hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {submitting ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Wird gesendet...
              </>
            ) : (
              <>
                <Send size={18} />
                Absenden
              </>
            )}
          </button>
        </div>
      </div>

      {/* Meine Nachrichten */}
      <div className="bg-white rounded-xl shadow-sm border p-5">
        <h3 className="text-lg font-bold text-gray-800 mb-4">Meine Nachrichten</h3>
        {loading ? (
          <div className="text-center py-4 text-gray-500">Lade...</div>
        ) : messages.length === 0 ? (
          <p className="text-gray-500 text-center py-4">Noch keine Nachrichten</p>
        ) : (
          <div className="space-y-3">
            {messages.map((msg) => (
              <div key={msg.id} className="border rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedMsg(expandedMsg === msg.id ? null : msg.id)}
                  className="w-full p-3 flex items-center justify-between text-left hover:bg-gray-50"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${getCategoryColor(msg.category)}`}>
                        {getCategoryLabel(msg.category)}
                      </span>
                      {getStatusIcon(msg.status)}
                    </div>
                    <p className="text-sm text-gray-700 truncate">{msg.body}</p>
                    <p className="text-xs text-gray-400 mt-1">{formatDate(msg.created_at)}</p>
                  </div>
                  {msg.replies?.length > 0 && (
                    <div className="flex items-center gap-1 ml-2">
                      <span className="text-xs text-green-600 font-medium">{msg.replies.length} Antwort{msg.replies.length > 1 ? 'en' : ''}</span>
                      {expandedMsg === msg.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </div>
                  )}
                </button>

                {expandedMsg === msg.id && (
                  <div className="border-t bg-gray-50 p-3 space-y-2">
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{msg.body}</p>
                    {msg.replies?.map((reply) => (
                      <div key={reply.id} className={`p-2 rounded-lg text-sm ${reply.is_admin ? 'bg-blue-50 border-l-4 border-blue-400' : 'bg-gray-100'}`}>
                        <div className="text-xs text-gray-500 mb-1">
                          {reply.is_admin ? 'Admin' : 'Du'} - {formatDate(reply.created_at)}
                        </div>
                        <p className="text-gray-700">{reply.body}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-20 left-4 right-4 px-4 py-3 rounded-lg shadow-lg z-50 text-white text-sm font-medium
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

export default NachrichtenTab;
