import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

const API_URL = 'https://192.168.178.87:8001/api/v1';

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');

    try {
      const response = await axios.post(`${API_URL}/auth/login`, {
        email,
        password,
      });

      // Das ist unser "Mikrofon", um zu sehen, was der Server wirklich schickt
      console.log('ANTWORT VOM SERVER:', response.data);

      if (response.data.access_token) {
        // Alle Daten im Browser speichern
        localStorage.setItem('token', response.data.access_token);
        localStorage.setItem('userEmail', email);
        localStorage.setItem('userEmail', email);
        localStorage.setItem('userRole', response.data.role);
        localStorage.setItem('userName', response.data.user_name);
        localStorage.setItem('personalNr', response.data.personal_nr);

        // Weiterleiten basierend auf der Rolle
        if (response.data.role === 'admin') {
          navigate('/admin');
        } else {
          navigate('/dashboard');
        }
      } else {
         setError("Login fehlgeschlagen. Ungültige Antwort vom Server.");
      }
    } catch (err) {
      setError("Login fehlgeschlagen. Bitte überprüfe deine Eingaben.");
      console.error("Login-Fehler:", err);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-blue-200 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
        <h1 className="text-3xl font-bold text-gray-800 text-center mb-2">SEDA24</h1>
        <p className="text-center text-gray-600 mb-8">Zeiterfassung</p>
        
        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Passwort</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          
          {error && <p className="text-red-500 text-sm text-center">{error}</p>}
          
          <div>
            <button
              type="submit"
              className="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-lg font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Anmelden
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Login;
