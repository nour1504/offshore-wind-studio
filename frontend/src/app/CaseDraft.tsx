/**
 * The project being edited, shared by every project section: one draft, saved or discarded as
 * a whole, with the checks of the draft always up to date.
 */
import { notifications } from "@mantine/notifications";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useCase, useChecks, useSaveCase } from "../api/cases";
import type { Case, Issue } from "../api/types";
import { common } from "../i18n/common";
import { useT } from "../i18n";
import { synchronizePeriod } from "./period";

interface Draft {
  caseId: string;
  /** The saved project */
  saved: Case | undefined;
  /** The project as edited (equal to saved when nothing changed) */
  draft: Case | undefined;
  dirty: boolean;
  loading: boolean;
  error: unknown;
  /** Applies a change to a copy of the draft: update((c) => { c.name = "x" }) */
  update: (change: (c: Case) => void) => void;
  /** Back to the draft before the last change, and forward again */
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  replace: (c: Case) => void;
  save: () => Promise<boolean>;
  discard: () => void;
  saving: boolean;
  /** Why the last save was refused, until the next change */
  saveError: string | null;
  issues: Issue[];
  errors: Issue[];
}

const DraftContext = createContext<Draft | null>(null);

export function CaseDraftProvider({ caseId, children }: { caseId: string; children: ReactNode }) {
  const t = useT(common);
  const query = useCase(caseId);
  const saveMutation = useSaveCase(caseId);
  const [draft, setDraft] = useState<Case | undefined>(undefined);
  const [saveError, setSaveError] = useState<string | null>(null);

  // A new project, or the saved version after a save, replaces the draft
  useEffect(() => {
    setSaveError(null);
    setDraft(query.data ? structuredClone(query.data) : undefined);
  }, [query.data]);

  const dirty = useMemo(
    () => Boolean(draft && query.data && JSON.stringify(draft) !== JSON.stringify(query.data)),
    [draft, query.data],
  );
  const checks = useChecks(draft);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Undo and redo: the drafts before and after; the changes of a field typed in a row (less
  // than 700 ms apart) count as one
  const current = useRef(draft);
  current.current = draft;
  const past = useRef<Case[]>([]);
  const future = useRef<Case[]>([]);
  const lastChange = useRef(0);
  const [, setHistory] = useState(0);
  useEffect(() => {
    past.current = [];
    future.current = [];
    setHistory((n) => n + 1);
  }, [caseId]);

  /** A new draft, the previous one kept for undo. */
  const commit = useCallback((before: Case, next: Case) => {
    setSaveError(null);
    const now = Date.now();
    if (now - lastChange.current > 700) past.current = [...past.current.slice(-99), before];
    lastChange.current = now;
    future.current = [];
    current.current = next;
    setDraft(next);
    setHistory((n) => n + 1);
  }, []);

  const update = useCallback((change: (c: Case) => void) => {
    const before = current.current;
    if (!before) return;
    const next = structuredClone(before);
    change(next);
    synchronizePeriod(before, next);
    commit(before, next);
  }, [commit]);

  const replace = useCallback((next: Case) => {
    if (current.current) commit(current.current, next);
    else setDraft(next);
  }, [commit]);

  const step = useCallback((from: React.MutableRefObject<Case[]>, to: React.MutableRefObject<Case[]>) => {
    const target = from.current[from.current.length - 1];
    const now = current.current;
    if (!target || !now) return;
    from.current = from.current.slice(0, -1);
    to.current = [...to.current, now];
    lastChange.current = 0;
    current.current = target;
    setDraft(target);
    setHistory((n) => n + 1);
  }, []);
  const undo = useCallback(() => step(past, future), [step]);
  const redo = useCallback(() => step(future, past), [step]);

  // Ctrl+Z, Ctrl+Y (or Ctrl+Shift+Z) outside the fields, where the browser undoes the typing
  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && (target.closest("input, textarea, select, [contenteditable='true']"))) return;
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) { event.preventDefault(); undo(); }
      else if (key === "y" || (key === "z" && event.shiftKey)) { event.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [undo, redo]);

  const save = useCallback(async () => {
    if (!draft) return false;
    try {
      await saveMutation.mutateAsync(draft);
      notifications.show({ color: "teal", message: t("saved") });
      return true;
    } catch (error) {
      setSaveError((error as Error).message);
      return false;
    }
  }, [draft, saveMutation, t]);

  const value: Draft = {
    caseId,
    saved: query.data,
    draft,
    dirty,
    loading: query.isLoading,
    error: query.error,
    update,
    undo,
    redo,
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
    replace,
    save,
    discard: () => { setSaveError(null); setDraft(query.data ? structuredClone(query.data) : undefined); },
    saving: saveMutation.isPending,
    saveError,
    issues: checks.data ?? [],
    errors: (checks.data ?? []).filter((i) => i.severity === "error"),
  };
  return <DraftContext.Provider value={value}>{children}</DraftContext.Provider>;
}

export function useDraft(): Draft {
  const value = useContext(DraftContext);
  if (!value) throw new Error("useDraft outside a project");
  return value;
}

/** What the server's checks say about one field (an error first, else a warning), in a few
    words; nothing outside a project or when the field is fine. */
export function useFieldIssue(field: string | undefined): { severity: "error" | "warning"; text: string } | null {
  const value = useContext(DraftContext);
  if (!field || !value) return null;
  const about = value.issues.filter((issue) => issue.field === field);
  const found = about.find((issue) => issue.severity === "error") ?? about.find((issue) => issue.severity === "warning");
  return found ? { severity: found.severity as "error" | "warning", text: found.short ?? found.message } : null;
}

/** The draft when it is loaded; pages render a loading state before that. */
export function useLoadedDraft(): Draft & { draft: Case } {
  const value = useDraft();
  if (!value.draft) throw new Error("Project not loaded yet");
  return value as Draft & { draft: Case };
}
