/**
 * Hash routing: #/projects/<id>/farms. Works from a file, a local server or the desktop window
 * without server-side routes.
 */
import { type AnchorHTMLAttributes, type MouseEvent, useSyncExternalStore } from "react";

import { setNavigationMotion, withViewTransition } from "./motion";

function read(): string {
  return window.location.hash.replace(/^#\/?/, "");
}

// One listener for the whole application: a change of page (not of query parameters alone)
// cross-fades the content as a view transition; every useRoute() then sees the same route
let current = read();
const listeners = new Set<() => void>();
window.addEventListener("hashchange", () => {
  const next = read();
  if (next === current) return;
  const changedPage = next.split("?")[0] !== current.split("?")[0];
  const apply = () => {
    current = next;
    listeners.forEach((listener) => listener());
  };
  if (changedPage) {
    setNavigationMotion(current, next);
    withViewTransition("page", apply);
  }
  else apply();
});

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

function snapshot(): string {
  return current;
}

export interface Route {
  /** Path segments, decoded: ["projects", "horns-rev", "farms"] */
  segments: string[];
  /** Query parameters after "?" in the hash */
  params: URLSearchParams;
}

export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.split("?");
  return {
    segments: path.split("/").filter(Boolean).map(decodeURIComponent),
    params: new URLSearchParams(query),
  };
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, snapshot);
  return parseRoute(hash);
}

export function href(path: string): string {
  return `#/${path.replace(/^\/+/, "")}`;
}

export function navigate(path: string, options: { replace?: boolean } = {}): void {
  const target = href(path);
  if (options.replace) window.location.replace(target);
  else window.location.hash = target;
}

/** Changes query parameters of the current route without adding a history entry. */
export function setParams(changes: Record<string, string | null>): void {
  const route = parseRoute(read());
  for (const [key, value] of Object.entries(changes)) {
    if (value === null) route.params.delete(key);
    else route.params.set(key, value);
  }
  const query = route.params.toString();
  navigate(route.segments.map(encodeURIComponent).join("/") + (query ? `?${query}` : ""), { replace: true });
}

export function Link({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <a
      href={href(to)}
      onClick={(event: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(event);
      }}
      {...rest}
    />
  );
}
