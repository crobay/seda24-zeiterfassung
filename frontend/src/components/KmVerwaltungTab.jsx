import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { TrendingUp, Edit2, Trash2, Save, X, Plus } from 'lucide-react';

const KmVerwaltungTab = ({ showToast }) => {
  const [distances, setDistances] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [objects, setObjects] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [showNewModal, setShowNewModal] = useState(false);
  const [newForm, setNewForm] = useState({ employee_id: '', object_id: '', distance_km: '' });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [distRes, empRes, objRes] = await Promise.all([
        api.get('/admin/km-distances/all'),
        api.get('/admin/employees-with-categories'),
        api.get('/admin/objects-list')
      ]);

      setDistances(distRes.data.sort((a, b) => a.personal_nr.localeCompare(b.personal_nr)));
      setEmployees(empRes.data);
      setObjects(objRes.data);
    } catch (error) {
      showToast('Fehler beim Laden', 'error');
    }
  };

  const getEmployeeName = (emp) => {
    if (emp.name) return `${emp.name} (${emp.personal_nr})`;
    return `${emp.first_name} ${emp.last_name} (${emp.personal_nr})`;
  };

  const startEdit = (distance) => {
    setEditingId(distance.id);
    setEditForm({
      employee_id: distance.employee_id,
      object_id: distance.object_id,
      distance_km: distance.distance_km
    });
  };

  const saveEdit = async (id) => {
    try {
      await api.put(`/admin/km-distances/${id}`, editForm);
      showToast('Gespeichert', 'success');
      setEditingId(null);
      loadData();
    } catch (error) {
      showToast('Fehler', 'error');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Wirklich löschen?')) return;
    try {
      await api.delete(`/admin/km-distances/${id}`);
      showToast('Gelöscht', 'success');
      loadData();
    } catch (error) {
      showToast('Fehler', 'error');
    }
  };

  const handleCreateNew = async () => {
    if (!newForm.employee_id || !newForm.object_id || !newForm.distance_km) {
      showToast('Alle Felder ausfüllen', 'error');
      return;
    }
    try {
      await api.post('/admin/km-distances', {
        employee_id: parseInt(newForm.employee_id),
        object_id: parseInt(newForm.object_id),
        distance_km: parseFloat(newForm.distance_km),
        rate_per_km: 0.30
      });
      showToast('Erstellt', 'success');
      setShowNewModal(false);
      setNewForm({ employee_id: '', object_id: '', distance_km: '' });
      loadData();
    } catch (error) {
      showToast('Fehler', 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div style={{background:'linear-gradient(135deg,#f97316 0%,#dc2626 100%)',borderRadius:'15px',padding:'30px',color:'white'}}>
        <h2 style={{fontSize:'28px',display:'flex',alignItems:'center',gap:'10px'}}><TrendingUp size={32}/>Standard-Kilometer verwalten</h2>
      </div>

      <div style={{background:'white',borderRadius:'15px',padding:'20px',boxShadow:'0 4px 15px rgba(0,0,0,0.1)',display:'flex',justifyContent:'space-between'}}>
        <div>Gesamt: <strong>{distances.length} Einträge</strong></div>
        <button onClick={()=>setShowNewModal(true)} style={{padding:'12px 24px',background:'#10b981',color:'white',border:'none',borderRadius:'8px',cursor:'pointer',display:'flex',gap:'8px',fontSize:'16px',fontWeight:'600'}}>
          <Plus size={20}/>Neuer Eintrag
        </button>
      </div>

      <div style={{background:'white',borderRadius:'15px',boxShadow:'0 4px 15px rgba(0,0,0,0.1)',overflow:'hidden'}}>
        <table style={{width:'100%',borderCollapse:'collapse'}}>
          <thead style={{background:'#f9fafb',borderBottom:'2px solid #e5e7eb'}}>
            <tr>
              <th style={{padding:'16px',textAlign:'left',fontWeight:'600'}}>Pers.Nr</th>
              <th style={{padding:'16px',textAlign:'left',fontWeight:'600'}}>Mitarbeiter</th>
              <th style={{padding:'16px',textAlign:'left',fontWeight:'600'}}>Objekt</th>
              <th style={{padding:'16px',textAlign:'left',fontWeight:'600'}}>Adresse</th>
              <th style={{padding:'16px',textAlign:'right',fontWeight:'600'}}>Entfernung</th>
              <th style={{padding:'16px',textAlign:'center',fontWeight:'600'}}>Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {distances.map(dist=>(
              <tr key={dist.id} style={{borderBottom:'1px solid #e5e7eb'}}>
                {editingId===dist.id?(
                  <>
                    <td style={{padding:'12px'}}>{dist.personal_nr}</td>
                    <td style={{padding:'12px'}}>
                      <select value={editForm.employee_id} onChange={e=>setEditForm({...editForm,employee_id:parseInt(e.target.value)})} style={{width:'100%',padding:'8px',border:'1px solid #ddd',borderRadius:'6px'}}>
                        {employees.filter(e => e.is_active !== false).map(emp=><option key={emp.id} value={emp.id}>{getEmployeeName(emp)}</option>)}
                      </select>
                    </td>
                    <td style={{padding:'12px'}}>
                      <select value={editForm.object_id} onChange={e=>setEditForm({...editForm,object_id:parseInt(e.target.value)})} style={{width:'100%',padding:'8px',border:'1px solid #ddd',borderRadius:'6px'}}>
                        {objects.filter(o => o.is_active !== false).map(obj=><option key={obj.id} value={obj.id}>{obj.name}</option>)}
                      </select>
                    </td>
                    <td style={{padding:'12px',fontSize:'13px',color:'#666'}}>{objects.find(o=>o.id===editForm.object_id)?.address}</td>
                    <td style={{padding:'12px',textAlign:'right'}}>
                      <input type="number" step="0.1" value={editForm.distance_km} onChange={e=>setEditForm({...editForm,distance_km:parseFloat(e.target.value)})} style={{width:'100px',padding:'8px',border:'1px solid #ddd',borderRadius:'6px',textAlign:'right'}}/>
                    </td>
                    <td style={{padding:'12px',textAlign:'center'}}>
                      <div style={{display:'flex',gap:'8px',justifyContent:'center'}}>
                        <button onClick={()=>saveEdit(dist.id)} style={{padding:'8px 12px',background:'#10b981',color:'white',border:'none',borderRadius:'6px',cursor:'pointer'}}><Save size={16}/></button>
                        <button onClick={()=>setEditingId(null)} style={{padding:'8px 12px',background:'#6b7280',color:'white',border:'none',borderRadius:'6px',cursor:'pointer'}}><X size={16}/></button>
                      </div>
                    </td>
                  </>
                ):(
                  <>
                    <td style={{padding:'12px',fontWeight:'600'}}>{dist.personal_nr}</td>
                    <td style={{padding:'12px'}}>{dist.employee_name}</td>
                    <td style={{padding:'12px',fontWeight:'500'}}>{dist.object_name}</td>
                    <td style={{padding:'12px',fontSize:'13px',color:'#666'}}>{dist.object_address}</td>
                    <td style={{padding:'12px',textAlign:'right',fontWeight:'600'}}>{dist.distance_km} km</td>
                    <td style={{padding:'12px',textAlign:'center'}}>
                      <div style={{display:'flex',gap:'8px',justifyContent:'center'}}>
                        <button onClick={()=>startEdit(dist)} style={{padding:'8px 16px',background:'#3b82f6',color:'white',border:'none',borderRadius:'6px',cursor:'pointer'}}><Edit2 size={16}/></button>
                        <button onClick={()=>handleDelete(dist.id)} style={{padding:'8px 16px',background:'#ef4444',color:'white',border:'none',borderRadius:'6px',cursor:'pointer'}}><Trash2 size={16}/></button>
                      </div>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showNewModal&&(
        <div style={{position:'fixed',top:0,left:0,right:0,bottom:0,background:'rgba(0,0,0,0.5)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000}}>
          <div style={{background:'white',borderRadius:'15px',padding:'30px',width:'500px',maxWidth:'90%'}}>
            <h3 style={{fontSize:'24px',marginBottom:'20px',fontWeight:'600'}}>Neuer KM-Eintrag</h3>
            <div style={{marginBottom:'20px'}}>
              <label style={{display:'block',marginBottom:'8px',fontWeight:'600'}}>Mitarbeiter</label>
              <select value={newForm.employee_id} onChange={e=>setNewForm({...newForm,employee_id:e.target.value})} style={{width:'100%',padding:'12px',border:'1px solid #ddd',borderRadius:'8px',fontSize:'16px'}}>
                <option value="">Bitte wählen...</option>
                {employees.filter(e => e.is_active !== false).map(emp=><option key={emp.id} value={emp.id}>{getEmployeeName(emp)}</option>)}
              </select>
            </div>
            <div style={{marginBottom:'20px'}}>
              <label style={{display:'block',marginBottom:'8px',fontWeight:'600'}}>Objekt</label>
              <select value={newForm.object_id} onChange={e=>setNewForm({...newForm,object_id:e.target.value})} style={{width:'100%',padding:'12px',border:'1px solid #ddd',borderRadius:'8px',fontSize:'16px'}}>
                <option value="">Bitte wählen...</option>
                {objects.filter(o => o.is_active !== false).map(obj=><option key={obj.id} value={obj.id}>{obj.name}</option>)}
              </select>
            </div>
            <div style={{marginBottom:'30px'}}>
              <label style={{display:'block',marginBottom:'8px',fontWeight:'600'}}>Entfernung (km)</label>
              <input type="number" step="0.1" value={newForm.distance_km} onChange={e=>setNewForm({...newForm,distance_km:e.target.value})} style={{width:'100%',padding:'12px',border:'1px solid #ddd',borderRadius:'8px',fontSize:'16px'}} placeholder="z.B. 15.5"/>
            </div>
            <div style={{display:'flex',gap:'12px'}}>
              <button onClick={()=>setShowNewModal(false)} style={{flex:1,padding:'12px',background:'#6b7280',color:'white',border:'none',borderRadius:'8px',cursor:'pointer',fontSize:'16px',fontWeight:'600'}}>Abbrechen</button>
              <button onClick={handleCreateNew} style={{flex:1,padding:'12px',background:'#10b981',color:'white',border:'none',borderRadius:'8px',cursor:'pointer',fontSize:'16px',fontWeight:'600'}}>Erstellen</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KmVerwaltungTab;
