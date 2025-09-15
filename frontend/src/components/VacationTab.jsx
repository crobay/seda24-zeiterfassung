import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Calendar } from 'lucide-react';

const VacationTab = ({ token }) => {
  const [vacationData, setVacationData] = useState(null);
  const API_URL = 'https://app.seda.de/api/v1';

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await axios.get(`${API_URL}/vacation/my-vacation`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setVacationData(response.data);
      } catch (error) {
        console.error('Fehler beim Laden der Urlaubsdaten:', error);
      }
    };
    fetchData();
  }, [token]);

  if (!vacationData) return <div>Lade Urlaubsdaten...</div>;

  return (
    <div style={{ padding: '24px' }}>
      <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '24px' }}>Mein Urlaub 2025</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div style={{ background: '#f0f9ff', padding: '16px', borderRadius: '12px' }}>
          <p style={{ color: '#666' }}>Urlaubsanspruch</p>
          <p style={{ fontSize: '28px', fontWeight: 'bold' }}>{vacationData.days_entitled} Tage</p>
        </div>
        <div style={{ background: '#fef2f2', padding: '16px', borderRadius: '12px' }}>
          <p style={{ color: '#666' }}>Genommen</p>
          <p style={{ fontSize: '28px', fontWeight: 'bold' }}>{vacationData.days_taken} Tage</p>
        </div>
        <div style={{ background: '#f0fdf4', padding: '16px', borderRadius: '12px' }}>
          <p style={{ color: '#666' }}>Resturlaub</p>
          <p style={{ fontSize: '28px', fontWeight: 'bold' }}>{vacationData.days_remaining} Tage</p>
        </div>
        <div style={{ background: '#fefce8', padding: '16px', borderRadius: '12px' }}>
          <p style={{ color: '#666' }}>Urlaubssatz</p>
          <p style={{ fontSize: '28px', fontWeight: 'bold' }}>{vacationData.vacation_rate?.toFixed(2)}€</p>
        </div>
      </div>
    </div>
  );
};

export default VacationTab;
