import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import { API_URL } from '../config.js';

const ResetPasswordPage = () => {
  const { token } = useParams();
  const navigate = useNavigate();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tokenValid, setTokenValid] = useState(null);

  useEffect(() => {
    axios.get(`${API_URL}/auth/verify-reset-token/${token}`)
      .then(() => setTokenValid(true))
      .catch(() => setTokenValid(false));
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Passwoerter stimmen nicht ueberein!');
      return;
    }
    if (newPassword.length < 6) {
      setError('Passwort muss mindestens 6 Zeichen lang sein!');
      return;
    }

    setLoading(true);
    try {
      await axios.post(`${API_URL}/auth/reset-password-by-token`, {
        token, new_password: newPassword,
      });
      setSuccess(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Fehler beim Zuruecksetzen');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="bg-white rounded-lg shadow-md p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold mb-2 text-center">Neues Passwort vergeben</h1>

        {tokenValid === null && (
          <p className="text-gray-500 text-center py-8">Link wird geprueft...</p>
        )}

        {tokenValid === false && (
          <div>
            <div className="bg-red-50 text-red-600 p-4 rounded-lg mb-4 text-sm text-center">
              Dieser Link ist ungueltig oder abgelaufen.
            </div>
            <button
              onClick={() => navigate('/login')}
              className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600"
            >
              Zum Login
            </button>
          </div>
        )}

        {tokenValid === true && !success && (
          <form onSubmit={handleSubmit}>
            <p className="text-gray-500 text-center mb-6 text-sm">
              Gib dein neues Passwort ein.
            </p>

            {error && <div className="bg-red-50 text-red-600 p-3 rounded-lg mb-4 text-sm">{error}</div>}

            <input
              type="password"
              placeholder="Neues Passwort"
              className="w-full px-4 py-2 mb-4 border rounded-lg focus:outline-none focus:border-blue-500"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              required
              autoFocus
            />
            <input
              type="password"
              placeholder="Passwort bestaetigen"
              className="w-full px-4 py-2 mb-4 border rounded-lg focus:outline-none focus:border-blue-500"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 disabled:opacity-50"
            >
              {loading ? 'Speichere...' : 'Passwort speichern'}
            </button>
          </form>
        )}

        {success && (
          <div>
            <div className="bg-green-50 text-green-600 p-4 rounded-lg mb-4 text-sm text-center">
              Passwort wurde erfolgreich geaendert!
            </div>
            <button
              onClick={() => navigate('/login')}
              className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600"
            >
              Zum Login
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ResetPasswordPage;
