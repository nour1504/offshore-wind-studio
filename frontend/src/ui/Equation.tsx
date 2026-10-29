/**
 * Equations typeset with KaTeX (TeX source, rendered once), with a few words above each one: what
 * it gives. The equations are centred in one column, the words above them small and muted.
 */
import "katex/dist/katex.min.css";

import { Stack, Text } from "@mantine/core";
import katex from "katex";
import { useMemo } from "react";

export interface EquationLine {
  /** A few words: what the equation gives */
  caption?: string;
  tex: string;
}

export function Equation({ tex }: { tex: string }) {
  const html = useMemo(() => katex.renderToString(tex, { displayMode: true, throwOnError: false, output: "html" }), [tex]);
  return <div className="ows-equation" dangerouslySetInnerHTML={{ __html: html }} />;
}

export function Equations({ lines }: { lines: EquationLine[] }) {
  return (
    <Stack gap={22} className="ows-equations">
      {lines.map((line) => (
        <Stack key={line.tex} gap={2} align="center">
          {line.caption && <Text size="xs" fw={600} c="dimmed" ta="center">{line.caption}</Text>}
          <Equation tex={line.tex} />
        </Stack>
      ))}
    </Stack>
  );
}
