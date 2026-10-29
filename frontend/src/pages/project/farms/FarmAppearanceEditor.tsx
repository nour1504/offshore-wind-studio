import { ActionIcon, Button, ColorPicker, ColorSwatch, Group, Modal, Popover, Stack, Text, TextInput } from "@mantine/core";
import { IconCheck, IconPlus } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import type { FarmAppearance, FarmSymbol } from "../../../api/types";
import { defineMessages, useT } from "../../../i18n";
import { FarmSymbolMark } from "../../../ui/map/FarmSymbolMark";
import { FARM_COLORS, FARM_SYMBOLS } from "../../../ui/map/farms";

export const appearanceMessages = defineMessages({
  en: {
    color: "Colour", symbol: "Symbol", other: "Other colour",
    circle: "Dot", cross: "Cross", plus: "Plus", square: "Square", diamond: "Diamond", triangle: "Triangle",
    create: "Create farm", newFarm: "New wind farm", name: "Name", example: "For example CM3",
  },
  fr: {
    color: "Couleur", symbol: "Symbole", other: "Autre couleur",
    circle: "Point", cross: "Croix", plus: "Plus", square: "Carré", diamond: "Losange", triangle: "Triangle",
    create: "Créer le parc", newFarm: "Nouveau parc éolien", name: "Nom", example: "Par exemple CM3",
  },
});

/** Colour and symbol of a farm on the maps: two rows of the same width, swatches then symbols. */
export function FarmAppearanceEditor({ value, index, onChange }: { value: FarmAppearance | undefined; index: number; onChange: (appearance: FarmAppearance) => void }) {
  const t = useT(appearanceMessages);
  const color = value?.color ?? FARM_COLORS[index % FARM_COLORS.length];
  const symbol = !value?.symbol || value.symbol === "auto" ? FARM_SYMBOLS[index % FARM_SYMBOLS.length] : value.symbol;
  const other = !FARM_COLORS.includes(color.toLowerCase());
  const [picked, setPicked] = useState(color);
  useEffect(() => { setPicked(color); }, [color]);
  const set = (change: Partial<{ color: string; symbol: FarmSymbol }>) => onChange({ color: change.color ?? value?.color ?? null, symbol: change.symbol ?? value?.symbol ?? "auto" });
  return <div className="ows-appearance">
    <Text size="xs" c="dimmed" className="ows-appearance-label">{t("color")}</Text>
    <div className="ows-appearance-row" role="radiogroup" aria-label={t("color")}>
      {FARM_COLORS.map((swatch) => <ColorSwatch key={swatch} component="button" type="button" role="radio" aria-checked={swatch === color.toLowerCase()} aria-label={swatch} color={swatch} size={24} withShadow={false} className="ows-swatch" onClick={() => set({ color: swatch })}>
        {swatch === color.toLowerCase() && <IconCheck size={13} stroke={3} color="#fff" />}
      </ColorSwatch>)}
      <Popover position="bottom" shadow="md" withArrow>
        <Popover.Target>
          <ColorSwatch component="button" type="button" role="radio" aria-checked={other} aria-label={t("other")} title={t("other")} color={other ? color : "transparent"} size={24} withShadow={false} className="ows-swatch ows-swatch-other">
            {other ? <IconCheck size={13} stroke={3} color="#fff" /> : <IconPlus size={13} />}
          </ColorSwatch>
        </Popover.Target>
        <Popover.Dropdown p="xs"><ColorPicker format="hex" size="sm" value={picked} onChange={setPicked} onChangeEnd={(choice) => set({ color: choice })} /></Popover.Dropdown>
      </Popover>
    </div>
    <Text size="xs" c="dimmed" className="ows-appearance-label">{t("symbol")}</Text>
    <div className="ows-appearance-row" role="radiogroup" aria-label={t("symbol")}>
      {FARM_SYMBOLS.map((shape) => <ActionIcon key={shape} role="radio" aria-checked={shape === symbol} aria-label={t(shape)} title={t(shape)} variant={shape === symbol ? "default" : "subtle"} color="gray" size={24} className="ows-symbol" onClick={() => set({ symbol: shape })}>
        <FarmSymbolMark symbol={shape} color={color} size={15} />
      </ActionIcon>)}
    </div>
  </div>;
}

export function FarmCreate({ opened, index, defaultName, onClose, onCreate }: { opened: boolean; index: number; defaultName: string; onClose: () => void; onCreate: (name: string, appearance: FarmAppearance) => void }) {
  const t = useT(appearanceMessages);
  const [name, setName] = useState(defaultName);
  const [appearance, setAppearance] = useState<FarmAppearance>({ color: null, symbol: "auto" });
  return <Modal opened={opened} onClose={onClose} title={t("newFarm")} size="md"><Stack gap="lg">
    <TextInput label={t("name")} placeholder={t("example")} maxLength={80} value={name} onChange={(event) => setName(event.currentTarget.value)} data-autofocus />
    <FarmAppearanceEditor value={appearance} index={index} onChange={setAppearance} />
    <Group justify="flex-end"><Button disabled={!name.trim()} onClick={() => onCreate(name.trim(), appearance)}>{t("create")}</Button></Group>
  </Stack></Modal>;
}
