import {useEffect, useState} from "react";
import {API, NOT_AVAILABLE, showPct} from "../../lib/oiltrace";
import {show} from "../../lib/oiltrace";
import type {Environment, Scan} from "../../types";

interface ModelsPayload {
  detection?: {name?: string; parameters?: number | null;
               validation?: Record<string, number> | null; statement?: string};
  behaviour?: {name?: string; hyperparameters?: Record<string, unknown>; statement?: string};
  attribution?: {is_trained_model?: boolean; validated?: boolean; statement?: string};
  system_limitations?: string[];
}

/**
 * What produced these numbers, and what a reader needs to reproduce or dispute
 * the run.
 *
 * Model facts are fetched from GET /api/models rather than restated here — the
 * same reason they are backend-owned for the MODEL INFO panel. A report that
 * retyped the metrics would eventually disagree with the checkpoint.
 */
export function ReportProvenance({scan, environment}: {
  scan: Scan;
  environment?: Environment | null;
}) {
  const [models, setModels] = useState<ModelsPayload | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`${API}/api/models`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => live && setModels(d))
      .catch(() => undefined);   // absent model info is stated below, not fatal
    return () => { live = false; };
  }, []);

  const p = scan.provenance ?? {};
  const cnn = models?.detection;
  const metrics = cnn?.validation ?? null;

  return (
    <>
      <h3>Model information</h3>
      {models ? (
        <>
          <div className="reportgrid">
            <div><small>DETECTION</small><b>{cnn?.name ?? NOT_AVAILABLE}</b></div>
            <div><small>PARAMETERS</small><b>{cnn?.parameters?.toLocaleString() ?? NOT_AVAILABLE}</b></div>
            <div><small>RECALL (HELD-OUT)</small><b>{showPct(metrics?.recall)}</b></div>
            <div><small>PRECISION</small><b>{showPct(metrics?.precision)}</b></div>
          </div>
          <p className="reportnote">{cnn?.statement}</p>
          <p className="reportnote">{models.behaviour?.statement}</p>
          <p className="reportnote">{models.attribution?.statement}</p>
        </>
      ) : (
        <p className="reportempty">
          Model details could not be loaded from the backend for this report. They are
          available at GET /api/models.
        </p>
      )}

      <h3>Data provenance</h3>
      <div className="reportgrid">
        <div><small>PASS</small><b>{String(scan.snapshot_id).toUpperCase()}
          {scan.observed_at ? ` · ${scan.observed_at.slice(0, 16).replace("T", " ")} UTC` : ""}</b></div>
        <div><small>VESSELS SCANNED</small><b>{show(scan.scanned)}</b></div>
        <div><small>MODE</small><b>{p.live_inference ? "Live inference" : "Stored result"}</b></div>
        <div><small>REGION</small><b>{scan.region ?? NOT_AVAILABLE}</b></div>
      </div>
      <div className="reportgrid">
        <div><small>SAR INPUT</small><b>Sentinel-1, shared pool</b></div>
        <div><small>AIS</small><b>{p.ais_dataset
          ? `${p.ais_dataset.vessels_in_corpus} vessels · ${p.ais_dataset.monitored} monitored`
          : NOT_AVAILABLE}</b></div>
        <div><small>ENVIRONMENTAL DATA</small>
          <b>{environment?.environment_mode === "historical"
            ? (environment.source ?? "loaded") : "None loaded"}</b></div>
        <div><small>SIMULATION SEED</small><b>{show(p.simulation_seed)}</b></div>
      </div>
      <div className="reportgrid">
        <div><small>DETECTION MODEL</small><b>{p.oil_detection?.model_version ?? NOT_AVAILABLE}</b></div>
        <div><small>BEHAVIOUR MODEL</small><b>{p.anomaly_detection?.model_version ?? NOT_AVAILABLE}</b></div>
        <div><small>AIS CO-PRESENCE</small><b>{p.ais_dataset?.co_presence ?? NOT_AVAILABLE}</b></div>
        <div><small>FLEET DATA</small><b>{p.fleet_data ?? NOT_AVAILABLE}</b></div>
      </div>
      {p.simulation_note && <p className="reportnote">{p.simulation_note}</p>}
      {p.sar_input?.note && <p className="reportnote">{p.sar_input.note}</p>}

      <h3>Limitations</h3>
      <ul className="reportlimits">
        {(models?.system_limitations ?? []).map((l, i) => <li key={i}>{l}</li>)}
        <li>
          Classification only — no segmentation, so no spill area, thickness or boundary
          is measured anywhere in this report.
        </li>
        <li>
          Source, age, drift envelope and forecast are model estimates. Ranking is
          analytical association with an estimated source and window; it does not
          establish that any vessel caused the spill.
        </li>
      </ul>
    </>
  );
}
