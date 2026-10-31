import { useEffect, type ReactNode } from 'react';
import { AlertTriangle, Inbox, Loader2, X } from 'lucide-react';
import type { ReportStatus, SupportCategory, WorkflowState } from '@/api/types';
import { errorText } from '@/api/client';
import { STATE_LABEL, STATUS_LABEL, STATUS_TONE, SUPPORT_LABEL, SUPPORT_STEPS, SUPPORT_TONE, type Tone } from '@/lib/format';

export function Panel({ title, icon, sub, actions, children, className = '', bodyClass = '' }: {
  title?: ReactNode; icon?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={`glass panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          {title && (
            <div>
              <h2 className="panel-title" style={{ margin: 0 }}>
                {icon && <span className="ico">{icon}</span>}
                {title}
              </h2>
              {sub && <div className="panel-sub">{sub}</div>}
            </div>
          )}
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      <div className={`panel-body ${bodyClass}`}>{children}</div>
    </section>
  );
}

export const Chip = ({ tone = 'muted', children, pip = false, title }: { tone?: Tone; children: ReactNode; pip?: boolean; title?: string }) => (
  <span className={`chip t-${tone}`} title={title}>
    {pip && <span className="pip" />}
    {children}
  </span>
);

export const StatusChip = ({ status }: { status: ReportStatus }) => <Chip tone={STATUS_TONE[status]} pip>{STATUS_LABEL[status]}</Chip>;
export const SupportChip = ({ category }: { category: SupportCategory }) => (
  <Chip tone={SUPPORT_TONE[category]} title="Documented support category — not a probability">{SUPPORT_LABEL[category]}</Chip>
);

export function Kpi({ icon, tone = '', value, unit, label, title }: { icon: ReactNode; tone?: string; value: ReactNode; unit?: ReactNode; label: string; title?: string }) {
  return (
    <div className="glass kpi" title={title}>
      <div className={`kpi-ico ${tone}`}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <div className="kpi-value">
          {value}
          {unit && <small> {unit}</small>}
        </div>
        <div className="kpi-label">{label}</div>
      </div>
    </div>
  );
}

export const Loading = ({ label = 'Loading…' }: { label?: string }) => (
  <div className="state">
    <Loader2 className="ico" size={22} style={{ animation: 'spin 1s linear infinite' }} />
    <span>{label}</span>
    <style>{'@keyframes spin{to{transform:rotate(360deg)}}'}</style>
  </div>
);
export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => (
  <div className="state">
    <Inbox className="ico" size={26} />
    <div style={{ color: 'var(--text)', fontWeight: 600 }}>{title}</div>
    {children && <div style={{ maxWidth: 420, fontSize: 13.5 }}>{children}</div>}
  </div>
);
export const ErrorState = ({ error, title = 'Could not load' }: { error: unknown; title?: string }) => (
  <div className="state">
    <AlertTriangle className="ico" size={24} style={{ color: 'var(--amber)' }} />
    <div style={{ color: 'var(--text)', fontWeight: 600 }}>{title}</div>
    <div style={{ maxWidth: 460, fontSize: 13.5 }}>{errorText(error)}</div>
  </div>
);

export function Drawer({ open, title, sub, onClose, children }: { open: boolean; title: ReactNode; sub?: ReactNode; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="glass strong drawer" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Details'}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 18, fontWeight: 680 }}>{title}</div>
            {sub && <div className="panel-sub" style={{ marginTop: 2 }}>{sub}</div>}
          </div>
          <button className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}

export const Json = ({ value }: { value: unknown }) => <pre className="json">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>;

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode }[] }) {
  return (
    <div className="tabs" role="tablist">
      {items.map((i) => (
        <button key={i.id} role="tab" aria-selected={value === i.id} className={value === i.id ? 'on' : ''} onClick={() => onChange(i.id)}>{i.label}</button>
      ))}
    </div>
  );
}

const TONE_VAR: Record<Tone, string> = {
  cyan: 'var(--cyan)', green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)', violet: 'var(--violet)',
  blue: 'var(--blue)', muted: 'var(--text-muted)', magenta: 'var(--magenta)',
};
export const toneVar = (t: Tone) => TONE_VAR[t];

/** Qualitative support meter: ordered categories, never a percentage. */
export function SupportMeter({ category }: { category: SupportCategory }) {
  const idx = SUPPORT_STEPS.indexOf(category);
  const tone = SUPPORT_TONE[category];
  return (
    <div className="meter" style={{ ['--mc' as string]: toneVar(tone) }}>
      <div className="meter-steps" aria-hidden>
        {SUPPORT_STEPS.map((s, i) => <i key={s} className={idx >= 0 && i <= idx ? 'on' : ''} />)}
      </div>
      <div className="meter-label">{SUPPORT_LABEL[category]}</div>
      <div className="meter-note">support category · not a probability</div>
    </div>
  );
}

const FLOW: WorkflowState[] = ['VALIDATING', 'DISCOVERING', 'INVESTIGATING', 'CORRELATING', 'VERIFYING'];
const SHORT: Partial<Record<WorkflowState, string>> = {
  VALIDATING: 'Validate', DISCOVERING: 'Discover agents', INVESTIGATING: 'Investigate', CORRELATING: 'Correlate', VERIFYING: 'Verify',
};
export function Lifecycle({ seen, current, running }: { seen: Set<string>; current: WorkflowState | null; running: boolean }) {
  const terminal = current && !FLOW.includes(current) && current !== 'NEW' ? current : null;
  return (
    <div className="lifecycle" aria-label="Diagnosis lifecycle">
      {FLOW.map((s, i) => (
        <span key={s} style={{ display: 'contents' }}>
          {i > 0 && <span className="lc-sep" />}
          <span className={`lc-step ${current === s && running ? 'now' : seen.has(s) ? 'done' : ''}`} title={STATE_LABEL[s]}><i />{SHORT[s]}</span>
        </span>
      ))}
      <span className="lc-sep" />
      <span className={`lc-step ${terminal ? 'now' : ''}`}><i />{terminal ? STATE_LABEL[terminal] : 'Conclusion'}</span>
    </div>
  );
}

export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
      <defs>
        <radialGradient id="lg-core" cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor="#67e8f9" />
          <stop offset="70%" stopColor="#2563eb" />
          <stop offset="100%" stopColor="#1e1b4b" />
        </radialGradient>
        <filter id="lg-glow"><feGaussianBlur stdDeviation="1.6" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <circle cx="24" cy="24" r="21" fill="none" stroke="rgba(103,232,249,.45)" strokeWidth="1.2" />
      <ellipse cx="24" cy="24" rx="21" ry="8" fill="none" stroke="rgba(103,232,249,.35)" strokeWidth="1" transform="rotate(-28 24 24)" />
      <g filter="url(#lg-glow)" stroke="#67e8f9" strokeWidth="1.6">
        <line x1="24" y1="24" x2="10" y2="14" /><line x1="24" y1="24" x2="38" y2="13" /><line x1="24" y1="24" x2="34" y2="37" />
        <line x1="24" y1="24" x2="12" y2="35" /><line x1="10" y1="14" x2="38" y2="13" opacity=".45" />
      </g>
      <circle cx="24" cy="24" r="6.5" fill="url(#lg-core)" filter="url(#lg-glow)" />
      {[[10, 14, '#22d3ee'], [38, 13, '#e879f9'], [34, 37, '#22d3ee'], [12, 35, '#8b5cf6']].map(([x, y, c]) => (
        <circle key={`${x}-${y}`} cx={x as number} cy={y as number} r="3.2" fill={c as string} filter="url(#lg-glow)" />
      ))}
    </svg>
  );
}
