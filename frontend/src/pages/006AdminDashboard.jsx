import React, { useState, useEffect } from 'react';
import { 
  Users, Building2, Calendar, Activity, FileText, Plus, Edit2, Trash2, 
  Save, X, Check, AlertCircle, LogOut, Search, Download, Upload,
  MapPin, Clock, Shield, Eye, EyeOff, ChevronDown, Filter, Settings
} from 'lucide-react';
import axios from 'axios';

const AdminDashboard = () => {
  const API_URL = 'https://192.168.178.87:8001/api/v1';
  const token = localStorage.getItem('token');
  
  const [activeTab, setActiveTab] = useState('overview');
  const [employees, setEmployees] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [customerHours, setCustomerHours] = useState([]);
  const [specialRules, setSpecialRules] = useState([]);
  const [liveStatus, setLiveStatus] = useState([]);
  const [toast, setToast] = useState(null);
  const [stats, setStats] = useState({
    active_employees: 0,
    paused_employees: 0,
    offline_employees: 0,
    total_employees: 0,
    total_hours_today: 0
  });

  const [editingHours, setEditingHours] = useState({});
  const [showSpecialRuleModal, setShowSpecialRuleModal] = useState(false);
  const [specialRuleForm, setSpecialRuleForm] = useState({
    employee_id: '',
    customer_id: '',
    special_hours: '',
    note: ''
  });

  useEffect(() => {
    fetchDashboardData();
    fetchEmployees();
    fetchCustomers();
    fetchCustomerHours();
    fetchSpecialRules();
  }, []);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchDashboardData = async () => {
    try {
      const statsResponse = await axios.get(`${API_URL}/admin/dashboard/stats`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setStats(statsResponse.data);
      
      const liveResponse = await axios.get(`${API_URL}/admin/live-status`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setLiveStatus(liveResponse.data);
    } catch (error) {
      console.error('Dashboard-Fehler:', error);
    }
  };

  const fetchEmployees = async () => {
    try {
      const response = await axios.get(`${API_URL}/employees`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const filtered = response.data.filter(emp => emp.employment_type !== 'admin');
      setEmployees(filtered);
    } catch (error) {
      console.error('Fehler beim Laden der Mitarbeiter:', error);
    }
  };

  const fetchCustomers = async () => {
    try {
      const response = await axios.get(`${API_URL}/customers`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setCustomers(response.data);
    } catch (error) {
      console.error('Fehler beim Laden der Kunden:', error);
    }
  };

  const fetchCustomerHours = async () => {
    try {
      const response = await axios.get(`${API_URL}/hours-management/customer-hours`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setCustomerHours(response.data);
    } catch (error) {
      console.error('Fehler beim Laden der Sollstunden:', error);
    }
  };

  const fetchSpecialRules = async () => {
    try {
      const response = await axios.get(`${API_URL}/hours-management/special-rules`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSpecialRules(response.data);
    } catch (error) {
      console.error('Fehler beim Laden der Spezialregeln:', error);
    }
  };

  const updateCustomerHours = async (customerId, hours) => {
    try {
      await axios.put(
        `${API_URL}/hours-management/customer-hours`,
        { customer_id: customerId, default_hours: parseFloat(hours) },
        { headers: { Authorization: `Bearer ${token}` }}
      );
      showToast('Sollstunden aktualisiert', 'success');
      fetchCustomerHours();
    } catch (error) {
      showToast('Fehler beim Speichern', 'error');
    }
  };

  const createSpecialRule = async () => {
    try {
      await axios.post(
        `${API_URL}/hours-management/special-rules`,
        {
          ...specialRuleForm,
          special_hours: parseFloat(specialRuleForm.special_hours)
        },
        { headers: { Authorization: `Bearer ${token}` }}
      );
      showToast('Spezialregel gespeichert', 'success');
      setShowSpecialRuleModal(false);
      setSpecialRuleForm({
        employee_id: '',
        customer_id: '',
        special_hours: '',
        note: ''
      });
      fetchSpecialRules();
    } catch (error) {
      showToast('Fehler beim Speichern', 'error');
    }
  };

  const deleteSpecialRule = async (ruleId) => {
    if (confirm('Spezialregel wirklich loeschen?')) {
      try {
        await axios.delete(
          `${API_URL}/hours-management/special-rules/${ruleId}`,
          { headers: { Authorization: `Bearer ${token}` }}
        );
        showToast('Regel geloescht', 'success');
        fetchSpecialRules();
      } catch (error) {
        showToast('Fehler beim Loeschen', 'error');
      }
    }
  };

  // Tab Components
  const OverviewTab = () => (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-600">Aktive Mitarbeiter</p>
          <p className="text-2xl font-bold text-green-600">{stats.active_employees}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-600">Gesamt Mitarbeiter</p>
          <p className="text-2xl font-bold">{stats.total_employees}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-600">Stunden heute</p>
          <p className="text-2xl font-bold text-blue-600">{stats.total_hours_today}h</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-600">Offline</p>
          <p className="text-2xl font-bold text-gray-600">{stats.offline_employees}</p>
        </div>
      </div>
    </div>
  );

  const EmployeesTab = () => (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-4">Mitarbeiter</h2>
      <div className="space-y-2">
        {employees.map(emp => (
          <div key={emp.id} className="p-3 border rounded flex justify-between">
            <span>{emp.first_name} {emp.last_name}</span>
            <span className="text-gray-500">{emp.personal_nr}</span>
          </div>
        ))}
      </div>
    </div>
  );

  const CustomersTab = () => (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-4">Kunden</h2>
      <div className="space-y-2">
        {customers.map(cust => (
          <div key={cust.id} className="p-3 border rounded">
            <div className="font-medium">{cust.name}</div>
            <div className="text-sm text-gray-600">{cust.address}</div>
          </div>
        ))}
      </div>
    </div>
  );

  const HoursManagementTab = () => (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold">Standard-Sollstunden pro Kunde</h2>
          <p className="text-sm text-gray-600 mt-1">
            Definieren Sie die Standard-Arbeitszeit fuer jeden Kunden
          </p>
        </div>
        
        <div className="p-6">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Kunde</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Sollstunden</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {customerHours.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{item.name}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-center">
                    <input
                      type="number"
                      step="0.5"
                      value={editingHours[item.id] ?? item.hours}
                      onChange={(e) => setEditingHours({...editingHours, [item.id]: e.target.value})}
                      className="w-20 px-2 py-1 text-center border rounded"
                    />
                    <span className="ml-2 text-gray-500">Stunden</span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-center">
                    <button
                      onClick={() => {
                        updateCustomerHours(item.id, editingHours[item.id] || item.hours);
                        setEditingHours({...editingHours, [item.id]: undefined});
                      }}
                      className="text-blue-600 hover:text-blue-900"
                    >
                      <Save size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-xl font-bold">Spezialregeln (Abweichungen)</h2>
              <p className="text-sm text-gray-600 mt-1">
                z.B. Eldina bei Lidl nur 4h statt 5h
              </p>
            </div>
            <button
              onClick={() => setShowSpecialRuleModal(true)}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
            >
              <Plus size={20} />
              Neue Regel
            </button>
          </div>
        </div>
        
        <div className="p-6">
          {specialRules.length === 0 ? (
            <p className="text-gray-500 text-center py-8">Keine Spezialregeln definiert</p>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Mitarbeiter</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Kunde</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Standard</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Spezial</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notiz</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Aktion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {specialRules.map((rule) => (
                  <tr key={rule.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm">{rule.employee_name}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">{rule.customer_name}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-center text-sm">
                      {rule.standard_hours}h
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-center">
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-sm font-medium">
                        {rule.special_hours}h
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{rule.note}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-center">
                      <button
                        onClick={() => deleteSpecialRule(rule.id)}
                        className="text-red-600 hover:text-red-900"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );

  const ScheduleTab = () => (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-4">Dienstplan</h2>
      <p className="text-gray-600">Dienstplan-Verwaltung kommt noch...</p>
    </div>
  );

  const LiveTab = () => (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-4">Live Status</h2>
      {liveStatus.length === 0 ? (
        <p className="text-gray-600">Momentan niemand eingestempelt</p>
      ) : (
        <div className="space-y-2">
          {liveStatus.map((status, idx) => (
            <div key={idx} className="p-3 border rounded">
              {status.employee_name} - {status.object_name}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const ReportsTab = () => (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-4">Berichte</h2>
      <p className="text-gray-600">Berichte-Funktionen kommen noch...</p>
    </div>
  );

  const tabs = [
    { id: 'overview', label: 'Uebersicht', icon: Activity },
    { id: 'employees', label: 'Mitarbeiter', icon: Users },
    { id: 'customers', label: 'Kunden', icon: Building2 },
    { id: 'hours', label: 'Sollstunden', icon: Clock },
    { id: 'schedule', label: 'Dienstplan', icon: Calendar },
    { id: 'live', label: 'Live', icon: MapPin },
    { id: 'reports', label: 'Berichte', icon: FileText }
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <h1 className="text-2xl font-bold text-gray-900">SEDA24 Admin</h1>
            <button
              onClick={() => {
                localStorage.clear();
                window.location.href = '/login';
              }}
              className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600"
            >
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-8">
            {tabs.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors
                    ${activeTab === tab.id 
                      ? 'border-blue-500 text-blue-600' 
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }
                  `}
                >
                  <Icon size={20} />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && <OverviewTab />}
        {activeTab === 'employees' && <EmployeesTab />}
        {activeTab === 'customers' && <CustomersTab />}
        {activeTab === 'hours' && <HoursManagementTab />}
        {activeTab === 'schedule' && <ScheduleTab />}
        {activeTab === 'live' && <LiveTab />}
        {activeTab === 'reports' && <ReportsTab />}
      </div>

      {showSpecialRuleModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">Neue Spezialregel</h3>
            <div className="space-y-4">
              <select
                value={specialRuleForm.employee_id}
                onChange={(e) => setSpecialRuleForm({...specialRuleForm, employee_id: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="">Mitarbeiter waehlen...</option>
                {employees.map(emp => (
                  <option key={emp.id} value={emp.id}>
                    {emp.first_name} {emp.last_name}
                  </option>
                ))}
              </select>
              
              <select
                value={specialRuleForm.customer_id}
                onChange={(e) => setSpecialRuleForm({...specialRuleForm, customer_id: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="">Kunde waehlen...</option>
                {customers.map(cust => (
                  <option key={cust.id} value={cust.id}>{cust.name}</option>
                ))}
              </select>
              
              <input
                type="number"
                step="0.5"
                placeholder="Spezial-Stunden (z.B. 4.0)"
                value={specialRuleForm.special_hours}
                onChange={(e) => setSpecialRuleForm({...specialRuleForm, special_hours: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg"
              />
              
              <textarea
                placeholder="Begruendung (z.B. 'Eldina bei Lidl nur 4h statt 5h')"
                value={specialRuleForm.note}
                onChange={(e) => setSpecialRuleForm({...specialRuleForm, note: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg"
                rows="3"
              />
            </div>
            
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowSpecialRuleModal(false)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Abbrechen
              </button>
              <button
                onClick={createSpecialRule}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 z-50
          ${toast.type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'}`}>
          {toast.message}
        </div>
      )}
    </div>
  );
};

export default AdminDashboard;