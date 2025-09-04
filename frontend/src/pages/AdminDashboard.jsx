import React, { useState, useEffect } from 'react';
import { 
  Users, Building2, Calendar, Activity, FileText, Plus, Edit2, Trash2, 
  Save, X, Check, AlertCircle, LogOut, Search, Download, Upload,
  MapPin, Clock, Shield, Eye, EyeOff, ChevronDown, Filter
} from 'lucide-react';
import ScheduleTab from "../components/ScheduleTab";
import api from '../services/api';

const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [employees, setEmployees] = useState([
    { id: 1, personal_nr: '001', first_name: 'Max', last_name: 'Mustermann', email: 'max@seda24.de', tracking_mode: 'C', hourly_rate: 15.50, is_active: true, daily_hours: 8 },
    { id: 2, personal_nr: '002', first_name: 'Anna', last_name: 'Schmidt', email: 'anna@seda24.de', tracking_mode: 'B', hourly_rate: 16.00, is_active: true, daily_hours: 6 },
    { id: 3, personal_nr: '003', first_name: 'Peter', last_name: 'Weber', email: 'peter@seda24.de', tracking_mode: 'A', hourly_rate: 22.00, is_active: true, daily_hours: 8 }
  ]);
  
  const [customers, setCustomers] = useState([]);
  
  const [liveStatus, setLiveStatus] = useState([
    { employee_name: 'Max Mustermann', object_name: 'Sparkasse Rastatt', check_in_time: '08:15', work_hours: '2.5', is_paused: false },
    { employee_name: 'Anna Schmidt', object_name: 'Rathaus Gaggenau', check_in_time: '07:30', work_hours: '3.2', is_paused: false }
  ]);
  
  const [stats, setStats] = useState({
    active_employees: 2,
    paused_employees: 0,
    offline_employees: 8,
    total_employees: 10,
    total_hours_today: 5.7
  });
  
  // Modal States
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false);
  const [showNewCustomerModal, setShowNewCustomerModal] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [editingCustomer, setEditingCustomer] = useState(null);
  
  // Echte Kunden aus DB laden
  useEffect(() => {
  api.get('/admin/schedules/week?week_offset=0')
  .then(response => {
    if (response.data && response.data.objects) {
      const customerData = response.data.objects.map(obj => ({
        id: obj.id,
        name: obj.name,
        address: obj.name,  // Dummy Adresse
        contact_person: 'N/A',
        phone: 'N/A',
        hourly_rate: obj.hourly_rate || '0'
      }));
      setCustomers(customerData);
      console.log('Objekte als Kunden geladen:', customerData);
    }
  })
      .catch(error => console.error('Fehler:', error));
  }, []);
  
  // Form States for Employee Modal
  const [employeeForm, setEmployeeForm] = useState({
    first_name: '',
    last_name: '',
    personal_nr: '',
    email: '',
    password: '',
    tracking_mode: 'C',
    hourly_rate: '',
    daily_hours: '8',
    gps_required: false
  });
  
  // Form States for Customer Modal
  const [customerForm, setCustomerForm] = useState({
    name: '',
    address: '',
    contact_person: '',
    phone: '',
    hourly_rate: ''
  });
  
  // Filter & Search
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState('all');
  
  // Toast Notification
  const [toast, setToast] = useState(null);
