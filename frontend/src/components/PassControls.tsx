export function PassControls({ids, current, busy, onChange, times}: {
  ids: string[]; current?: string | null; busy?: boolean; onChange: (id: string) => void; times?: Record<string, string>;
}) {
  return <div className="pass-controls" aria-label="Satellite observations"><span>OBSERVATIONS</span>{ids.map((id) => <button key={id} disabled={busy} aria-pressed={current === id} className={current === id ? "active" : ""} onClick={() => onChange(id)} title={times?.[id] ? `${id.toUpperCase()} · ${times[id]}` : `Open ${id.toUpperCase()}`}>
    {id.toUpperCase()}{times?.[id] && <small>{times[id].slice(11, 16)}</small>}
  </button>)}</div>;
}
