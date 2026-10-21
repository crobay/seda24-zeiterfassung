import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API_URL } from '../config.js';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState('');
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const navigate = useNavigate();

  // Passwort-Reset States
  const [showResetFlow, setShowResetFlow] = useState(false);
  const [resetMethod, setResetMethod] = useState(null); // null | 'telegram' | 'email'
  const [resetStep, setResetStep] = useState(1);
  const [resetEmail, setResetEmail] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [resetConfirmPassword, setResetConfirmPassword] = useState('');
  const [resetMessage, setResetMessage] = useState('');
  const [resetError, setResetError] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetSuccess, setResetSuccess] = useState(false);

const handleLogin = async (e) => {
  e.preventDefault();
  setError('');

  try {
    const response = await axios.post(`${API_URL}/auth/login`, {
      email,
      password,
    });

    if (response.data.access_token) {
      // Token je nach "Eingeloggt bleiben" speichern
      const storage = rememberMe ? localStorage : sessionStorage;
      storage.setItem('token', response.data.access_token);
      localStorage.setItem('userEmail', email);
      localStorage.setItem('userRole', response.data.role);
      localStorage.setItem('userName', response.data.user_name);
      localStorage.setItem('personalNr', response.data.personal_nr);

      if (response.data.must_change_password) {
        setShowChangePassword(true);
      } else {
        if (response.data.role === 'admin' || response.data.role === 'objektleiter') {
          navigate('/admin');
        } else {
          navigate('/dashboard');
        }
      }
    } else {
      setError("Login fehlgeschlagen. Ungueltige Antwort vom Server.");
    }
  } catch (err) {
    setError("Login fehlgeschlagen. Bitte ueberpruefen Sie Ihre Eingaben.");
    console.error("Login-Fehler:", err);
  }
};

