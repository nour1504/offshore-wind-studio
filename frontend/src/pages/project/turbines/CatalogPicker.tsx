/**
 * The turbine catalogue in a window: a search field and one row per model with its power,
 * rotor and hub height in aligned columns. A click adds the model to the project and opens it.
 * Under the list, the power curve of the model pointed at, traced again for each model.
 */
import { Box, Group, ScrollArea, Stack, Text, TextInput, UnstyledButton } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import { IconSearch } from "@tabler/icons-react";
import { useMemo, useState } from "react";

import type { CatalogEntry } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { QueryView } from "../../../ui/States";
import { Window } from "../../../ui/Window";

const messages = defineMessages({
  en: { title: "Turbine catalog", search: "Search", model: "Type", power: "Power", rotor: "Rotor", hub: "Hub", none: "No type" },
  fr: { title: "Catalogue d'éoliennes", search: "Rechercher", model: "Type", power: "Puissance", rotor: "Rotor", hub: "Moyeu", none: "Aucun type" },
});

interface Props {
  opened: boolean;
  onClose: () => void;
  catalog: { data: CatalogEntry[] | undefined; isLoading: boolean; error: unknown; refetch: () => unknown };
  onPick: (entry: CatalogEntry) => void;
}

const CURVE_HEIGHT = 92;

/** The power curve of a model, from its own points (power against wind speed). */
function CurvePreview({ entry }: { entry: CatalogEntry }) {
  const f = useFormat();
  const { ref, width } = useElementSize();
  const points = entry.turbine.curve.filter((p) => Number.isFinite(p.wind_speed) && Number.isFinite(p.power_kw)).sort((a, b) => a.wind_speed - b.wind_speed);
  const vmax = Math.max(25, points.at(-1)?.wind_speed ?? 25);
  const pmax = Math.max(1, ...points.map((p) => p.power_kw));
  const x = (v: number) => 14 + (v / vmax) * Math.max(0, width - 28);
  const y = (p: number) => CURVE_HEIGHT - 18 - (p / pmax) * (CURVE_HEIGHT - 32);
  const line = points.map((p, k) => `${k ? "L" : "M"} ${x(p.wind_speed).toFixed(1)} ${y(p.power_kw).toFixed(1)}`).join(" ");
  return (
    <div ref={ref} className="ows-catalog-curve">
      {width > 0 && points.length > 1 && (
        <svg width={width} height={CURVE_HEIGHT} role="img" aria-label={`${entry.name} · ${f.number(pmax / 1000, 1)} MW`}>
          <line x1={14} x2={width - 14} y1={CURVE_HEIGHT - 18} y2={CURVE_HEIGHT - 18} stroke="var(--ows-border-strong)" />
          <path key={entry.id} d={line} pathLength={1} className="ows-curve-draw" fill="none" stroke="var(--mantine-primary-color-filled)" strokeWidth={2} strokeLinejoin="round" />
          <text x={14} y={12} fontSize={12} fill="var(--ows-muted)" className="ows-num">{f.number(pmax / 1000, 1)} MW</text>
          <text x={width - 14} y={CURVE_HEIGHT - 4} textAnchor="end" fontSize={12} fill="var(--ows-muted)" className="ows-num">{f.number(vmax, 0)} m/s</text>
        </svg>
      )}
    </div>
  );
}

export function CatalogPicker({ opened, onClose, catalog, onPick }: Props) {
  const t = useT(messages);
  const f = useFormat();
  const [query, setQuery] = useState("");
  const [pointed, setPointed] = useState<CatalogEntry | null>(null);
  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return (catalog.data ?? [])
      .filter((entry) => words.every((word) => entry.name.toLowerCase().includes(word)))
      .sort((a, b) => a.turbine.rated_power_mw - b.turbine.rated_power_mw);
  }, [catalog.data, query]);
  return (
    <Window opened={opened} onClose={() => { setQuery(""); onClose(); }} title={t("title")} size="lg" yOffset="12vh">
      <Stack gap="sm">
        <TextInput placeholder={t("search")} aria-label={t("search")} leftSection={<IconSearch size={16} />} value={query} onChange={(event) => setQuery(event.currentTarget.value)} data-autofocus />
        <QueryView query={catalog}>{() => (
          <Box className="ows-catalog">
            <Group className="ows-catalog-row ows-catalog-head" wrap="nowrap">
              <Text size="xs" fw={600} c="dimmed" className="ows-catalog-name">{t("model")}</Text>
              <Text size="xs" fw={600} c="dimmed" className="ows-catalog-figure">{t("power")}</Text>
              <Text size="xs" fw={600} c="dimmed" className="ows-catalog-figure">{t("rotor")}</Text>
              <Text size="xs" fw={600} c="dimmed" className="ows-catalog-figure">{t("hub")}</Text>
            </Group>
            <ScrollArea.Autosize mah={420} type="auto" offsetScrollbars>
              {shown.length === 0 && <Text size="sm" fw={600} c="dimmed" ta="center" py="lg">{t("none")}</Text>}
              {shown.map((entry) => (
                <UnstyledButton key={entry.id} className="ows-catalog-row" onPointerEnter={() => setPointed(entry)} onFocus={() => setPointed(entry)} onClick={() => { setQuery(""); onPick(entry); }}>
                  <Text size="sm" fw={500} className="ows-catalog-name" truncate>{entry.name}</Text>
                  <Text size="sm" className="ows-catalog-figure ows-num">{f.number(entry.turbine.rated_power_mw, entry.turbine.rated_power_mw < 10 ? 1 : 0)} MW</Text>
                  <Text size="sm" className="ows-catalog-figure ows-num">{f.number(entry.turbine.rotor_diameter_m, 0)} m</Text>
                  <Text size="sm" className="ows-catalog-figure ows-num">{f.number(entry.turbine.hub_height_m, 0)} m</Text>
                </UnstyledButton>
              ))}
            </ScrollArea.Autosize>
            {(pointed && shown.includes(pointed) ? pointed : shown[0]) && <CurvePreview entry={(pointed && shown.includes(pointed) ? pointed : shown[0]) as CatalogEntry} />}
          </Box>
        )}</QueryView>
      </Stack>
    </Window>
  );
}
