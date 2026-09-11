import {NOT_AVAILABLE} from "./lib/oiltrace";

export const fmt = (v: unknown, digits = 1) =>
  (typeof v === "number" ? v.toFixed(digits) : NOT_AVAILABLE);

/** Ring of lat/lng around a point, for the drift envelope. */
export const ring = (lat: number, lon: number, km: number): [number, number][] => {
  const dLat = km / 110.574;
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
  return Array.from({length: 49}, (_, i) => {
    const a = (i * 7.5 * Math.PI) / 180;
    return [lat + dLat * Math.cos(a), lon + dLon * Math.sin(a)] as [number, number];
  });
};

export function Card({children, className = "", dataDemo}: {
  children: React.ReactNode; className?: string;
  /** Stable hook for the guided walkthrough to scroll to and highlight. */
  dataDemo?: string;
}) {
  return <section className={"card " + className} data-demo={dataDemo}>{children}</section>;
}
export function Badge({children, tone = "blue"}: {children: React.ReactNode; tone?: string}) {
  return <span className={"badge " + tone}>{children}</span>;
}

/**
 * One term of the suspect score.
 *
 * Shows the raw 0-100 sub-score, the weight the backend applied, and the points
 * that term therefore contributes — so the final number can be checked by eye
 * rather than taken on trust.
 *
 * A null sub-score is the Isolation Forest declining to return a verdict. The
 * backend still weights it as zero in the sum, so that is stated rather than
 * hidden: a term that dragged the score down for want of an answer should not
 * look the same as a term that genuinely scored zero.
 */
export function ScoreBar({label, value, weight, detail}: {
  label: string; value: number | null; weight: number; detail?: string;
}) {
  const missing = typeof value !== "number";
  const pct = missing ? 0 : Math.max(0, Math.min(100, value as number));
  const contribution = (missing ? 0 : (value as number)) * weight;
  return (
    <div className={"scorebar" + (missing ? " missing" : "")}>
      <div className="scorebar-head">
        <b>{label}</b>
        <span className="weight">× {weight.toFixed(2)}</span>
        <strong>{missing ? NOT_AVAILABLE : (value as number).toFixed(2)}</strong>
      </div>
      <div className="scoretrack" role="img"
           aria-label={`${label} ${missing ? "not available" : pct.toFixed(0) + " out of 100"}`}>
        <i style={{width: `${pct}%`}} />
      </div>
      <small>
        {missing
          ? "No verdict returned — counted as 0.00 in the weighted sum."
          : `contributes ${contribution.toFixed(2)} points`}
        {detail ? ` · ${detail}` : ""}
      </small>
    </div>
  );
}
