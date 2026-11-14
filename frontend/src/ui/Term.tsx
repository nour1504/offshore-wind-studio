/**
 * One short, plain definition per technical word, the same everywhere in the application.
 * <Term id="pbl">label</Term> shows the label with a small info mark; hovering or focusing it
 * shows the definition. Pages never write their own definition of these words.
 */
import { IconInfoCircle } from "@tabler/icons-react";
import { Text, Tooltip } from "@mantine/core";
import type { ReactNode } from "react";

import { defineMessages, useT } from "../i18n";

export const glossary = defineMessages({
  en: {
    defs: {
      pbl: "Boundary layer scheme: turbulent mixing near the surface.",
      microphysics: "Cloud and precipitation scheme.",
      cumulus: "Subgrid convection scheme, usually off below about 4 km.",
      radiation: "Shortwave and longwave radiation schemes.",
      landSurface: "Heat and moisture exchanges with the ground.",
      fitch: "WRF wind-farm parameterization: turbine drag and TKE source.",
      mav: "Fitch variant that adds the wakes inside a grid cell.",
    },
  },
  fr: {
    defs: {
      pbl: "Schéma de couche limite : mélange turbulent près de la surface.",
      microphysics: "Schéma des nuages et des précipitations.",
      cumulus: "Convection sous-maille, en général désactivée sous 4 km environ.",
      radiation: "Schémas de rayonnement solaire et infrarouge.",
      landSurface: "Échanges de chaleur et d'humidité avec le sol.",
      fitch: "Paramétrisation des parcs de WRF : traînée des éoliennes et source de TKE.",
      mav: "Variante de Fitch qui ajoute les sillages internes à une maille.",
    },
  },
});

export type TermId = keyof typeof glossary.en.defs;

// The definition unfolds under the word, from its top edge
const unfold = {
  in: { opacity: 1, transform: "translateY(0)", clipPath: "inset(0 0 0 0 round 6px)" },
  out: { opacity: 0, transform: "translateY(-4px)", clipPath: "inset(0 0 100% 0 round 6px)" },
  transitionProperty: "opacity, transform, clip-path",
};

/** A technical word with its definition on hover or focus: a highlight sweeps across the word first. */
export function Term({ id, children }: { id: TermId; children: ReactNode }) {
  const t = useT(glossary);
  return (
    <Tooltip label={t(`defs.${id}`)} maw={300} multiline position="bottom-start" openDelay={60} transitionProps={{ transition: unfold, duration: 220 }} events={{ hover: true, focus: true, touch: true }}>
      <Text component="span" inherit tabIndex={0} className="ows-term" style={{ cursor: "help", display: "inline-flex", alignItems: "center", gap: 4 }}>
        {children}
        <IconInfoCircle size={13} style={{ color: "var(--ows-muted)", flexShrink: 0 }} aria-hidden />
      </Text>
    </Tooltip>
  );
}
