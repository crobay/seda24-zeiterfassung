/**
 * Notification-Service fuer SEDA24 V3.0
 * Push entfernt - nur noch API-Abfragen fuer offene Bestaetigungen.
 */
import { API_URL } from '../config.js';

export async function getPendingNotifications() {
  const token = localStorage.getItem('token') || sessionStorage.getItem('token');
  if (!token) return [];

  try {
    const response = await fetch(`${API_URL}/push/pending`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    if (response.ok) {
      return await response.json();
    }
  } catch (error) {
    console.error('Pending Notifications Fehler:', error);
  }
  return [];
}

export async function respondToNotification(notificationId, responseType, data = {}) {
  const token = localStorage.getItem('token') || sessionStorage.getItem('token');
  const response = await fetch(`${API_URL}/push/respond/${notificationId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      response: responseType,
      ...data
    })
  });

  if (response.ok) {
    return await response.json();
  }
  throw new Error('Response fehlgeschlagen');
}
