/**
 * The turbine catalogue in a window: a search field and one row per model with its power,
 * rotor and hub height in aligned columns. A click adds the model to the project and opens it.
 */
import { Box, Group, Modal, ScrollArea, Stack, Text, TextInput, UnstyledButton } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useMemo, useState } from "react";

import type { CatalogEntry } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { QueryView } from "../../../ui/States";

const messages = defineMessages({
  en: { title: "Turbine catalogue", search: "Search", model: "Model", power: "Power", rotor: "Rotor", hub: "Hub", none: "No model" },
  fr: { title: "Catalogue d'éoliennes", search: "Rechercher", model: "Modèle", power: "Puissance", rotor: "Rotor", hub: "Moyeu", none: "Aucun modèle" },
});

interface Props {
  opened: boolean;
  onClose: () => void;
  catalog: { data: CatalogEntry[] | undefined; isLoading: boolean; error: unknown; refetch: () => unknown };
  onPick: (entry: CatalogEntry) => void;
}

export function CatalogPicker({ opened, onClose, catalog, onPick }: Props) {
  const t = useT(messages);
  const f = useFormat();
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return (catalog.data ?? [])
      .filter((entry) => words.every((word) => entry.name.toLowerCase().includes(word)))
      .sort((a, b) => a.turbine.rated_power_mw - b.turbine.rated_power_mw);
  }, [catalog.data, query]);
  return (
    <Modal opened={opened} onClose={() => { setQuery(""); onClose(); }} title={t("title")} size="lg" yOffset="12vh">
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
                <UnstyledButton key={entry.id} className="ows-catalog-row" onClick={() => { setQuery(""); onPick(entry); }}>
                  <Text size="sm" fw={500} className="ows-catalog-name" truncate>{entry.name}</Text>
                  <Text size="sm" className="ows-catalog-figure ows-num">{f.number(entry.turbine.rated_power_mw, entry.turbine.rated_power_mw < 10 ? 1 : 0)} MW</Text>
                  <Text size="sm" className="ows-catalog-figure ows-num">{f.number(entry.turbine.rotor_diameter_m, 0)} m</Text>
                  <Text size="sm" className="ows-catalog-figure ows-num">{f.number(entry.turbine.hub_height_m, 0)} m</Text>
                </UnstyledButton>
              ))}
            </ScrollArea.Autosize>
          </Box>
        )}</QueryView>
      </Stack>
    </Modal>
  );
}
