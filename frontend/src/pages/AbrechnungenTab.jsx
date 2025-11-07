import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { FileText, Download, Package, Calendar, Users } from 'lucide-react';

const AbrechnungenTab = () => {
  const [employees, setEmployees] = useState([]);
  const [selectedEmployees, setSelectedEmployees] = useState([]);
  const [selectAll, setSelectAll] = useState(false);
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  
  const API_URL = 'https://app.seda.de/api/v1';
  const token = localStorage.getItem('token');

  useEffect(() => {
    fetchEmployees();
  }, []);

  const fetchEmployees = async () => {
    try {
      const response = await axios.get(`${API_URL}/admin/employees-for-pdf`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setEmployees(response.data);
    } catch (error) {
      console.error('Fehler beim Laden der Mitarbeiter:', error);
    }
  };

  const handleSelectAll = () => {
    if (selectAll) {
      setSelectedEmployees([]);
    } else {
      setSelectedEmployees(employees.map(e => e.id));
    }
    setSelectAll(!selectAll);
  };

  const handleSelectEmployee = (empId) => {
    if (selectedEmployees.includes(empId)) {
      setSelectedEmployees(selectedEmployees.filter(id => id !== empId));
    } else {
      setSelectedEmployees([...selectedEmployees, empId]);
    }
  };

  const generatePDF = async (type) => {
    if (selectedEmployees.length === 0) {
      setMessage('❌ Bitte mindestens einen Mitarbeiter auswählen!');
      setTimeout(() => setMessage(''), 3000);
      return;
    }

    setLoading(true);
    setMessage('⏳ PDF wird generiert...');

    try {
      if (selectedEmployees.length === 1) {
        // Einzelner MA
        const empId = selectedEmployees[0];
        let endpoint = '';
        
        if (type === 'zeitnachweis') {
          endpoint = `${API_URL}/admin/generate-pdf-zeitnachweis`;
        } else if (type === 'kilometer') {
          endpoint = `${API_URL}/admin/generate-pdf-kilometer`;
        } else if (type === 'komplett') {
          endpoint = `${API_URL}/admin/generate-pdf-komplett`;
        }

        const response = await axios.post(
          endpoint,
          { employee_id: empId, year, month },
          {
            headers: { Authorization: `Bearer ${token}` },
            responseType: 'blob'
          }
        );

        // Download
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        const employee = employees.find(e => e.id === empId);
        const filename = employee ? `SEDA24_${type}_${employee.name.replace(/ /g, '_')}_${month}_${year}.${type === 'komplett' ? 'zip' : 'pdf'}` : `SEDA24_${type}_${month}_${year}.${type === 'komplett' ? 'zip' : 'pdf'}`;
        link.setAttribute('download', filename);
        document.body.appendChild(link);
        link.click();
        link.remove();

        setMessage('✅ PDF erfolgreich heruntergeladen!');
        
      } else {
        // Mehrere MAs - immer als Bulk
        const response = await axios.post(
          `${API_URL}/admin/generate-pdf-bulk`,
          {
            employee_ids: selectedEmployees,
            year,
            month,
            include_zeitnachweis: (type === 'zeitnachweis' || type === 'komplett'),
            include_kilometer: (type === 'kilometer' || type === 'komplett')
          },
          {
            headers: { Authorization: `Bearer ${token}` },
            responseType: 'blob'
          }
        );

        // Download ZIP
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `SEDA24_Bulk_${selectedEmployees.length}_MA_${month}_${year}.zip`);
        document.body.appendChild(link);
        link.click();
        link.remove();

        setMessage(`✅ ${selectedEmployees.length} PDFs als ZIP heruntergeladen!`);
      }
      
    } catch (error) {
      console.error('PDF-Fehler:', error);
      setMessage('❌ Fehler beim Generieren der PDF!');
    } finally {
      setLoading(false);
      setTimeout(() => setMessage(''), 5000);
    }
  };

  const monthNames = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
  ];

  return (
    <div style={{ padding: '20px' }}>
      {/* HEADER */}
      <div style={{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        borderRadius: '15px',
        padding: '30px',
        marginBottom: '30px',
        color: 'white'
      }}>
        <h2 style={{ fontSize: '28px', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <FileText size={32} />
          PDF-Abrechnungen generieren
        </h2>
        <p style={{ opacity: 0.9 }}>
          Erstellen Sie professionelle Zeitnachweise und Kilometerabrechnungen
        </p>
      </div>

      {/* AUSWAHL */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '30px' }}>
        {/* ZEITRAUM */}
        <div style={{
          background: 'white',
          borderRadius: '15px',
          padding: '25px',
          boxShadow: '0 4px 15px rgba(0,0,0,0.1)'
        }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
            <Calendar size={24} />
            Zeitraum wählen
          </h3>
          
          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: '600' }}>Monat</label>
            <select
              value={month}
              onChange={(e) => setMonth(parseInt(e.target.value))}
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '8px',
                border: '2px solid #e0e0e0',
                fontSize: '16px'
              }}
            >
              {monthNames.map((name, idx) => (
                <option key={idx} value={idx + 1}>{name}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: '600' }}>Jahr</label>
            <select
              value={year}
              onChange={(e) => setYear(parseInt(e.target.value))}
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '8px',
                border: '2px solid #e0e0e0',
                fontSize: '16px'
              }}
            >
              {[2024, 2025, 2026].map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
        </div>

        {/* INFO */}
        <div style={{
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          borderRadius: '15px',
          padding: '25px',
          color: 'white'
        }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
            <Package size={24} />
            Ausgewählte Mitarbeiter
          </h3>
          <div style={{ fontSize: '48px', fontWeight: 'bold', marginBottom: '10px' }}>
            {selectedEmployees.length}
          </div>
          <p style={{ opacity: 0.9 }}>
            {selectedEmployees.length === 1 ? 'Mitarbeiter ausgewählt' : 'Mitarbeiter ausgewählt'}
          </p>
          {selectedEmployees.length > 1 && (
            <p style={{ marginTop: '10px', fontSize: '14px', opacity: 0.9 }}>
              💡 PDFs werden als ZIP-Datei heruntergeladen
            </p>
          )}
        </div>
      </div>

      {/* MITARBEITER-LISTE */}
      <div style={{
        background: 'white',
        borderRadius: '15px',
        padding: '25px',
        boxShadow: '0 4px 15px rgba(0,0,0,0.1)',
        marginBottom: '30px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Users size={24} />
            Mitarbeiter auswählen
          </h3>
          <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={selectAll}
              onChange={handleSelectAll}
              style={{ width: '20px', height: '20px', cursor: 'pointer' }}
            />
            <span style={{ fontWeight: '600' }}>Alle auswählen</span>
          </label>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
          gap: '15px'
        }}>
          {employees.map(emp => (
            <label
              key={emp.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '15px',
                borderRadius: '10px',
                border: selectedEmployees.includes(emp.id) ? '3px solid #667eea' : '2px solid #e0e0e0',
                background: selectedEmployees.includes(emp.id) ? '#f0f4ff' : 'white',
                cursor: 'pointer',
                transition: 'all 0.3s ease'
              }}
            >
              <input
                type="checkbox"
                checked={selectedEmployees.includes(emp.id)}
                onChange={() => handleSelectEmployee(emp.id)}
                style={{ width: '20px', height: '20px', cursor: 'pointer' }}
              />
              <div>
                <div style={{ fontWeight: '600', fontSize: '14px' }}>{emp.name}</div>
                <div style={{ fontSize: '12px', color: '#666' }}>{emp.personal_nr}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* BUTTONS */}
      <div style={{
        background: 'white',
        borderRadius: '15px',
        padding: '25px',
        boxShadow: '0 4px 15px rgba(0,0,0,0.1)'
      }}>
        <h3 style={{ marginBottom: '20px' }}>PDF generieren</h3>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '15px' }}>
          <button
            onClick={() => generatePDF('zeitnachweis')}
            disabled={loading || selectedEmployees.length === 0}
            style={{
              background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a8f 100%)',
              color: 'white',
              padding: '20px',
              borderRadius: '12px',
              border: 'none',
              cursor: selectedEmployees.length > 0 ? 'pointer' : 'not-allowed',
              opacity: selectedEmployees.length > 0 ? 1 : 0.5,
              fontSize: '16px',
              fontWeight: '600',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '10px',
              transition: 'transform 0.2s'
            }}
            onMouseOver={(e) => selectedEmployees.length > 0 && (e.currentTarget.style.transform = 'translateY(-3px)')}
            onMouseOut={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
          >
            <FileText size={32} />
            Zeitnachweis PDF
          </button>

          <button
            onClick={() => generatePDF('kilometer')}
            disabled={loading || selectedEmployees.length === 0}
            style={{
              background: 'linear-gradient(135deg, #d97706 0%, #b45309 100%)',
              color: 'white',
              padding: '20px',
              borderRadius: '12px',
              border: 'none',
              cursor: selectedEmployees.length > 0 ? 'pointer' : 'not-allowed',
              opacity: selectedEmployees.length > 0 ? 1 : 0.5,
              fontSize: '16px',
              fontWeight: '600',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '10px',
              transition: 'transform 0.2s'
            }}
            onMouseOver={(e) => selectedEmployees.length > 0 && (e.currentTarget.style.transform = 'translateY(-3px)')}
            onMouseOut={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
          >
            <Download size={32} />
            Kilometer PDF
          </button>

          <button
            onClick={() => generatePDF('komplett')}
            disabled={loading || selectedEmployees.length === 0}
            style={{
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
              color: 'white',
              padding: '20px',
              borderRadius: '12px',
              border: 'none',
              cursor: selectedEmployees.length > 0 ? 'pointer' : 'not-allowed',
              opacity: selectedEmployees.length > 0 ? 1 : 0.5,
              fontSize: '16px',
              fontWeight: '600',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '10px',
              transition: 'transform 0.2s'
            }}
            onMouseOver={(e) => selectedEmployees.length > 0 && (e.currentTarget.style.transform = 'translateY(-3px)')}
            onMouseOut={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
          >
            <Package size={32} />
            Komplett-Paket
          </button>
        </div>

        {message && (
          <div style={{
            marginTop: '20px',
            padding: '15px',
            borderRadius: '10px',
            background: message.includes('✅') ? '#d1fae5' : message.includes('❌') ? '#fee2e2' : '#fef3c7',
            color: message.includes('✅') ? '#065f46' : message.includes('❌') ? '#991b1b' : '#92400e',
            textAlign: 'center',
            fontWeight: '600'
          }}>
            {message}
          </div>
        )}
      </div>
    </div>
  );
};

export default AbrechnungenTab;
