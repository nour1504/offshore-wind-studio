/**
 * Heights typed in a text field, "100, 150" as [100, 150]: positive, once each, from the lowest.
 * Spaces, semicolons and commas separate them; in French, except one comma between digits in a
 * value without a point: the decimal comma ("92,5" is 92.5 m), as the number fields write it.
 */
export function parseHeights(text: string, lang: "en" | "fr"): number[] {
  const heights = text
    .split(/[;\s]+/)
    .flatMap((token) => {
      const value = token.replace(/^,+|,+$/g, "");
      return lang === "fr" && /^\d+,\d+$/.test(value) ? [value.replace(",", ".")] : value.split(",");
    })
    .filter(Boolean)
    .map(Number)
    .filter((h) => Number.isFinite(h) && h > 0);
  return [...new Set(heights)].sort((a, b) => a - b);
}

/** Heights written back in such a field (to a tenth of a metre), with the decimal mark of the
 * language: "75, 92,5" in French, "75, 92.5" in English; parseHeights reads them again. */
export function writeHeights(heights: readonly number[], lang: "en" | "fr"): string {
  return heights.map((h) => String(Math.round(h * 10) / 10).replace(".", lang === "fr" ? "," : ".")).join(", ");
}
