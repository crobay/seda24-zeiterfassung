import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const EmployeeManagement = () => {
  const [employees, setEmployees] = useState([]);
  const navigate = useNavigate();
  
  const API_URL = 'https://192.168.178.87:8001/api/v1';
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
