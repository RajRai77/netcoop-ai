import { createElement, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Cpu, Download, FileText, Globe2, Radio, ServerCrash, ShieldQuestion, Unplug, Waves, Wifi } from 'lucide-react';
import type { Finding, Hypothesis, Report } from '@/api/types';
import { claimLabel, downloadBlob, faultLabel, fmtValue, HYP_LABEL, HYP_TONE, STATUS_LABEL, subjectText } from '@/lib/format';
import { Chip, Confidence, Drawer, Json, StatusChip, SupportMeter } from './ui';

const FAULT_ICON: Record<string, typeof Activity> = {
  LINK_CONGESTION: Activity, INTERFACE_DEGRADATION: Waves, LINK_OR_PATH_FAILURE: Unplug, DEVICE_CPU_OVERLOAD: Cpu,
  DEVICE_DOWN: ServerCrash, WEAK_WIFI_SIGNAL: Wifi, WIRELESS_INTERFERENCE: Radio, DNS_FAILURE: Globe2, DHCP_FAILURE: Globe2,
};
export const faultIcon = (f: string) => FAULT_ICON[f] ?? ShieldQuestion;

/** Top hypotheses for a compact board: selected causes, then live competitors, then a few ruled out. */
export function pickHypotheses(r: Report, max = 5): Hypothesis[] {
  const hs = r.hypotheses ?? [];
  const causeIds = new Set((r.root_causes ?? []).map((c) => c.hypothesis_id));
  const causes = hs.filter((h) => causeIds.has(h.hypothesis_id));
  const live = hs.filter((h) => !causeIds.has(h.hypothesis_id) && h.status !== 'contradicted');
  const out = hs.filter((h) => h.status === 'contradicted' && h.explained_findings.length > 0);
  return [...causes, ...live, ...out].slice(0, max);
}

export function HypothesisRow({ h, max, leading, onOpen }: { h: Hypothesis; max: number; leading: boolean; onOpen: () => void }) {
  const icon = createElement(faultIcon(h.fault_type), { size: 18 });
  const n = h.explained_findings.length;
  const pct = max ? Math.max(6, Math.round((n / max) * 100)) : 0;
  return (
    <button className={`hyp ${leading ? 'leading' : ''}`} onClick={onOpen} style={{ width: '100%', textAlign: 'left', color: 'inherit', font: 'inherit' }}>
      <div className="hyp-ico" style={{ color: h.status === 'contradicted' ? 'var(--text-faint)' : 'var(--cyan)' }}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
          <span className="hyp-name" style={h.status === 'contradicted' ? { color: 'var(--text-muted)' } : undefined}>{faultLabel(h.fault_type)}</span>
          <span className="hyp-loc">{h.location}</span>
        </div>
        <div className={`bar ${h.status === 'plausible' ? 'amber' : h.status === 'contradicted' ? 'muted' : ''}`} title="Symptom findings explained, relative to the best explanation (not a probability)">
          <i style={{ width: `${pct}%` }} />
        </div>
        <div className="panel-sub" style={{ marginTop: 5, fontSize: 12.5 }}>
          explains {n} symptom finding{n === 1 ? '' : 's'} · {h.independent_sources} independent source{h.independent_sources === 1 ? '' : 's'}
          {h.status === 'contradicted' && h.contradictions[0] ? ` · ${h.contradictions[0]}` : ''}
          {h.status === 'plausible' && h.missing_discriminators.length ? ` · unchecked: ${[...new Set(h.missing_discriminators.map((m) => claimLabel(m.claim)))].join(', ')}` : ''}
        </div>
      </div>
      <Chip tone={leading && h.status === 'confirmed' ? 'green' : HYP_TONE[h.status]}>{leading && h.status === 'confirmed' ? 'Selected cause' : HYP_LABEL[h.status]}</Chip>
    </button>
  );
}

