'use client';

import { useEffect, useMemo, useState } from 'react';
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

type GraphPayload = { nodes: Array<{ id: string; type: string; label: string }>; edges: Array<{ id: string; source: string; target: string; label: string }> };
type LiveEvent = { type: string; timestamp?: string; agent_status?: string; quota?: { used: number; limit: number; reset: string }; control?: string };

const initialTimeline = [
  ['09:42:18', 'Memory context built', '2-hop retrieval · 14 nodes'],
  ['09:42:12', 'Safety policy passed', '3 actions approved'],
  ['09:41:56', 'Agent entered planning', 'Confidence 0.86'],
  ['09:40:03', 'Task received', 'Fix authentication flow'],
];

export default function HomePage() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [agentStatus, setAgentStatus] = useState('IDLE');
  const [quota, setQuota] = useState({ used: 64, limit: 100, reset: '18 min' });
  const [connected, setConnected] = useState(false);
  const [control, setControl] = useState('ON');
  const [model, setModel] = useState('Claude 3.5 Haiku');
  const [strategy, setStrategy] = useState<'First Prompt Only' | 'Autonomous'>('First Prompt Only');
  const [timeline, setTimeline] = useState(initialTimeline);
  const [socket, setSocket] = useState<WebSocket | null>(null);

  useEffect(() => {
    fetch('http://localhost:8000/graph').then((response) => response.json()).then((payload: GraphPayload) => {
      setNodes(payload.nodes.map((node, index) => ({ id: node.id, position: { x: 110 + (index % 3) * 220, y: 80 + Math.floor(index / 3) * 150 }, data: { label: node.label }, style: { background: node.type === 'Error' ? '#f5d3ce' : node.type === 'Decision' ? '#fbe0c9' : '#fafff8' } })));
      setEdges(payload.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, label: edge.label, animated: edge.label === 'CAUSED' })));
    }).catch(() => undefined);

    const socketUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.hostname}:8000/ws/dashboard?task_id=task-ws`;
    const socket = new WebSocket(socketUrl);
    setSocket(socket);
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as LiveEvent;
      if (event.agent_status) setAgentStatus(event.agent_status);
      if (event.quota) setQuota(event.quota);
      if (event.type === 'control_ack') setTimeline((items) => [[new Date().toLocaleTimeString(), `Control ${event.control}`, 'Live command acknowledged'], ...items].slice(0, 5));
    };
    return () => {
      socket.close();
      setSocket(null);
    };
  }, []);

  const flowNodes = useMemo(() => nodes, [nodes]);
  const sendControl = (next: string) => {
    setControl(next);
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: next }));
  };
  const selectStrategy = (next: 'First Prompt Only' | 'Autonomous') => {
    setStrategy(next);
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'PROMPT_STRATEGY', strategy: next === 'Autonomous' ? 'autonomous' : 'first-prompt-only' }));
  };

  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand"><div className="brand-mark">B</div><div><h1>BrainGraph Runtime</h1><p>autonomous coding workspace / control plane</p></div></div>
        <div className="top-actions">
          <span className="connection"><i className={`dot ${connected ? 'live' : ''}`} /> {connected ? 'LIVE STREAM' : 'OFFLINE'}</span>
          {['ON', 'PAUSE', 'STOP'].map((item) => <button key={item} className={`control ${control === item ? 'active' : ''} ${item === 'STOP' ? 'stop' : ''}`} onClick={() => sendControl(item)}>{item}</button>)}
        </div>
      </header>

      <div className="layout">
        <section className="left">
          <section className="panel brain"><div className="panel-head"><h2>Project Brain</h2><span>{nodes.length || 6} nodes · graph memory</span></div><div className="flow-wrap"><ReactFlow nodes={flowNodes} edges={edges} fitView><Background /><MiniMap /><Controls /></ReactFlow></div></section>
          <div className="task-grid">
            <section className="panel metric"><span className="eyebrow">Current task</span><strong>Fix authentication flow</strong><p>Task / high priority / 4 files linked</p><div className="progress"><i style={{ width: '68%' }} /></div></section>
            <section className="panel metric"><span className="eyebrow">Agent status</span><strong>{agentStatus}</strong><p>Iteration 04 · {strategy.toLowerCase()} mode</p><div className="progress"><i style={{ width: agentStatus === 'IDLE' ? '8%' : '46%' }} /></div></section>
          </div>
          <section className="panel"><div className="panel-head"><h2>Execution Timeline</h2><span>latest events</span></div><div className="timeline">{timeline.map(([time, title, detail]) => <div className="event" key={`${time}-${title}`}><span className="time">{time}</span><i className="event-mark" /><div><strong>{title}</strong><p>{detail}</p></div></div>)}</div></section>
        </section>

        <aside className="right">
          <section className="panel"><div className="panel-head"><h2>Runtime controls</h2><span>configured</span></div><div className="selectors"><div className="selector"><label>Model</label><select value={model} onChange={(event) => setModel(event.target.value)}><option>Claude 3.5 Haiku</option><option>GPT-4o mini</option><option>Gemini 1.5 Flash</option></select></div><div className="selector"><label>Prompt strategy</label><select value={strategy} onChange={(event) => selectStrategy(event.target.value as 'First Prompt Only' | 'Autonomous')}><option>First Prompt Only</option><option>Autonomous</option></select></div></div></section>
          <section className="panel"><div className="panel-head"><h2>Quota status</h2><span>{quota.reset} to reset</span></div><div className="metric"><span className="eyebrow">Provider capacity</span><strong>{quota.used} / {quota.limit}</strong><p>{model} · {quota.limit - quota.used} requests remaining</p><div className="progress"><i style={{ width: `${quota.used / quota.limit * 100}%` }} /></div></div></section>
          <section className="panel"><div className="panel-head"><h2>Safety alerts</h2><span>policy monitor</span></div><div className="status-list"><div className="status-row"><span>Network access</span><b className="badge">BLOCKED</b></div><div className="status-row"><span>Filesystem boundary</span><b className="badge">PASSED</b></div><div className="status-row"><span>Pending approval</span><b className="badge warn">1 REVIEW</b></div><div className="status-row"><span>Last blocked action</span><b className="badge alert">NONE</b></div></div></section>
          <section className="panel"><div className="panel-head"><h2>Git history</h2><span>checkpoints</span></div><div className="git-item"><span className="hash">a81f2c</span><div><strong>checkpoint: auth flow</strong><p>4 files · iteration 03 · 2m ago</p></div></div><div className="git-item"><span className="hash">c42be1</span><div><strong>test: add token coverage</strong><p>2 files · iteration 02 · 8m ago</p></div></div><div className="git-item"><span className="hash">9d173a</span><div><strong>scaffold runtime graph</strong><p>12 files · iteration 01 · 21m ago</p></div></div></section>
        </aside>
      </div>
    </main>
  );
}
