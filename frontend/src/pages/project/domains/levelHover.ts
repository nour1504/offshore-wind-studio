/**
 * The model level under the pointer in the profile of the levels (index from the ground, 0 for
 * the ground itself), shared with the 3D view, which lights that level up.
 */
let current: number | null = null;
const listeners = new Set<() => void>();

export const levelHover = {
  get: () => current,
  set(level: number | null) {
    if (level === current) return;
    current = level;
    listeners.forEach((listener) => listener());
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};
