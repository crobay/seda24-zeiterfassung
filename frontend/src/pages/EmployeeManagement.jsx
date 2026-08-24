import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ArrowLeft, KeyRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_URL } from '../config.js';

const EmployeeManagement = () => {
  const [employees, setEmployees] = useState([]);
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  useEffect(() => {
    fetchEmployees();
  }, []);

  const fetchEmployees = async () => {
    try {
      const response = await axios.get(`${API_URL}/admin/employees-with-categories`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      console.log("Daten erhalten:", response.data);
      setEmployees(response.data || []);
    } catch (error) {
      console.error("Fehler beim Laden:", error);
    }
  };

  const handleCategoryChange = async (employeeId, newCategory) => {
    try {
      await axios.put(
        `${API_URL}/admin/employees/${employeeId}/category`,
        JSON.stringify(newCategory),
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );
      fetchEmployees();
    } catch (error) {
      console.error('Fehler beim Ändern der Kategorie:', error);
    }
  };

  // Wochentags-Mapping: DB speichert Python-Konvention (0=Mo..6=So)
  // JS weekday-Labels in deutscher Reihenfolge Mo-So
  const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

  const handleWorkDaysChange = async (employeeId, pyDay, checked) => {
    const emp = employees.find(e => e.id === employeeId);
    const current = emp?.work_days_profile
      ? emp.work_days_profile.split(',').map(Number)
      : [];
    const updated = checked
      ? [...new Set([...current, pyDay])].sort()
      : current.filter(d => d !== pyDay);
    const profile = updated.length > 0 ? updated.join(',') : '';
    try {
      await axios.put(
        `${API_URL}/admin/employees/${employeeId}/work-days-profile`,
        { work_days_profile: profile },
        { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } }
      );
      fetchEmployees();
    } catch (error) {
      console.error('Fehler beim Aendern des Arbeitstagsprofils:', error);
    }
  };

  const handleResetPassword = async (emp) => {
    if (!window.confirm(`Passwort von ${emp.name} wirklich zuruecksetzen?\n\nDas Passwort wird auf "seda2026" gesetzt. Der Mitarbeiter muss beim naechsten Login ein eigenes Passwort vergeben.`)) {
      return;
    }
    try {
      const response = await axios.post(
        `${API_URL}/admin/employees/${emp.id}/reset-password`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert(`Passwort zurueckgesetzt!\n\nMitarbeiter: ${emp.name}\nNeues Passwort: ${response.data.temp_password}\n\nBeim naechsten Login wird ein eigenes Passwort verlangt.`);
    } catch (error) {
      alert('Fehler: ' + (error.response?.data?.detail || 'Passwort-Reset fehlgeschlagen'));
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-lg shadow-lg p-6">
          <button
            onClick={() => navigate('/admin')}
            className="flex items-center gap-2 mb-6 text-gray-600 hover:text-gray-800"
          >
            <ArrowLeft size={20} />
            Zurück
          </button>

          <h1 className="text-3xl font-bold mb-6">Mitarbeiter-Verwaltung</h1>
          
          <div className="bg-gray-50 p-4 rounded mb-6">
            <p>Gesamt: {employees.length} Mitarbeiter</p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-100">
                  <th className="border p-2">Nr</th>
                  <th className="border p-2">Name</th>
                  <th className="border p-2">Kürzel</th>
                  <th className="border p-2">Kategorie</th>
                  <th className="border p-2">Arbeitstage</th>
                  <th className="border p-2">Passwort</th>
                </tr>
              </thead>
              <tbody>
                {employees.map((emp) => (
                  <tr key={emp.id}>
                    <td className="border p-2">{emp.personal_nr}</td>
                    <td className="border p-2">{emp.name}</td>
                    <td className="border p-2">{emp.personal_nr}</td>
                    <td className="border p-2">
                      <select
                        value={emp.tracking_mode || 'C'}
                        onChange={(e) => handleCategoryChange(emp.id, e.target.value)}
                        className="px-2 py-1 border rounded"
                      >
                        <option value="A">A</option>
                        <option value="B">B</option>
                        <option value="C">C</option>
                      </select>
                    </td>
                    <td className="border p-2">
                      <div className="flex gap-1 flex-wrap">
                        {WEEKDAY_LABELS.map((label, pyDay) => {
                          const activeDays = emp.work_days_profile
                            ? emp.work_days_profile.split(',').map(Number)
                            : [];
                          const isActive = activeDays.includes(pyDay);
                          return (
                            <label key={pyDay} className="flex items-center gap-0.5 text-xs cursor-pointer">
                              <input
                                type="checkbox"
                                checked={isActive}
                                onChange={(e) => handleWorkDaysChange(emp.id, pyDay, e.target.checked)}
                                className="w-3.5 h-3.5"
                              />
                              {label}
                            </label>
                          );
                        })}
                      </div>
                    </td>
                    <td className="border p-2 text-center">
                      <button
                        onClick={() => handleResetPassword(emp)}
                        className="text-orange-500 hover:text-orange-700 p-1"
                        title="Passwort zuruecksetzen"
                      >
                        <KeyRound size={18} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmployeeManagement;
