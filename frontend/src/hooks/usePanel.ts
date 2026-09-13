import {useCallback, useEffect, useState} from "react";
export const PANELS = ["candidates", "evidence", "method", "models", "report", "data", "routing"] as const;
export type Panel = typeof PANELS[number];
const readPanel = (): Panel | null => PANELS.find((p) => location.hash === `#${p}`) ?? null;

/** Panel history shares the current path/query, including the full-map route. */
export function usePanel() {
  const [panel, setPanel] = useState<Panel | null>(readPanel);
  useEffect(() => {
    const sync = () => setPanel(readPanel());
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", sync);
    return () => { window.removeEventListener("popstate", sync); window.removeEventListener("hashchange", sync); };
  }, []);
  const openPanel = useCallback((next: Panel) => {
    if (readPanel() === next) return;
    const url = new URL(location.href); url.hash = next;
    history.pushState({...history.state, oiltracePanel: true}, "", url);
    setPanel(next);
  }, []);
  const closePanel = useCallback(() => {
    if (history.state?.oiltracePanel) history.back();
    else {
      const url = new URL(location.href); url.hash = "";
      history.replaceState(history.state, "", url); setPanel(null);
    }
  }, []);
  return {panel, openPanel, closePanel};
}
