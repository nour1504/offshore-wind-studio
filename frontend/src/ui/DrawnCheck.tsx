/** A tick traced from its foot to its tip: a step done. */
export function DrawnCheck({ size = 16 }: { size?: number }) {
  return (
    <svg className="ows-drawn-check" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <path d="M5 12.5l4.2 4.2L19 7" pathLength={1} />
    </svg>
  );
}
