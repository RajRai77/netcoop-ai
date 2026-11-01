import { memo, useMemo } from 'react';
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Cloud, Laptop, Network, Router, Server, Users, Wifi } from 'lucide-react';
import type { Finding, Report, TopologySnapshot } from '@/api/types';

export type NodeState = 'cause' | 'affected' | 'symptom' | 'candidate' | 'healthy' | 'unknown';
export const NODE_COLOR: Record<NodeState, string> = {
  cause: '#e5484d', affected: '#f59e0b', symptom: '#d4a106', candidate: '#7c4dff', healthy: '#4caf50', unknown: '#9aa8bc',
};
export const NODE_LABEL: Record<NodeState, string> = {
  cause: 'Root-cause location', affected: 'Affected', symptom: 'Symptom observed', candidate: 'Candidate location',
  healthy: 'Checked · normal', unknown: 'No findings',
};

const SYMPTOM_FREE = new Set(['COMMON_UPSTREAM_DEPENDENCY', 'COMMON_SERVICE_DEPENDENCY']);
const subjectNode = (f: Finding) => f.subject.device_id ?? f.subject.service_id ?? f.subject.segment_id;

/** Node states derived only from stored findings and the report. "healthy" means a specialist checked the node and
 * reported no anomaly; "unknown" means no specialist reported on it at all. */
export function nodeStates(topo: TopologySnapshot, report?: Report | null, findings?: Finding[]): Map<string, NodeState> {
  const st = new Map<string, NodeState>(topo.nodes.map((n) => [n.id, 'unknown']));
  const rank: NodeState[] = ['cause', 'affected', 'symptom', 'candidate', 'healthy', 'unknown'];
  const set = (id: string | undefined, s: NodeState) => {
    if (!id || !st.has(id)) return;
    if (rank.indexOf(s) < rank.indexOf(st.get(id)!)) st.set(id, s);
  };
  for (const f of findings ?? []) {
    if (SYMPTOM_FREE.has(f.claim)) continue;
    set(subjectNode(f), f.polarity === 'present' ? 'symptom' : 'healthy');
  }
  for (const h of report?.hypotheses ?? []) if (h.status !== 'contradicted') set(h.location.split(':')[0], 'candidate');
  for (const a of report?.affected_devices ?? []) set(a, 'affected');
  for (const rc of report?.root_causes ?? []) set(rc.location.split(':')[0], 'cause');
  return st;
}

/** Topology impact scope of the selected root cause(s), as computed by the backend hypothesis. */
export function impactScope(report?: Report | null): Set<string> {
  const ids = new Set((report?.root_causes ?? []).map((c) => c.hypothesis_id));
  const out = new Set<string>();
  for (const h of report?.hypotheses ?? []) if (ids.has(h.hypothesis_id)) h.impact_scope.forEach((x) => out.add(x.split(':')[0]));
  return out;
}

const ICONS: Record<string, typeof Router> = { device: Router, ap: Wifi, service: Server, segment: Users, host: Laptop };

type TData = { label: string; sub: string; state: NodeState; type: string; role?: string; selected: boolean; small: boolean; count?: string; dim: boolean; scope: boolean };

