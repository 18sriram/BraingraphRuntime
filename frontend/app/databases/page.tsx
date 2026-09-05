'use client';

import { FormEvent, useEffect, useState } from 'react';
import '../../styles/database-management.css';

type Database = { id: number; name: string; host: string; bolt_port: number; username: string; default_database: string; is_active: boolean };
type Workspace = { id: number; name: string; project_path: string; database_id: number; brain_version: string };
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Request failed');
  return response.status === 204 ? (undefined as T) : response.json();
}

export default function DatabasesPage() {
  const [databases, setDatabases] = useState<Database[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [notice, setNotice] = useState('');
  const [form, setForm] = useState({ name: '', host: 'localhost', bolt_port: '7687', username: 'neo4j', password: '', default_database: 'neo4j' });

  const refresh = async () => {
    const [nextDatabases, workspaces] = await Promise.all([api<Database[]>('/api/databases'), api<Workspace[]>('/api/workspaces')]);
    setDatabases(nextDatabases);
    setWorkspace(workspaces[0] || null);
  };
  useEffect(() => { refresh().catch((error) => setNotice(error.message)); }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const payload = { ...form, bolt_port: Number(form.bolt_port), ...(form.password ? {} : { password: undefined }) };
      if (editing) await api(`/api/databases/${editing}`, { method: 'PUT', body: JSON.stringify(payload) });
      else await api('/api/databases', { method: 'POST', body: JSON.stringify(payload) });
      setNotice(editing ? 'Database updated' : 'Database added'); setEditing(null); setForm({ name: '', host: 'localhost', bolt_port: '7687', username: 'neo4j', password: '', default_database: 'neo4j' }); await refresh();
    } catch (error) { setNotice((error as Error).message); }
  };

  const test = async (id: number) => { try { const result = await api<{ connected: boolean }>(`/api/databases/${id}/test`, { method: 'POST' }); setNotice(result.connected ? 'Connection verified' : 'Connection failed'); } catch (error) { setNotice((error as Error).message); } };
  const activate = async (id: number) => { if (!workspace) return; try { await api(`/api/workspaces/${workspace.id}/database`, { method: 'POST', body: JSON.stringify({ database_id: id, move_existing_graph: false }) }); setNotice('Workspace database switched'); await refresh(); } catch (error) { setNotice((error as Error).message); } };
  const remove = async (id: number) => { if (!window.confirm('Delete this database registration?')) return; try { await api(`/api/databases/${id}`, { method: 'DELETE' }); await refresh(); setNotice('Database deleted'); } catch (error) { setNotice((error as Error).message); } };
  const beginEdit = (database: Database) => { setEditing(database.id); setForm({ name: database.name, host: database.host, bolt_port: String(database.bolt_port), username: database.username, password: '', default_database: database.default_database }); };

  return <main className="database-page">
    <header className="database-header"><div><p className="kicker">BrainGraph / infrastructure</p><h1>Database management</h1><p>Keep each project connected to the graph that belongs to it.</p></div><a href="/">Back to dashboard</a></header>
    {notice && <div className="notice" role="status">{notice}</div>}
    <section className="workspace-panel"><div><span className="kicker">Current workspace</span><h2>{workspace?.name || 'No workspace loaded'}</h2><p>{workspace?.project_path || 'Register a workspace with bg init to begin.'}</p></div><dl><div><dt>Database</dt><dd>{databases.find((item) => item.id === workspace?.database_id)?.name || '—'}</dd></div><div><dt>Brain version</dt><dd>{workspace?.brain_version || '—'}</dd></div></dl></section>
    <div className="database-layout"><section className="database-list"><div className="section-heading"><div><span className="kicker">Connections</span><h2>Registered databases</h2></div><span>{databases.length} total</span></div>{databases.map((database) => <article className={`database-row ${database.is_active ? 'active-row' : ''}`} key={database.id}><div className="database-main"><div className="database-title"><h3>{database.name}</h3>{database.is_active && <b className="active-badge">ACTIVE</b>}</div><p>{database.host}:{database.bolt_port} · {database.username} · {database.default_database}</p></div><div className="row-actions"><button onClick={() => test(database.id)}>Test</button><button onClick={() => activate(database.id)} disabled={database.is_active || !workspace}>Use</button><button onClick={() => beginEdit(database)}>Edit</button><button className="danger" onClick={() => remove(database.id)}>Delete</button></div></article>)}</section>
      <section className="editor-panel"><div className="section-heading"><div><span className="kicker">{editing ? 'Update credentials' : 'New connection'}</span><h2>{editing ? 'Edit database' : 'Add database'}</h2></div></div><form onSubmit={submit}>{[['name', 'Name'], ['host', 'Host'], ['bolt_port', 'Bolt port'], ['username', 'Username'], ['default_database', 'Database name'], ['password', editing ? 'New password (optional)' : 'Password']].map(([key, label]) => <label key={key}>{label}<input required={key !== 'password' || !editing} type={key === 'password' ? 'password' : key === 'bolt_port' ? 'number' : 'text'} value={form[key as keyof typeof form]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} /></label>)}<div className="form-actions"><button className="primary" type="submit">{editing ? 'Save changes' : 'Add database'}</button>{editing && <button type="button" onClick={() => setEditing(null)}>Cancel</button>}</div></form></section></div>
  </main>;
}