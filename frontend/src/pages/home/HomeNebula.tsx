/**
 * The home page's background (nebula.ts draws it): before the projects open, a nebula that forms
 * a wind turbine over waves from time to time; after, the same matter gathered into orbs, one for
 * each project and some free. The names and buttons come as children, over it.
 */
import { type ReactNode, useEffect, useRef } from "react";

import { prefersReducedMotion } from "../../motion";
import { createEngine, type Engine, type Mode } from "./nebula";

export function HomeNebula({ mode, burst, onEngine, children }: {
  mode: Mode;
  burst: { x: number; y: number; at: number } | null;
  onEngine: (engine: Engine | null) => void;
  children?: ReactNode;
}) {
  const host = useRef<HTMLDivElement>(null);
  const engine = useRef<Engine | null>(null);
  const first = useRef({ mode, onEngine });
  useEffect(() => {
    const root = host.current;
    if (!root) return;
    // A new canvas each time: a WebGL context once released cannot be used again
    const canvas = document.createElement("canvas");
    canvas.className = "ows-home-canvas";
    canvas.setAttribute("aria-hidden", "true");
    root.prepend(canvas);
    const created = createEngine(canvas, { reduced: prefersReducedMotion(), mode: first.current.mode });
    engine.current = created;
    first.current.onEngine(created);
    return () => {
      created?.dispose();
      canvas.remove();
      engine.current = null;
      first.current.onEngine(null);
    };
  }, []);
  useEffect(() => engine.current?.setMode(mode), [mode]);
  useEffect(() => {
    if (burst) engine.current?.burst(burst.x, burst.y);
  }, [burst]);
  return (
    <div ref={host} className="ows-home-backdrop" data-mode={mode}>
      <div className="ows-home-veil" />
      {children}
    </div>
  );
}
