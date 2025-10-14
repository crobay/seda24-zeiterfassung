import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const navigate = useNavigate();

const API_URL = 'https://app.seda.de/api/v1';

const handleLogin = async (e) => {
  e.preventDefault();
  setError('');
  
  try {
    const response = await axios.post(`${API_URL}/auth/login`, {
      email,
      password,
    });
    
    console.log('ANTWORT VOM SERVER:', response.data);
    
    if (response.data.access_token) {
      localStorage.setItem('token', response.data.access_token);
      localStorage.setItem('userEmail', email);
      localStorage.setItem('userRole', response.data.role);
      localStorage.setItem('userName', response.data.user_name);
      localStorage.setItem('personalNr', response.data.personal_nr);
      
      console.log("Login Response:", response.data);
      console.log("Checking must_change_password:", response.data.must_change_password === true, typeof response.data.must_change_password);
      console.log("About to setShowChangePassword:", response.data.must_change_password);
      if (response.data.must_change_password) {
        setShowChangePassword(true);
      } else {
        if (response.data.role === 'admin') {
          navigate('/admin');
        } else {
          navigate('/dashboard');
        }
      }
    } else {
      setError("Login fehlgeschlagen. Ungültige Antwort vom Server.");
    }
  } catch (err) {
    setError("Login fehlgeschlagen. Bitte überprüfe deine Eingaben.");
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
    const token = localStorage.getItem('token');
    await axios.post(`${API_URL}/auth/change-password`, 
      { new_password: newPassword },
      { headers: { 'Authorization': `Bearer ${token}` }}
    );
    
    alert('Passwort erfolgreich geändert!');
    const role = localStorage.getItem('userRole');
    if (role === 'admin') {
      navigate('/admin');
    } else {
      navigate('/dashboard');
    }
  } catch (err) {
    setError('Fehler beim Ändern des Passworts');
  }
};

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
              required
            />
            <input
              type="password"
              placeholder="Passwort bestätigen"
              className="w-full px-4 py-2 mb-4 border rounded-lg"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
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
        
        <form onSubmit={handleLogin}>
          <div className="mb-4">
            <label className="block text-gray-700 mb-2">E-Mail:</label>
            <input
              type="email"
              className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:border-blue-500"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          
          <div className="mb-6">
            <label className="block text-gray-700 mb-2">Passwort:</label>
            <input
              type="password"
              className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:border-blue-500"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          
          <button
            type="submit"
            className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 transition-colors"
          >
            Einloggen
          </button>
        </form>
      </div>
    </div>
  );
};

export default Login;