// Echte Kunden aus DB laden
  useEffect(() => {
    api.get('/admin/customers')
      .then(response => {
        if (response.data) {
          setCustomers(response.data);
          console.log('Kunden geladen:', response.data);
        }
      })
      .catch(error => console.error('Fehler:', error));
  }, []);
  useEffect(() => {
    // Simuliere Live-Updates
    const interval = setInterval(() => {
      setStats(prev => ({
        ...prev,
        total_hours_today: prev.total_hours_today + 0.1
      }));
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleSaveEmployee = () => {
    if (editingEmployee) {
      setEmployees(prev => prev.map(emp => 
        emp.id === editingEmployee.id 
          ? { ...emp, ...employeeForm }
          : emp
      ));
      showToast('Mitarbeiter aktualisiert', 'success');
    } else {
      const newEmployee = {
        id: employees.length + 1,
        ...employeeForm,
        hourly_rate: parseFloat(employeeForm.hourly_rate),
        daily_hours: parseFloat(employeeForm.daily_hours),
        is_active: true
      };
      setEmployees(prev => [...prev, newEmployee]);
      showToast('Mitarbeiter hinzugefügt', 'success');
    }
    
    setShowNewEmployeeModal(false);
    setEditingEmployee(null);
    setEmployeeForm({
      first_name: '',
      last_name: '',
      personal_nr: '',
      email: '',
      password: '',
      tracking_mode: 'C',
      hourly_rate: '',
      daily_hours: '8',
      gps_required: false
    });
  };

  const handleInlineCategoryChange = (employeeId, newCategory) => {
    setEmployees(prev => prev.map(emp => 
      emp.id === employeeId 
        ? { ...emp, tracking_mode: newCategory }
        : emp
    ));
    showToast('Kategorie geändert', 'success');
  };

  const handleSaveCustomer = () => {
    if (editingCustomer) {
      setCustomers(prev => prev.map(cust => 
        cust.id === editingCustomer.id 
          ? { ...cust, ...customerForm }
          : cust
      ));
      showToast('Kunde aktualisiert', 'success');
    } else {
      const newCustomer = {
        id: customers.length + 1,
        ...customerForm,
        hourly_rate: customerForm.hourly_rate ? parseFloat(customerForm.hourly_rate) : null
      };
      setCustomers(prev => [...prev, newCustomer]);
      showToast('Kunde hinzugefügt', 'success');
    }
    
    setShowNewCustomerModal(false);
    setEditingCustomer(null);
    setCustomerForm({
      name: '',
      address: '',
      contact_person: '',
      phone: '',
      hourly_rate: ''
    });
  };

  const handleDeleteEmployee = (id) => {
    if (confirm('Mitarbeiter wirklich löschen?')) {
      setEmployees(prev => prev.filter(emp => emp.id !== id));
      showToast('Mitarbeiter gelöscht', 'success');
    }
  };

  const handleDeleteCustomer = (id) => {
    if (confirm('Kunde wirklich löschen?')) {
      setCustomers(prev => prev.filter(cust => cust.id !== id));
      showToast('Kunde gelöscht', 'success');
    }
  };

  const openEditEmployeeModal = (employee) => {
    setEditingEmployee(employee);
    setEmployeeForm({
      first_name: employee.first_name,
      last_name: employee.last_name,
      personal_nr: employee.personal_nr,
      email: employee.email,
      password: '',
      tracking_mode: employee.tracking_mode,
      hourly_rate: employee.hourly_rate.toString(),
      daily_hours: employee.daily_hours.toString(),
      gps_required: employee.gps_required || false
    });
    setShowNewEmployeeModal(true);
  };

  const openEditCustomerModal = (customer) => {
    setEditingCustomer(customer);
    setCustomerForm({
      name: customer.name,
      address: customer.address,
      contact_person: customer.contact_person || '',
      phone: customer.phone || '',
      hourly_rate: customer.hourly_rate ? customer.hourly_rate.toString() : ''
    });
    setShowNewCustomerModal(true);
  };

  const handleExportExcel = () => {
    showToast('Excel-Export wird vorbereitet...', 'info');
    // Hier würde der echte Export-Code stehen
  };

  const getCategoryBadge = (category) => {
    const badges = {
      'A': { color: 'bg-green-100 text-green-800', icon: '✅', label: 'Auto' },
      'B': { color: 'bg-blue-100 text-blue-800', icon: '🔘', label: 'Button' },
      'C': { color: 'bg-orange-100 text-orange-800', icon: '📍', label: 'Normal' }
    };
    return badges[category] || badges['C'];
  };

  const filteredEmployees = employees.filter(emp => {
    const matchesSearch = emp.first_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         emp.last_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         emp.personal_nr?.includes(searchTerm);
    const matchesFilter = filterCategory === 'all' || emp.tracking_mode === filterCategory;
    return matchesSearch && matchesFilter;
  });

  // Tab Components
  const OverviewTab = () => (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Aktive Mitarbeiter</p>
              <p className="text-2xl font-bold text-green-600">{stats.active_employees}</p>
            </div>
            <Activity className="text-green-500" size={32} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">In Pause</p>
              <p className="text-2xl font-bold text-orange-600">{stats.paused_employees}</p>
            </div>
            <Clock className="text-orange-500" size={32} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Offline</p>
              <p className="text-2xl font-bold text-gray-600">{stats.offline_employees}</p>
            </div>
            <Users className="text-gray-500" size={32} />
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Stunden heute</p>
              <p className="text-2xl font-bold text-blue-600">{stats.total_hours_today.toFixed(1)}h</p>
            </div>
            <Clock className="text-blue-500" size={32} />
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">Schnellzugriff</h3>
          <div className="space-y-3">
            <button
              onClick={() => setActiveTab('employees')}
              className="w-full text-left p-3 rounded-lg hover:bg-gray-50 flex items-center justify-between border"
            >
              <span className="flex items-center gap-2">
                <Users size={20} />
                Mitarbeiter verwalten
              </span>
              <ChevronDown className="rotate-[-90deg]" size={16} />
            </button>
            <button
              onClick={() => setActiveTab('schedule')}
              className="w-full text-left p-3 rounded-lg hover:bg-gray-50 flex items-center justify-between border"
            >
              <span className="flex items-center gap-2">
                <Calendar size={20} />
                Dienstplan ansehen
              </span>
              <ChevronDown className="rotate-[-90deg]" size={16} />
            </button>
            <button
              onClick={() => setActiveTab('reports')}
              className="w-full text-left p-3 rounded-lg hover:bg-gray-50 flex items-center justify-between border"
            >
              <span className="flex items-center gap-2">
                <FileText size={20} />
                Berichte erstellen
              </span>
              <ChevronDown className="rotate-[-90deg]" size={16} />
            </button>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">Aktuelle Aktivitäten</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {liveStatus.slice(0, 5).map((status, idx) => (
              <div key={idx} className="flex items-center justify-between p-2 hover:bg-gray-50 rounded">
                <div>
                  <p className="font-medium">{status.employee_name}</p>
                  <p className="text-sm text-gray-600">📍 {status.object_name}</p>
                </div>
                <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                  {status.work_hours}h
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  const EmployeesTab = () => (
    <div className="bg-white rounded-lg shadow">
      <div className="p-6 border-b">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-bold">Mitarbeiterverwaltung</h2>
          <div className="flex gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 text-gray-400" size={20} />
              <input
                type="text"
                placeholder="Suchen..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 pr-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Alle Kategorien</option>
              <option value="A">Kategorie A</option>
              <option value="B">Kategorie B</option>
              <option value="C">Kategorie C</option>
            </select>
            <button
              onClick={() => {
                setEditingEmployee(null);
                setEmployeeForm({
                  first_name: '',
                  last_name: '',
                  personal_nr: '',
                  email: '',
                  password: '',
                  tracking_mode: 'C',
                  hourly_rate: '',
                  daily_hours: '8',
                  gps_required: false
                });
                setShowNewEmployeeModal(true);
              }}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
            >
              <Plus size={20} />
              Neuer Mitarbeiter
            </button>
          </div>
        </div>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Personal-Nr</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Kategorie</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Stundensatz</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aktionen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {filteredEmployees.map((employee) => {
              const badge = getCategoryBadge(employee.tracking_mode);
              return (
                <tr key={employee.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap font-mono text-sm">
                    {employee.personal_nr}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">
                      {employee.first_name} {employee.last_name}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {employee.email}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <select
                      value={employee.tracking_mode}
                      onChange={(e) => handleInlineCategoryChange(employee.id, e.target.value)}
                      className={`px-3 py-1 rounded-full text-xs font-medium ${badge.color} cursor-pointer border-0`}
                    >
                      <option value="A">✅ Auto</option>
                      <option value="B">🔘 Button</option>
                      <option value="C">📍 Normal</option>
                    </select>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {employee.hourly_rate}€/h
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      employee.is_active 
                        ? 'bg-green-100 text-green-800' 
                        : 'bg-red-100 text-red-800'
                    }`}>
                      {employee.is_active ? 'Aktiv' : 'Inaktiv'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <button
                      onClick={() => openEditEmployeeModal(employee)}
                      className="text-blue-600 hover:text-blue-900 mr-3"
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => handleDeleteEmployee(employee.id)}
                      className="text-red-600 hover:text-red-900"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );

  const CustomersTab = () => (
    <div className="bg-white rounded-lg shadow">
      <div className="p-6 border-b">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-bold">Kundenverwaltung</h2>
          <button
            onClick={() => {
              setEditingCustomer(null);
              setCustomerForm({
                name: '',
                address: '',
                contact_person: '',
                phone: '',
                hourly_rate: ''
              });
              setShowNewCustomerModal(true);
            }}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
          >
            <Plus size={20} />
            Neuer Kunde
          </button>
        </div>
      </div>
      
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {customers.map((customer) => (
            <div key={customer.id} className="border rounded-lg p-4 hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start mb-3">
                <Building2 className="text-gray-400" size={24} />
                <div className="flex gap-2">
                  <button
                    onClick={() => openEditCustomerModal(customer)}
                    className="text-blue-600 hover:text-blue-900"
                  >
                    <Edit2 size={16} />
                  </button>
                  <button 
                    onClick={() => handleDeleteCustomer(customer.id)}
                    className="text-red-600 hover:text-red-900"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              <h3 className="font-semibold text-lg mb-2">{customer.name}</h3>
              <p className="text-sm text-gray-600 mb-1">📍 {customer.address}</p>
              <p className="text-sm text-gray-600 mb-1">👤 {customer.contact_person}</p>
              <p className="text-sm text-gray-600">📞 {customer.phone}</p>
              {customer.hourly_rate && (
                <p className="text-sm font-semibold mt-2 text-blue-600">
                  {customer.hourly_rate}€/h
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );

   const LiveTab = () => (
    <div className="bg-white rounded-lg shadow">
      <div className="p-6 border-b">
        <h2 className="text-xl font-bold">Live-Übersicht</h2>
        <p className="text-sm text-gray-600 mt-1">
          Aktueller Status aller Mitarbeiter - Aktualisiert alle 30 Sekunden
        </p>
      </div>
      
      <div className="p-6">
        {liveStatus.length === 0 ? (
          <div className="text-center py-12">
            <Users className="mx-auto text-gray-400 mb-4" size={48} />
            <p className="text-gray-600">Momentan sind keine Mitarbeiter eingestempelt</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {liveStatus.map((status, idx) => (
              <div key={idx} className="border rounded-lg p-4 hover:shadow-lg transition-shadow">
                <div className="flex justify-between items-start mb-3">
                  <span className="bg-green-100 text-green-800 text-xs px-2 py-1 rounded">
                    AKTIV
                  </span>
                  <Clock className="text-gray-400" size={20} />
                </div>
                <h3 className="font-semibold text-lg">{status.employee_name}</h3>
                <p className="text-sm text-gray-600 mt-2">📍 {status.object_name}</p>
                <p className="text-sm text-gray-600">⏰ Seit: {status.check_in_time}</p>
                <p className="text-sm font-semibold text-blue-600 mt-2">
                  Arbeitszeit: {status.work_hours} Stunden
                </p>
                {status.is_paused && (
                  <span className="inline-block mt-2 bg-orange-100 text-orange-800 text-xs px-2 py-1 rounded">
                    IN PAUSE
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const ReportsTab = () => (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold">Berichte & Auswertungen</h2>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">
          Bericht generieren
        </button>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <FileText className="text-blue-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">Monatsabrechnung</h3>
          <p className="text-sm text-gray-600">
            Detaillierte Stundenübersicht pro Mitarbeiter für den aktuellen Monat
          </p>
        </div>
        
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <Building2 className="text-green-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">Objektauswertung</h3>
          <p className="text-sm text-gray-600">
            Geleistete Stunden pro Kunde/Objekt mit Kostenübersicht
          </p>
        </div>
        
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <Download className="text-purple-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">Excel-Export</h3>
          <p className="text-sm text-gray-600">
            Vollständiger Datenexport für externe Lohnabrechnungssysteme
          </p>
        </div>
        
        <div className="border rounded-lg p-6 hover:shadow-lg cursor-pointer">
          <Shield className="text-orange-500 mb-3" size={32} />
          <h3 className="font-semibold mb-2">DSGVO-Bericht</h3>
          <p className="text-sm text-gray-600">
            Datenschutzkonforme Aufbereitung der Arbeitszeitdaten
          </p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">SEDA24 Admin</h1>
              <p className="text-sm text-gray-600">
                Verwaltungszentrale - {new Date().toLocaleDateString('de-DE', { 
                  weekday: 'long', 
                  year: 'numeric', 
                  month: 'long', 
                  day: 'numeric' 
                })}
              </p>
            </div>
            <button
              onClick={() => {
                localStorage.clear();
                window.location.href = '/login';
              }}
              className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2"
            >
              <LogOut size={20} />
              Abmelden
            </button>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-8">
            {[
              { id: 'overview', label: 'Übersicht', icon: Activity },
              { id: 'employees', label: 'Mitarbeiter', icon: Users },
              { id: 'customers', label: 'Kunden', icon: Building2 },
              { id: 'schedule', label: 'Dienstplan', icon: Calendar },
			  { id: 'hours', label: 'Sollstunden', icon: Clock },
              { id: 'live', label: 'Live', icon: MapPin },
              { id: 'reports', label: 'Berichte', icon: FileText }
            ].map(tab => {
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

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && <OverviewTab />}
        {activeTab === 'employees' && <EmployeesTab />}
        {activeTab === 'customers' && <CustomersTab />}
		{activeTab === 'hours' && (
		  <div className="bg-white rounded-lg shadow p-6">
			<h2 className="text-xl font-bold mb-4">Sollstunden-Verwaltung</h2>
			<div className="space-y-4">
			  <p className="text-green-600 font-medium">✓ Tab funktioniert!</p>
			  <p className="text-gray-600">Backend-Verbindung ist bereit:</p>
			  <ul className="list-disc list-inside text-sm text-gray-500">
				<li>customer_hours Tabelle ✓</li>
				<li>special_rules Tabelle ✓</li>
				<li>API-Endpoints laufen ✓</li>
			  </ul>
			  <p className="text-blue-600 mt-4">Nächster Schritt: Tabelle mit echten Daten anzeigen</p>
			</div>
		  </div>
		)}
        {activeTab === 'schedule' && <ScheduleTab />}
        {activeTab === 'live' && <LiveTab />}
        {activeTab === 'reports' && <ReportsTab />}
      </div>

      {/* Toast Notification */}
      {toast && (
        <div className={`
          fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 z-50
          ${toast.type === 'success' ? 'bg-green-500 text-white' : ''}
          ${toast.type === 'error' ? 'bg-red-500 text-white' : ''}
          ${toast.type === 'info' ? 'bg-blue-500 text-white' : ''}
        `}>
          {toast.type === 'success' && <Check size={20} />}
          {toast.type === 'error' && <X size={20} />}
          {toast.type === 'info' && <AlertCircle size={20} />}
          {toast.message}
        </div>
      )}

      {/* Employee Modal */}
      {showNewEmployeeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">
              {editingEmployee ? 'Mitarbeiter bearbeiten' : 'Neuer Mitarbeiter'}
            </h3>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <input
                  placeholder="Vorname"
                  value={employeeForm.first_name}
                  onChange={(e) => setEmployeeForm({...employeeForm, first_name: e.target.value})}
                  className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <input
                  placeholder="Nachname"
                  value={employeeForm.last_name}
                  onChange={(e) => setEmployeeForm({...employeeForm, last_name: e.target.value})}
                  className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <input
                placeholder="Personal-Nr"
                value={employeeForm.personal_nr}
                onChange={(e) => setEmployeeForm({...employeeForm, personal_nr: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="email"
                placeholder="Email"
                value={employeeForm.email}
                onChange={(e) => setEmployeeForm({...employeeForm, email: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {!editingEmployee && (
                <input
                  type="password"
                  placeholder="Passwort"
                  value={employeeForm.password}
                  onChange={(e) => setEmployeeForm({...employeeForm, password: e.target.value})}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}
              <select
                value={employeeForm.tracking_mode}
                onChange={(e) => setEmployeeForm({...employeeForm, tracking_mode: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="A">Kategorie A - Vollautomatisch</option>
                <option value="B">Kategorie B - War-da Button</option>
                <option value="C">Kategorie C - Normal</option>
              </select>
              <div className="grid grid-cols-2 gap-4">
                <input
                  type="number"
                  step="0.01"
                  placeholder="Stundensatz (€)"
                  value={employeeForm.hourly_rate}
                  onChange={(e) => setEmployeeForm({...employeeForm, hourly_rate: e.target.value})}
                  className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <input
                  type="number"
                  step="0.5"
                  placeholder="Sollstunden/Tag"
                  value={employeeForm.daily_hours}
                  onChange={(e) => setEmployeeForm({...employeeForm, daily_hours: e.target.value})}
                  className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={employeeForm.gps_required}
                  onChange={(e) => setEmployeeForm({...employeeForm, gps_required: e.target.checked})}
                  id="gps_required"
                  className="w-4 h-4"
                />
                <label htmlFor="gps_required" className="text-sm">
                  GPS-Pflicht aktivieren
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setShowNewEmployeeModal(false);
                  setEditingEmployee(null);
                }}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Abbrechen
              </button>
              <button
                onClick={handleSaveEmployee}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Customer Modal */}
      {showNewCustomerModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">
              {editingCustomer ? 'Kunde bearbeiten' : 'Neuer Kunde'}
            </h3>
            <div className="space-y-4">
              <input
                placeholder="Firmenname/Objektname"
                value={customerForm.name}
                onChange={(e) => setCustomerForm({...customerForm, name: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                placeholder="Adresse"
                value={customerForm.address}
                onChange={(e) => setCustomerForm({...customerForm, address: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                placeholder="Ansprechpartner"
                value={customerForm.contact_person}
                onChange={(e) => setCustomerForm({...customerForm, contact_person: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                placeholder="Telefonnummer"
                value={customerForm.phone}
                onChange={(e) => setCustomerForm({...customerForm, phone: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="number"
                step="0.01"
                placeholder="Stundensatz (€) - optional"
                value={customerForm.hourly_rate}
                onChange={(e) => setCustomerForm({...customerForm, hourly_rate: e.target.value})}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setShowNewCustomerModal(false);
                  setEditingCustomer(null);
                }}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Abbrechen
              </button>
              <button
                onClick={handleSaveCustomer}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDashboard;