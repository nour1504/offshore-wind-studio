/**
 * The projects as orbs on a slowly turning sphere (drawn by nebula.ts): a project's orb has its
 * colour and name, a free orb starts a new project. Drag or arrow keys turn the sphere; every orb
 * and name is a button.
 */
import { AnimatePresence, motion } from "motion/react";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CaseSummary, RunState } from "../../api/types";
import { common } from "../../i18n/common";
import { defineMessages, useFormat, useT } from "../../i18n";
import { SPRING } from "../../motion";
import type { Engine } from "./nebula";

const messages = defineMessages({
  en: {
    orbs: "Projects",
    free: "New project",
    domains: "{n|# domain|# domains}",
    turbines: "{n|# turbine|# turbines}",
  },
  fr: {
    orbs: "Projets",
    free: "Nouveau projet",
    domains: "{n|# domaine|# domaines}",
    turbines: "{n|# éolienne|# éoliennes}",
  },
});

/** Orbs on the sphere: at least this many, and always a few free ones */
const MIN_ORBS = 18, FREE_ORBS = 6, MAX_ORBS = 48;
const SLOTS = "ows.home.orbs";

/** State of the last run, as a dot */
function StateDot({ state }: { state: RunState }) {
  return <span className="ows-state-dot" data-state={state} aria-hidden="true" />;
}

function readSlots(): Record<string, number> {
  try {
    const value = JSON.parse(window.localStorage.getItem(SLOTS) ?? "{}") as Record<string, number>;
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}
function writeSlots(slots: Record<string, number>) {
  try {
    window.localStorage.setItem(SLOTS, JSON.stringify(slots));
  } catch {
    // Storage blocked: the orbs are dealt again next time
  }
}
/** The orb a new project will take, once created */
export function claimOrb(id: string, index: number) {
  writeSlots({ ...readSlots(), [id]: index });
}

/** Which project holds each orb: kept from visit to visit, new projects on free orbs spread round the sphere. */
function deal(projects: CaseSummary[]): (CaseSummary | null)[] {
  const n = Math.min(MAX_ORBS, Math.max(MIN_ORBS, projects.length + FREE_ORBS));
  const orbs: (CaseSummary | null)[] = new Array(n).fill(null);
  const saved = readSlots();
  const kept: Record<string, number> = {};
  const later: CaseSummary[] = [];
  for (const project of [...projects].sort((a, b) => a.name.localeCompare(b.name))) {
    const k = saved[project.id];
    if (Number.isInteger(k) && k >= 0 && k < n && !orbs[k]) {
      orbs[k] = project;
      kept[project.id] = k;
    } else later.push(project);
  }
  // A stride across the spiral spreads them over the sphere
  for (let step = 0, k = 0; later.length && step < n * 2; step++, k = (k + 7) % n) {
    if (orbs[k]) continue;
    const project = later.shift()!;
    orbs[k] = project;
    kept[project.id] = k;
  }
  writeSlots(kept);
  return orbs;
}

/** A project's name; its period, figures, description and actions show beside it on hover or focus. */
function ProjectName({ project, delay, menu, onOpen }: {
  project: CaseSummary;
  delay: number;
  menu: (project: CaseSummary, onOpenChange: (open: boolean) => void) => ReactNode;
  onOpen: (project: CaseSummary, from: HTMLElement) => void;
}) {
  const t = useT(messages);
  const tc = useT(common);
  const f = useFormat();
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="ows-pin-item" data-menu={menuOpen || undefined}>
      <motion.button
        type="button"
        className="ows-pin-name"
        onClick={(event) => onOpen(project, event.currentTarget)}
        initial={{ opacity: 0, x: -8, filter: "blur(6px)" }}
        animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
        transition={{ ...SPRING.soft, delay }}
      >
        {project.name}
      </motion.button>
      <div className="ows-pin-card">
        <div className="ows-pin-card-inner">
          <div className="ows-pin-facts">
            <span className="ows-num">{f.date(project.start)} → {f.date(project.end)}</span>
            <span>{t("domains", { n: project.domains })}</span>
            {project.turbines > 0 && <span>{t("turbines", { n: project.turbines })}</span>}
            <span className="ows-pin-state"><StateDot state={project.last_run_state} />{tc(`state.${project.last_run_state}`)}</span>
          </div>
          {project.description && <p className="ows-pin-description">{project.description}</p>}
          <div className="ows-pin-actions">{menu(project, setMenuOpen)}</div>
        </div>
      </div>
    </div>
  );
}

export function ProjectOrbs({ engine, projects, menu, onOpen, onCreate }: {
  engine: Engine | null;
  projects: CaseSummary[];
  menu: (project: CaseSummary, onOpenChange: (open: boolean) => void) => ReactNode;
  onOpen: (project: CaseSummary, from: HTMLElement) => void;
  /** A free orb was clicked: a new project for it */
  onCreate: (index: number) => void;
}) {
  const t = useT(messages);
  const orbs = useMemo(() => deal(projects), [projects]);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    engine?.setOrbs(orbs.map(Boolean));
  }, [engine, orbs]);
  useEffect(() => {
    engine?.setHover(hover);
  }, [engine, hover]);

  /* ------------------------------------------------------------------- names and buttons follow the orbs */
  const items = useRef<(HTMLDivElement | null)[]>([]);
  const follow = useCallback(() => {
    if (!engine) return;
    const views = engine.orbs();
    const { width } = engine.size();
    views.forEach((view, k) => {
      const element = items.current[k];
      if (!element) return;
      element.style.transform = `translate3d(${view.x.toFixed(1)}px, ${view.y.toFixed(1)}px, 0)`;
      element.style.setProperty("--r", `${view.r.toFixed(1)}px`);
      element.style.setProperty("--depth", view.depth.toFixed(3));
      element.style.zIndex = String(Math.round(view.depth * 100));
      element.dataset.side = view.x > width - 230 ? "left" : "right";
    });
  }, [engine]);
  useEffect(() => {
    if (!engine) return;
    follow();
    return engine.onFrame(follow);
  }, [engine, follow, orbs]);

  /* ------------------------------------------------------------------- turning the sphere */
  const drag = useRef<{ id: number; x: number; y: number; t: number; vx: number; vy: number; moved: boolean } | null>(null);
  const swallow = useRef(false);
  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!engine || event.button !== 0 || (event.target as HTMLElement).closest(".ows-pin-card")) return;
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, t: performance.now(), vx: 0, vy: 0, moved: false };
  };
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || !engine || d.id !== event.pointerId) return;
    const dx = event.clientX - d.x, dy = event.clientY - d.y, now = performance.now();
    if (!d.moved) {
      if (Math.hypot(dx, dy) < 5) return;
      d.moved = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      engine.setDragging(true);
    }
    const dt = Math.max(1, now - d.t) / 1000;
    d.vx = d.vx * 0.6 + (dx / dt) * 0.4;
    d.vy = d.vy * 0.6 + (dy / dt) * 0.4;
    d.x = event.clientX;
    d.y = event.clientY;
    d.t = now;
    engine.turn(dx, dy);
  };
  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || !engine || d.id !== event.pointerId) return;
    drag.current = null;
    if (!d.moved) return;
    // A drag is not a click
    swallow.current = true;
    window.setTimeout(() => (swallow.current = false), 0);
    engine.setDragging(false);
    if (performance.now() - d.t < 80) engine.fling(d.vx, d.vy);
  };
  const onClickCapture = (event: React.MouseEvent) => {
    if (!swallow.current) return;
    event.preventDefault();
    event.stopPropagation();
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!engine || (event.target as HTMLElement).closest("input, [role=menu]")) return;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-70, 0], ArrowRight: [70, 0], ArrowUp: [0, -50], ArrowDown: [0, 50] };
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    engine.turn(...move);
  };

  return (
    <div
      className="ows-orbs"
      tabIndex={-1}
      role="group"
      aria-label={t("orbs")}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onClickCapture={onClickCapture}
      onKeyDown={onKeyDown}
    >
      {orbs.map((project, k) => (
        <div key={project?.id ?? `free-${k}`} ref={(element) => void (items.current[k] = element)} className="ows-orb" data-held={project ? "" : undefined}>
          <button
            type="button"
            className="ows-orb-hit"
            aria-label={project ? project.name : t("free")}
            onPointerEnter={() => setHover(k)}
            onPointerLeave={() => setHover((value) => (value === k ? null : value))}
            onFocus={() => setHover(k)}
            onBlur={() => setHover((value) => (value === k ? null : value))}
            onClick={(event) => (project ? onOpen(project, event.currentTarget) : onCreate(k))}
            tabIndex={project ? -1 : 0}
          />
          <div className="ows-orb-label">
            {project ? (
              <ProjectName project={project} delay={1.4 + (k % 12) * 0.05} menu={menu} onOpen={onOpen} />
            ) : (
              <AnimatePresence>
                {hover === k && (
                  <motion.span className="ows-orb-free" initial={{ opacity: 0, x: -6, filter: "blur(4px)" }} animate={{ opacity: 1, x: 0, filter: "blur(0px)" }} exit={{ opacity: 0, filter: "blur(4px)" }} transition={SPRING.snappy}>
                    + {t("free")}
                  </motion.span>
                )}
              </AnimatePresence>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
