import { memo, useMemo } from 'react';
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Globe, Laptop, Network, Router, Server, Users, Wifi } from 'lucide-react';
import type { Finding, Report, TopologySnapshot } from '@/api/types';

export type NodeState = 'cause' | 'affected' | 'symptom' | 'candidate' | 'healthy';
export const NODE_COLOR: Record<NodeState, string> = {
  cause: '#ef4444', affected: '#f59e0b', symptom: '#facc15', candidate: '#a78bfa', healthy: '#22d3ee',
};
export const NODE_LABEL: Record<NodeState, string> = {
  cause: 'Root-cause location', affected: 'Affected', symptom: 'Symptom observed', candidate: 'Candidate location', healthy: 'No issue reported',
};

const SYMPTOM_FREE = new Set(['COMMON_UPSTREAM_DEPENDENCY', 'COMMON_SERVICE_DEPENDENCY']);

export function nodeStates(topo: TopologySnapshot, report?: Report | null, findings?: Finding[]): Map<string, NodeState> {
  const st = new Map<string, NodeState>(topo.nodes.map((n) => [n.id, 'healthy']));
  const set = (id: string | undefined, s: NodeState, rank: NodeState[]) => {
    if (!id || !st.has(id)) return;
    const cur = st.get(id)!;
    if (rank.indexOf(s) < rank.indexOf(cur)) st.set(id, s);
  };
  const rank: NodeState[] = ['cause', 'affected', 'symptom', 'candidate', 'healthy'];
  for (const f of findings ?? []) {
    if (f.polarity !== 'present' || SYMPTOM_FREE.has(f.claim)) continue;
    set(f.subject.device_id ?? f.subject.service_id ?? f.subject.segment_id, 'symptom', rank);
  }
  for (const h of report?.hypotheses ?? []) {
    if (h.status !== 'contradicted') set(h.location.split(':')[0], 'candidate', rank);
  }
  for (const a of report?.affected_devices ?? []) set(a, 'affected', rank);
  for (const rc of report?.root_causes ?? []) set(rc.location.split(':')[0], 'cause', rank);
  return st;
}

const ICONS: Record<string, typeof Router> = { device: Router, ap: Wifi, service: Server, segment: Users, host: Laptop };

type TData = { label: string; sub: string; state: NodeState; type: string; role?: string; selected: boolean; small: boolean; count?: string };

const TNode = memo(({ data }: NodeProps<Node<TData>>) => {
  const Icon = data.role === 'core' ? Globe : data.type === 'device' && data.role === 'distribution' ? Network : ICONS[data.type] ?? Router;
  return (
    <div className={`tnode ${data.small ? 'small' : ''} ${data.state === 'cause' ? 'cause' : ''} ${data.selected ? 'selected' : ''}`}
         style={{ ['--c' as string]: NODE_COLOR[data.state] }} title={`${data.label} · ${NODE_LABEL[data.state]}`}>
      <Handle type="target" position={Position.Top} />
      <div className="tnode-orb"><Icon size={data.small ? 14 : 20} /></div>
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
      if (d === 0) return a.localeCompare(b);
      const pa = order.get(parent.get(a) ?? '') ?? 0;
      const pb = order.get(parent.get(b) ?? '') ?? 0;
      return pa - pb || a.localeCompare(b);
    });
    lvl.forEach((id, i) => order.set(id, i));
  });
  const width = Math.max(...levels.map((l) => l?.length ?? 0), 1);
  const gapX = topo.nodes.length <= 18 ? 150 : 120;
  const pos = new Map<string, { x: number; y: number }>();
  levels.forEach((lvl, d) => {
    if (!lvl) return;
    const off = ((width - lvl.length) * gapX) / 2;
    lvl.forEach((id, i) => pos.set(id, { x: off + i * gapX, y: d * 130 }));
  });
  return pos;
}

/** Compact view: healthy hosts/segments are folded into a count on the node they attach to.
 * Anything with a reported state (symptom, affected, cause, candidate) always stays visible. */
function collapse(topo: TopologySnapshot, states: Map<string, NodeState>) {
  const leafTypes = new Set(['host', 'segment']);
  const hidden = new Set(topo.nodes.filter((n) => leafTypes.has(n.type) && (states.get(n.id) ?? 'healthy') === 'healthy').map((n) => n.id));
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
  const collapsed = useMemo(
    () => (compact ? collapse(topo, states) : { t: topo, label: new Map<string, string>() }), [compact, topo, states]);
  const view = collapsed.t;
  const countLabel = collapsed.label;
  const pos = useMemo(() => layout(view), [view]);
  const nodes: Node<TData>[] = useMemo(() => view.nodes.map((n) => {
    const small = n.type === 'host' || n.type === 'segment';
    const st = states.get(n.id) ?? 'healthy';
    return {
      id: n.id, type: 't', position: pos.get(n.id) ?? { x: 0, y: 0 },
      data: {
        label: n.id, small, state: st, type: n.type, role: n.role, selected: selected === n.id,
        sub: n.service_kind ? n.service_kind.toUpperCase() : n.role && !small ? n.role : '',
        count: countLabel.get(n.id),
      },
      draggable: false,
    };
  }), [view, pos, states, selected, countLabel]);
  const edges: Edge[] = useMemo(() => view.links.map((l) => {
    const a = states.get(l.from), b = states.get(l.to);
    const hot = (a === 'cause' || a === 'affected') && (b === 'cause' || b === 'affected');
    const dep = l.type === 'dependency';
    const color = hot ? (a === 'cause' || b === 'cause' ? '#ef4444' : '#f59e0b') : dep ? 'rgba(196,181,253,.45)' : 'rgba(125,211,252,.42)';
    return {
      id: l.id, source: l.from, target: l.to, type: dep ? 'default' : 'straight',
      style: { stroke: color, strokeWidth: hot ? 2.6 : 1.4, strokeDasharray: dep ? '5 5' : undefined,
        filter: hot ? `drop-shadow(0 0 4px ${color})` : undefined },
    };
  }), [view, states]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: compact ? 0.08 : 0.15 }}
      minZoom={0.2}
      maxZoom={2}
      nodesConnectable={false}
      nodesDraggable={false}
      elementsSelectable
      onNodeClick={(_e, n) => onSelect?.(n.id === selected ? null : n.id)}
      onPaneClick={() => onSelect?.(null)}
      proOptions={{ hideAttribution: true }}
      colorMode="dark"
      style={{ background: 'transparent' }}
    >
      <Background color="rgba(125,211,252,.08)" gap={28} size={1} />
      {!compact && <Controls showInteractive={false} position="bottom-left" />}
    </ReactFlow>
  );
}

export function TopologyLegend({ counts, strip = false }: { counts?: Map<NodeState, number>; strip?: boolean }) {
  return (
    <div className={`glass soft topo-legend ${strip ? 'strip' : ''}`}>
      {(Object.keys(NODE_COLOR) as NodeState[]).map((s) => (
        <span key={s}><i style={{ background: NODE_COLOR[s], boxShadow: `0 0 8px ${NODE_COLOR[s]}` }} />{NODE_LABEL[s]}{counts ? ` · ${counts.get(s) ?? 0}` : ''}</span>
      ))}
      <span><i style={{ background: 'transparent', border: '1px dashed #c4b5fd', borderRadius: 2, width: 14, height: 0 }} />Service dependency</span>
    </div>
  );
}
