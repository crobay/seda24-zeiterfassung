import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

function ChangePassword() {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
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
      await api.post('/auth/change-password', { new_password: newPassword });
      alert('Passwort erfolgreich geändert!');
      navigate('/dashboard');
    } catch (err) {
      setError('Fehler beim Ändern des Passworts');
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="bg-white p-8 rounded-lg shadow-md w-96">
        <h2 className="text-2xl font-bold mb-6">Passwort ändern erforderlich</h2>
        <p className="text-gray-600 mb-4">Bitte ändern Sie Ihr Passwort.</p>
        
        {error && <p className="text-red-500 mb-4">{error}</p>}
        
        <form onSubmit={handleSubmit}>
          <input
            type="password"
            placeholder="Neues Passwort"
            className="w-full p-2 mb-4 border rounded"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="Passwort bestätigen"
            className="w-full p-2 mb-4 border rounded"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
          <button
            type="submit"
            className="w-full bg-blue-500 text-white p-2 rounded hover:bg-blue-600"
          >
            Passwort ändern
          </button>
        </form>
      </div>
    </div>
  );
}

export default ChangePassword;