const TNode = memo(({ data }: NodeProps<Node<TData>>) => {
  const core = data.role === 'core';
  const Icon = core ? Cloud : data.type === 'device' && data.role === 'distribution' ? Network : ICONS[data.type] ?? Router;
  return (
    <div className={`tnode ${data.small ? 'small' : ''} ${core ? 'core' : ''} ${data.state === 'cause' ? 'cause' : ''} ${data.selected ? 'selected' : ''} ${data.dim ? 'dim' : ''}`}
         style={{ ['--c' as string]: NODE_COLOR[data.state] }} title={`${data.label} · ${NODE_LABEL[data.state]}${data.scope ? ' · in impact scope' : ''}`}>
      <Handle type="target" position={Position.Top} />
      <div className="tnode-orb" style={data.scope && data.state !== 'cause' ? { outline: '2px dashed #f59e0b', outlineOffset: 4 } : undefined}>
        <Icon size={data.small ? 14 : core ? 24 : 20} />
        {data.state === 'cause' && <span className="tnode-alert">!</span>}
      </div>
      <div className="tnode-label">{data.label}</div>
      {data.sub && <div className="tnode-sub">{data.sub}</div>}
      {data.count && <div className="tnode-count">{data.count}</div>}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
});

const nodeTypes = { t: TNode };

function layout(topo: TopologySnapshot) {
  const phys = topo.links.filter((l) => l.type !== 'dependency');
  const adj = new Map<string, string[]>(topo.nodes.map((n) => [n.id, []]));
  for (const l of phys) {
    adj.get(l.from)?.push(l.to);
    adj.get(l.to)?.push(l.from);
  }
  const depth = new Map<string, number>();
  const parent = new Map<string, string>();
  const q = topo.nodes.filter((n) => n.role === 'core').map((n) => n.id);
  if (!q.length && topo.nodes[0]) q.push(topo.nodes[0].id);
  q.forEach((r) => depth.set(r, 0));
  while (q.length) {
    const c = q.shift()!;
    for (const n of adj.get(c) ?? []) {
      if (!depth.has(n)) {
        depth.set(n, depth.get(c)! + 1);
        parent.set(n, c);
        q.push(n);
      }
    }
  }
  for (const n of topo.nodes) if (!depth.has(n.id)) depth.set(n.id, 1);
  const levels: string[][] = [];
  for (const n of topo.nodes) (levels[depth.get(n.id)!] ??= []).push(n.id);
  const order = new Map<string, number>();
  levels.forEach((lvl, d) => {
    lvl.sort((a, b) => {
      const nat = (x: string, y: string) => x.localeCompare(y, undefined, { numeric: true });
      if (d === 0) return nat(a, b);
      const pa = order.get(parent.get(a) ?? '') ?? 0;
      const pb = order.get(parent.get(b) ?? '') ?? 0;
      return pa - pb || nat(a, b);
    });
    lvl.forEach((id, i) => order.set(id, i));
  });
  // A level wider than MAX_ROW (e.g. a flat star of switches) is wrapped into several rows.
  const MAX_ROW = topo.nodes.length > 18 ? 9 : 6;
  const rows: string[][] = [];
  for (const lvl of levels) {
    if (!lvl) continue;
    for (let i = 0; i < lvl.length; i += MAX_ROW) rows.push(lvl.slice(i, i + MAX_ROW));
  }
  const width = Math.max(...rows.map((l) => l.length), 1);
  const gapX = topo.nodes.length <= 18 ? 128 : 112;
  const pos = new Map<string, { x: number; y: number }>();
  rows.forEach((row, r) => {
    const off = ((width - row.length) * gapX) / 2;
    row.forEach((id, i) => pos.set(id, { x: off + i * gapX, y: r * 118 }));
  });
  return pos;
}

/** Compact view: hosts/segments without any reported problem are folded into a count on their parent node.
 * Anything with a reported state (symptom, affected, cause, candidate) always stays visible. */
function collapse(topo: TopologySnapshot, states: Map<string, NodeState>) {
  const leafTypes = new Set(['host', 'segment']);
  const quiet = (id: string) => ['healthy', 'unknown'].includes(states.get(id) ?? 'unknown');
  const hidden = new Set(topo.nodes.filter((n) => leafTypes.has(n.type) && quiet(n.id)).map((n) => n.id));
  const counts = new Map<string, { host: number; segment: number }>();
  const typeOf = new Map(topo.nodes.map((n) => [n.id, n.type]));
  for (const l of topo.links) {
    if (l.type === 'dependency') continue;
    const leaf = hidden.has(l.to) ? l.to : hidden.has(l.from) ? l.from : null;
    const parent = leaf === l.to ? l.from : leaf === l.from ? l.to : null;
    if (!leaf || !parent || hidden.has(parent)) continue;
    const c = counts.get(parent) ?? { host: 0, segment: 0 };
    c[typeOf.get(leaf) === 'host' ? 'host' : 'segment'] += 1;
    counts.set(parent, c);
  }
  const t: TopologySnapshot = {
    ...topo,
    nodes: topo.nodes.filter((n) => !hidden.has(n.id)),
    links: topo.links.filter((l) => !hidden.has(l.from) && !hidden.has(l.to)),
  };
  const label = new Map<string, string>();
  for (const [id, c] of counts) {
    const parts: string[] = [];
    if (c.host) parts.push(c.host + (c.host > 1 ? ' hosts' : ' host'));
    if (c.segment) parts.push(c.segment + ' seg');
    label.set(id, '+' + parts.join(', '));
  }
  return { t, label };
}

export function TopologyGraph({ topo, report, findings, selected, onSelect, compact = false }: {
  topo: TopologySnapshot; report?: Report | null; findings?: Finding[]; selected?: string | null;
  onSelect?: (id: string | null) => void; compact?: boolean;
}) {
  const states = useMemo(() => nodeStates(topo, report, findings), [topo, report, findings]);
  const scope = useMemo(() => impactScope(report), [report]);
  const collapsed = useMemo(
    () => (compact ? collapse(topo, states) : { t: topo, label: new Map<string, string>() }), [compact, topo, states]);
  const view = collapsed.t;
  const countLabel = collapsed.label;
  const pos = useMemo(() => layout(view), [view]);
  const related = useMemo(() => {
    if (!selected) return null;
    const r = new Set([selected]);
    for (const l of view.links) {
      if (l.from === selected) r.add(l.to);
      if (l.to === selected) r.add(l.from);
    }
    return r;
  }, [selected, view]);
  const nodes: Node<TData>[] = useMemo(() => view.nodes.map((n) => {
    const small = n.type === 'host' || n.type === 'segment';
    return {
      id: n.id, type: 't', position: pos.get(n.id) ?? { x: 0, y: 0 },
      data: {
        label: n.id, small, state: states.get(n.id) ?? 'unknown', type: n.type, role: n.role, selected: selected === n.id,
        sub: n.service_kind ? n.service_kind.toUpperCase() : n.role && !small ? n.role : '',
        count: countLabel.get(n.id), dim: !!related && !related.has(n.id), scope: scope.has(n.id),
      },
      draggable: false,
    };
  }), [view, pos, states, selected, countLabel, related, scope]);
  const edges: Edge[] = useMemo(() => view.links.map((l) => {
    const a = states.get(l.from), b = states.get(l.to);
    const bad = (s?: NodeState) => s === 'cause' || s === 'affected';
    const hot = bad(a) && bad(b) || (bad(a) && b !== 'unknown' && scope.has(l.to)) || (bad(b) && scope.has(l.from));
    const dep = l.type === 'dependency';
    const sel = !!selected && (l.from === selected || l.to === selected);
    const ok = a === 'healthy' && b === 'healthy';
    const color = sel ? '#1a73e8' : hot ? (a === 'cause' || b === 'cause' ? '#e5484d' : '#f59e0b') : dep ? '#a48bff' : ok ? '#8fcf92' : '#c3cfdf';
    return {
      id: l.id, source: l.from, target: l.to, type: dep ? 'default' : 'smoothstep',
      style: { stroke: color, strokeWidth: hot || sel ? 2.6 : 1.6, strokeDasharray: dep ? '5 5' : undefined, opacity: related && !sel ? 0.35 : 1 },
      animated: hot,
    };
  }), [view, states, selected, related, scope]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: compact ? 0.06 : 0.12 }}
      minZoom={0.2}
      maxZoom={2}
      nodesConnectable={false}
      nodesDraggable={false}
      elementsSelectable
      onNodeClick={(_e, n) => onSelect?.(n.id === selected ? null : n.id)}
      onPaneClick={() => onSelect?.(null)}
      proOptions={{ hideAttribution: true }}
      colorMode="light"
      style={{ background: 'transparent' }}
    >
      <Background color="#dfe6f0" gap={26} size={1.2} />
      {!compact && <Controls showInteractive={false} position="bottom-left" />}
    </ReactFlow>
  );
}

export function TopologyLegend({ counts, strip = false }: { counts?: Map<NodeState, number>; strip?: boolean }) {
  const order: NodeState[] = ['cause', 'affected', 'symptom', 'candidate', 'healthy', 'unknown'];
  return (
    <div className={`topo-legend ${strip ? 'strip' : 'glass soft'}`}>
      {order.filter((s) => !counts || (counts.get(s) ?? 0) > 0 || s === 'cause' || s === 'healthy').map((s) => (
        <span key={s}><i style={{ background: NODE_COLOR[s] }} />{NODE_LABEL[s]}{counts ? ` (${counts.get(s) ?? 0})` : ''}</span>
      ))}
      <span><i style={{ background: 'transparent', border: '2px dashed #f59e0b', borderRadius: 4 }} />Impact scope</span>
    </div>
  );
}
