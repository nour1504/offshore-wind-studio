import { Alert, Button, FileButton, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Table, Text, Textarea, TextInput } from "@mantine/core";
import { useState } from "react";

import { useParseCoordinates } from "../../../api/farms";
import type { Case, CoordinateOptions, TimeSeriesPoint } from "../../../api/types";
import { useFormat, useT } from "../../../i18n";
import { ErrorState } from "../../../ui/States";
import { ExampleFile } from "../../../ui/ExampleFile";
import { messages } from "./messages";
import { isValid, type NewPoint, pointProblems, prefixFor } from "./rules";

export function PointEditor({ initial, index, others, onClose, onApply }: { initial: TimeSeriesPoint; index: number | null; others: string[]; onClose: () => void; onApply: (point: TimeSeriesPoint) => void }) {
  const t = useT(messages);
  const [point, setPoint] = useState<NewPoint>({ ...initial });
  const problems = pointProblems(point, others);
  return <Modal opened onClose={onClose} title={t(index === null ? "editor.addTitle" : "editor.editTitle")} size="md">
    <Stack gap="lg">
      <TextInput label={t("editor.name")} description={t("editor.nameInfo")} value={point.name} maxLength={25} error={problems.name ? t(`editor.problems.${problems.name}`) : undefined} onChange={(event) => setPoint({ ...point, name: event.currentTarget.value })} />
      <SimpleGrid cols={{ base: 1, xs: 2 }}>
        {(["lat", "lon"] as const).map((key) => <NumberInput key={key} label={t(`editor.${key}`)} description={t(`editor.${key}Info`)} value={point[key]} decimalScale={6} min={key === "lat" ? -90 : -180} max={key === "lat" ? 90 : 180} error={problems[key] ? t(`editor.problems.${problems[key]}`) : undefined} onChange={(value) => setPoint({ ...point, [key]: value })} />)}
      </SimpleGrid>
      <TextInput label={t("editor.prefix")} description={t("editor.prefixInfo")} value={point.prefix} maxLength={5} error={problems.prefix ? t(`editor.problems.${problems.prefix}`) : undefined} onChange={(event) => setPoint({ ...point, prefix: event.currentTarget.value })} />
      <Button disabled={!isValid(problems)} onClick={() => onApply({ name: point.name.trim(), prefix: point.prefix, lat: Number(point.lat), lon: Number(point.lon) })}>{t(index === null ? "editor.create" : "editor.save")}</Button>
    </Stack>
  </Modal>;
}

export function PointsImport({ draft, onAdd }: { draft: Case; onAdd: (points: TimeSeriesPoint[]) => void }) {
  const t = useT(messages); const f = useFormat();
  const parser = useParseCoordinates();
  const [text, setText] = useState("");
  const [crs, setCrs] = useState<CoordinateOptions["crs"]>("auto");
  const [epsg, setEpsg] = useState(25832);
  const taken = new Set((draft.time_series?.points ?? []).map((point) => point.prefix.toLowerCase()));
  const points = (parser.data?.points ?? []).map((point, index) => {
    const name = (point.name || t("editor.defaultName", { n: (draft.time_series?.points.length ?? 0) + index + 1 })).slice(0, 25);
    return { name, prefix: prefixFor(name, taken), lat: point.lat, lon: point.lon };
  });
  return <Stack gap="lg">
    <Text size="sm" c="dimmed">{t("paste.text")}</Text>
    <Group gap="sm">
      <FileButton accept=".csv,.txt,.tsv" onChange={(file) => { if (file) void file.text().then((value) => { setText(value); parser.reset(); }); }}>{(props) => <Button {...props} variant="default" size="sm">{t("paste.file")}</Button>}</FileButton>
      <ExampleFile files={["points-mesure.csv"]} onUse={(value) => { setText(value); parser.reset(); }} />
    </Group>
    <Textarea label={t("paste.label")} placeholder={t("paste.placeholder")} minRows={5} value={text} onChange={(event) => { setText(event.currentTarget.value); parser.reset(); }} />
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <Select label={t("paste.format")} value={crs} allowDeselect={false} data={[{ value: "auto", label: t("paste.formats.auto") }, { value: "latlon", label: t("paste.formats.latlon") }, { value: "lonlat", label: t("paste.formats.lonlat") }, { value: "projected", label: t("paste.formats.epsg") }]} onChange={(value) => { setCrs(value as CoordinateOptions["crs"]); parser.reset(); }} />
      {crs === "projected" && <NumberInput label={t("paste.epsg")} value={epsg} min={1} onChange={(value) => { setEpsg(Number(value)); parser.reset(); }} />}
    </SimpleGrid>
    <Group><Button variant={points.length > 0 ? "light" : "filled"} loading={parser.isPending} disabled={!text.trim()} onClick={() => parser.mutate({ text, options: { crs, ...(crs === "projected" ? { epsg } : {}) }, near: { lat: draft.grid.projection.ref_lat, lon: draft.grid.projection.ref_lon } })}>{t("paste.read")}</Button></Group>
    {parser.error && <ErrorState error={parser.error} />}
    {parser.data && <Stack gap="sm">
      <Text size="sm" fw={600} role="status">{t("paste.result", { n: points.length, detected: parser.data.detected })}</Text>
      {points.length > 0 ? <>
        <Table.ScrollContainer minWidth={360}><Table aria-label={t("paste.preview")}><Table.Thead><Table.Tr><Table.Th>{t("ts.name")}</Table.Th><Table.Th>{t("ts.lat")}</Table.Th><Table.Th>{t("ts.lon")}</Table.Th></Table.Tr></Table.Thead><Table.Tbody>{points.slice(0, 8).map((point) => <Table.Tr key={point.prefix}><Table.Td>{point.name}</Table.Td><Table.Td>{f.number(point.lat, 5)}</Table.Td><Table.Td>{f.number(point.lon, 5)}</Table.Td></Table.Tr>)}</Table.Tbody></Table></Table.ScrollContainer>
        {points.length > 8 && <Text size="xs" c="dimmed">{t("paste.more", { n: points.length - 8 })}</Text>}
        <Text size="xs" c="dimmed">{t("paste.prefixNote")}</Text>
        <Button onClick={() => { onAdd(points); parser.reset(); setText(""); }}>{t("paste.addAll", { n: points.length })}</Button>
      </> : <Text size="sm" c="dimmed">{t("paste.nothing")}</Text>}
      {parser.data.skipped.length > 0 && <Alert color="orange">{t("paste.skipped", { lines: parser.data.skipped.join(", ") })}</Alert>}
    </Stack>}
  </Stack>;
}