const handlePasswordChange = async (e) => {
  e.preventDefault();

  if (newPassword !== confirmPassword) {
    setError('Passwörter stimmen nicht überein!');
    return;
  }

  if (newPassword.length < 6) {
    setError('Passwort muss mindestens 6 Zeichen lang sein!');
    return;
  }

  try {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    await axios.post(`${API_URL}/auth/change-password`,
      { new_password: newPassword },
      { headers: { 'Authorization': `Bearer ${token}` }}
    );

    alert('Passwort erfolgreich geändert!');
    const role = localStorage.getItem('userRole');
    if (role === 'admin' || role === 'objektleiter') {
      navigate('/admin');
    } else {
      navigate('/dashboard');
    }
  } catch (err) {
    setError('Fehler beim Ändern des Passworts');
  }
};

  const handleRequestReset = async (e) => {
    e.preventDefault();
    setResetError('');
    setResetMessage('');
    setResetLoading(true);
    try {
      await axios.post(`${API_URL}/auth/request-password-reset`, { email: resetEmail });
      setResetMessage('Code wurde per Telegram gesendet!');
      setResetStep(2);
    } catch (err) {
      setResetError(err.response?.data?.detail || 'Fehler beim Anfordern des Codes');
    } finally {
      setResetLoading(false);
    }
  };

  const handleRequestResetEmail = async (e) => {
    e.preventDefault();
    setResetError('');
    setResetMessage('');
    setResetLoading(true);
    try {
      await axios.post(`${API_URL}/auth/request-password-reset-email`, { email: resetEmail });
      setResetMessage('Falls die Adresse bekannt ist, wurde eine E-Mail mit einem Reset-Link verschickt. Bitte pruefe auch den Spam-Ordner.');
      setResetSuccess(true);
    } catch (err) {
      setResetError(err.response?.data?.detail || 'Fehler beim Anfordern');
    } finally {
      setResetLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setResetError('');
    if (resetNewPassword !== resetConfirmPassword) {
      setResetError('Passwörter stimmen nicht überein!');
      return;
    }
    if (resetNewPassword.length < 6) {
      setResetError('Passwort muss mindestens 6 Zeichen lang sein!');
      return;
    }
    setResetLoading(true);
    try {
      await axios.post(`${API_URL}/auth/reset-password`, {
        email: resetEmail, code: resetCode, new_password: resetNewPassword,
      });
      setResetSuccess(true);
      setResetMessage('Passwort wurde erfolgreich zurückgesetzt!');
    } catch (err) {
      setResetError(err.response?.data?.detail || 'Fehler beim Zuruecksetzen');
    } finally {
      setResetLoading(false);
    }
  };

  const backToLogin = () => {
    setShowResetFlow(false);
    setResetMethod(null);
    setResetStep(1);
    setResetEmail('');
    setResetCode('');
    setResetNewPassword('');
    setResetConfirmPassword('');
    setResetMessage('');
    setResetError('');
    setResetSuccess(false);
  };

  // Passwort-Reset Flow
  if (showResetFlow) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="bg-white rounded-lg shadow-md p-8 w-full max-w-md">
          <h1 className="text-2xl font-bold mb-2 text-center">Passwort zuruecksetzen</h1>

          {resetError && <div className="bg-red-50 text-red-600 p-3 rounded-lg mb-4 text-sm">{resetError}</div>}
          {resetMessage && <div className="bg-green-50 text-green-600 p-3 rounded-lg mb-4 text-sm">{resetMessage}</div>}

          {resetSuccess ? (
            <button onClick={backToLogin} className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600">
              Zurueck zum Login
            </button>
          ) : !resetMethod ? (
            /* Methoden-Auswahl */
            <>
              <p className="text-gray-500 text-center mb-6 text-sm">Wie moechtest du dein Passwort zuruecksetzen?</p>
              <button
                onClick={() => setResetMethod('email')}
                className="w-full bg-blue-500 text-white py-3 rounded-lg hover:bg-blue-600 mb-3 flex items-center justify-center gap-2"
              >
                Per E-Mail
              </button>
              <button
                onClick={() => setResetMethod('telegram')}
                className="w-full bg-gray-100 text-gray-700 py-3 rounded-lg hover:bg-gray-200 flex items-center justify-center gap-2"
              >
                Per Telegram
              </button>
            </>
          ) : resetMethod === 'email' ? (
            /* E-Mail Reset */
            <form onSubmit={handleRequestResetEmail}>
              <p className="text-gray-500 text-center mb-4 text-sm">
                Gib deine E-Mail-Adresse ein. Du erhaeltst einen Link zum Zuruecksetzen.
              </p>
              <input
                type="email"
                placeholder="E-Mail Adresse"
                className="w-full px-4 py-2 mb-4 border rounded-lg focus:outline-none focus:border-blue-500"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                required
                autoFocus
              />
              <button
                type="submit"
                disabled={resetLoading}
                className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 disabled:opacity-50"
              >
                {resetLoading ? 'Sende...' : 'Reset-Link anfordern'}
              </button>
            </form>
          ) : resetStep === 1 ? (
            /* Telegram Reset - Schritt 1 */
            <form onSubmit={handleRequestReset}>
              <p className="text-gray-500 text-center mb-4 text-sm">
                Gib deine E-Mail ein. Du erhaeltst einen Code per Telegram.
              </p>
              <input
                type="email"
                placeholder="E-Mail Adresse"
                className="w-full px-4 py-2 mb-4 border rounded-lg focus:outline-none focus:border-blue-500"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                required
                autoFocus
              />
              <button
                type="submit"
                disabled={resetLoading}
                className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 disabled:opacity-50"
              >
                {resetLoading ? 'Sende Code...' : 'Code anfordern'}
              </button>
            </form>
          ) : (
            /* Telegram Reset - Schritt 2 */
            <form onSubmit={handleResetPassword}>
              <p className="text-gray-500 text-center mb-4 text-sm">
                Gib den Code aus Telegram und dein neues Passwort ein.
              </p>
              <input
                type="text"
                placeholder="6-stelliger Code"
                className="w-full px-4 py-2 mb-4 border rounded-lg focus:outline-none focus:border-blue-500 text-center text-2xl tracking-widest"
                value={resetCode}
                onChange={(e) => setResetCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                required
                autoFocus
              />
              <input
                type="password"
                placeholder="Neues Passwort"
                className="w-full px-4 py-2 mb-4 border rounded-lg focus:outline-none focus:border-blue-500"
                value={resetNewPassword}
                onChange={(e) => setResetNewPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
              <input
                type="password"
                placeholder="Passwort bestaetigen"
                className="w-full px-4 py-2 mb-4 border rounded-lg focus:outline-none focus:border-blue-500"
                value={resetConfirmPassword}
                onChange={(e) => setResetConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
              <button
                type="submit"
                disabled={resetLoading}
                className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 disabled:opacity-50"
              >
                {resetLoading ? 'Setze zurueck...' : 'Passwort zuruecksetzen'}
              </button>
            </form>
          )}

          {!resetSuccess && (
            <button onClick={backToLogin} className="w-full mt-3 text-sm text-blue-500 hover:underline">
              Zurueck zum Login
            </button>
          )}
        </div>
      </div>
    );
  }

  if (showChangePassword) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="bg-white rounded-lg shadow-md p-8 w-full max-w-md">
          <h1 className="text-2xl font-bold mb-6 text-center">Passwort ändern erforderlich</h1>
          <p className="text-gray-600 mb-4">Bitte ändern Sie Ihr Passwort.</p>

          {error && <p className="text-red-500 mb-4">{error}</p>}

          <form onSubmit={handlePasswordChange}>
            <input
              type="password"
              placeholder="Neues Passwort"
              className="w-full px-4 py-2 mb-4 border rounded-lg"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            <input
              type="password"
              placeholder="Passwort bestaetigen"
              className="w-full px-4 py-2 mb-4 border rounded-lg"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            <button
              type="submit"
              className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600"
            >
              Passwort ändern
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="bg-white rounded-lg shadow-md p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold mb-6 text-center">Login</h1>

        {error && (
          <p className="text-red-500 text-center mb-4">{error}</p>
        )}

        <form onSubmit={handleLogin} autoComplete="on">
          <div className="mb-4">
            <label className="block text-gray-700 mb-2">E-Mail:</label>
            <input
              type="email"
              name="email"
              autoComplete="email"
              className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:border-blue-500"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="mb-4">
            <label className="block text-gray-700 mb-2">Passwort:</label>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:border-blue-500"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <div className="mb-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-4 h-4 text-blue-500 border-gray-300 rounded focus:ring-blue-500"
              />
              <span className="text-sm text-gray-600">Eingeloggt bleiben (30 Tage)</span>
            </label>
          </div>

          <button
            type="submit"
            className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 transition-colors"
          >
            Einloggen
          </button>
        </form>

        <button
          onClick={() => { setShowResetFlow(true); setError(''); }}
          className="w-full mt-4 text-sm text-blue-500 hover:underline"
        >
          Passwort vergessen?
        </button>

        <a
          href="/hilfe/"
          target="_blank"
          rel="noopener noreferrer"
          className="w-full mt-2 text-sm text-gray-400 hover:text-blue-500 hover:underline block text-center"
        >
          Hilfe & FAQ
        </a>
      </div>
    </div>
  );
};

export default Login;