export function HypothesisDrawer({ h, findings, onClose }: { h: Hypothesis | null; findings?: Finding[]; onClose: () => void }) {
  const fmap = new Map((findings ?? []).map((f) => [f.finding_id, f]));
  return (
    <Drawer open={!!h} onClose={onClose} title={h ? `${faultLabel(h.fault_type)} at ${h.location}` : ''}
            sub={h && `${h.hypothesis_id} · rank ${h.rank ?? '—'} · ${HYP_LABEL[h.status]}`}>
      {h && (
        <div className="stack" style={{ gap: 14 }}>
          <div className="chips">
            <Chip tone={HYP_TONE[h.status]} pip>{HYP_LABEL[h.status]}</Chip>
            <Chip tone="blue">{h.explained_findings.length} symptoms explained</Chip>
            <Chip tone="cyan">{h.independent_sources} independent sources</Chip>
            <Chip tone="muted">{h.independent_lineage_groups} sample lineages</Chip>
          </div>
          {h.contradictions.length > 0 && <Section title="Contradicted by">{h.contradictions.map((c) => <li key={c}>{c}</li>)}</Section>}
          {h.missing_discriminators.length > 0 && (
            <Section title="Missing discriminating evidence">
              {h.missing_discriminators.map((m, i) => <li key={i}>{claimLabel(m.claim)} at <span className="mono">{subjectText(m.subject)}</span></li>)}
            </Section>
          )}
          {h.temporal_issues.length > 0 && <Section title="Temporal issues">{h.temporal_issues.map((t) => <li key={t}>{t}</li>)}</Section>}
          <Section title="Signature findings">{h.signature_findings.length ? h.signature_findings.map((id) => <FindingLi key={id} id={id} f={fmap.get(id)} />) : <li className="muted">Signature not observed</li>}</Section>
          <Section title="Explained symptom findings">{h.explained_findings.map((id) => <FindingLi key={id} id={id} f={fmap.get(id)} />)}</Section>
          <Section title="Impact scope (topology)"><li className="mono">{h.impact_scope.join(', ') || '—'}</li></Section>
          {h.reasons.length > 0 && <Section title="Notes">{h.reasons.map((r) => <li key={r}>{r}</li>)}</Section>}
          <details><summary className="muted" style={{ cursor: 'pointer' }}>Raw hypothesis record</summary><Json value={h} /></details>
        </div>
      )}
    </Drawer>
  );
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div><div style={{ fontWeight: 620, marginBottom: 6 }}>{title}</div><ul className="list-plain">{children}</ul></div>
);
const FindingLi = ({ id, f }: { id: string; f?: Finding }) => (
  <li>{f ? <><b>{claimLabel(f.claim)}</b> <span className="muted">({f.polarity})</span> at <span className="mono">{subjectText(f.subject)}</span> · {f.agent_id} · {f.observation_refs.length} obs</> : <span className="mono">{id}</span>}</li>
);

export function verdictTitle(r: Report): string {
  if (r.status === 'diagnosed' && r.root_causes?.length) return r.root_causes.map((c) => `${faultLabel(c.fault_type)} at ${c.location}`).join(' + ');
  if (r.status === 'ambiguous') {
    const n = (r.hypotheses ?? []).filter((h) => h.status !== 'contradicted').length;
    return `Ambiguous — ${n} explanation${n === 1 ? '' : 's'} still fit the evidence`;
  }
  if (r.status === 'healthy') return 'No fault detected in the monitored scope';
  return STATUS_LABEL[r.status];
}

export function ReportVerdict({ r, compact = false }: { r: Report; compact?: boolean }) {
  const seen = new Set<string>();
  const ev = r.supporting_evidence.filter((e) => {
    const k = [e.metric, String(e.value), e.unit, e.interpretation.includes('NOT observed')].join('|');
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  }).slice(0, compact ? 4 : 8);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="verdict">
        <div><SupportMeter category={r.confidence_category} /><Confidence r={r} variant="block" /></div>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
            <StatusChip status={r.status} />
            <span className="panel-sub">revision {r.revision} · {r.transport === 'a2a' ? 'specialists over A2A' : r.transport}</span>
          </div>
          <div className="verdict-title">{verdictTitle(r)}</div>
          {r.explanation && <p className="muted" style={{ margin: '8px 0 0', fontSize: 14 }}>{r.explanation}</p>}
        </div>
      </div>
      <dl className="kv">
        <dt>Affected</dt>
        <dd className="chips">{r.affected_devices.length ? r.affected_devices.map((a) => <Chip key={a} tone="amber">{a}</Chip>) : <span className="muted">—</span>}</dd>
        <dt>Key evidence</dt>
        <dd className="chips">
          {ev.length ? ev.map((e) => (
            <Chip key={`${e.observation_id}-${e.finding_id}`} tone={e.interpretation.includes('NOT observed') ? 'muted' : 'cyan'} title={e.interpretation}>
              {e.metric} = {fmtValue(e.value)}{e.unit === 'state' || e.unit === 'boolean' ? '' : ' ' + e.unit}
            </Chip>
          )) : <span className="muted">—</span>}
        </dd>
        <dt>Specialists</dt>
        <dd className="chips">{r.evidence_sources.map((s) => <Chip key={s} tone="violet">{s.replace('-agent', '')}</Chip>)}</dd>
      </dl>
    </div>
  );
}

export function ReportActions({ r }: { r: Report }) {
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Link className="btn sm" to="/report"><FileText size={15} />Full report</Link>
      <button className="btn sm" disabled={busy} onClick={() => { setBusy(true); downloadBlob(`${r.incident_id}-r${r.revision}.json`, JSON.stringify(r, null, 2), 'application/json'); setBusy(false); }}>
        <Download size={15} />JSON
      </button>
    </>
  );
}
