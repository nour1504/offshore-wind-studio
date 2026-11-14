import type { FarmSymbol } from "../../api/types";
import { SYMBOL_PATHS } from "./farms";

export function FarmSymbolMark({ symbol, color, size = 16 }: { symbol: FarmSymbol; color: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ color, flexShrink: 0 }}><path d={SYMBOL_PATHS[symbol]} fill="currentColor" /></svg>;
}
