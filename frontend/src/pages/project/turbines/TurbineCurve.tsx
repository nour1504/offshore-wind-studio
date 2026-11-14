/**
 * The curves of a turbine model, one row: the rated wind speed on the left with the speeds of
 * production and the highest power coefficient; on the right the two charts, then the points in
 * three tabs: the table to edit, a paste from a spreadsheet or a file, and the table WRF reads.
 */
import { ActionIcon, Alert, Button, Checkbox, Code, FileButton, Group, List, ScrollArea, SegmentedControl, SimpleGrid, Stack, Table, Tabs, Text, Textarea } from "@mantine/core";
import { IconTrash } from "@tabler/icons-react";
import { useState } from "react";

import { useWrfTable } from "../../../api/turbines";
import type { CurvePoint, TurbineType } from "../../../api/types";
import { useFormat, useT } from "../../../i18n";
import { common } from "../../../i18n/common";
import { ExampleFile } from "../../../ui/ExampleFile";
import { Spec } from "../../../ui/Fold";
import { GlideTabsList } from "../../../ui/GlideTabs";
import { HelpLink } from "../../../ui/Help";
import { downloadText } from "../../../ui/download";
import { Confirm, FieldLabel, NumberField } from "../../../ui/Inputs";
import { CHART_COLORS, cssColor } from "../../../ui/chart";
import { ErrorState, QueryView } from "../../../ui/States";
import { Curves } from "../analyses/Charts";
import { BETZ_LIMIT, checkTurbine, hasErrors, metrics, parseCurve, powerCoefficient, sortedCurve, toCurve, type PowerUnit } from "./curve";
import { messages } from "./messages";

const UNITS: PowerUnit[] = ["kW", "MW", "W"];

export function TurbineCurve({ turbine, number, onChange }: { turbine: TurbineType; number: number; onChange: (patch: Partial<TurbineType>) => void }) {
  const t = useT(messages);
  const tc = useT(common);
  const f = useFormat();
  const [tab, setTab] = useState<string | null>("points");
  const [pasted, setPasted] = useState("");
  const [unit, setUnit] = useState<PowerUnit>("kW");
  const [fileError, setFileError] = useState(false);
  const [copyError, setCopyError] = useState<unknown>(null);
  const [copied, setCopied] = useState(false);
  const [setRated, setSetRated] = useState(true);
  const problems = checkTurbine(turbine);
  const table = useWrfTable(hasErrors(problems) ? null : turbine);
  const m = metrics(turbine);
  const parsed = parseCurve(pasted);
  const curve = parsed.ok ? toCurve(parsed.rows, parsed.headerUnit ?? unit) : [];
  // A curve from another turbine: offer to take its maximum as the rated power (a WRF table brings its own)
  const curveMw = curve.length ? Math.round(Math.max(...curve.map((point) => point.power_kw))) / 1000 : 0;
  const ratedDiffers = parsed.ok && !parsed.characteristics && curveMw > 0 && Math.abs(curveMw - turbine.rated_power_mw) > 0.001;
  // Wind speed to scale: rows every 0.1 m/s near rated speed do not stretch the curves
  const along = (y: (point: CurvePoint) => number | null) => turbine.curve.map((point) => ({ x: point.wind_speed, y: y(point) ?? NaN }));
  const speeds = turbine.curve.map((point) => point.wind_speed).filter(Number.isFinite);
  const speedAxis = { label: t("curve.speed"), unit: "m/s", digits: 1 };
  // Wind speeds as written in the curve: 3, 11.4, 3.25
  const speed = (value: number) => f.number(value, Number.isInteger(value) ? 0 : Number.isInteger(value * 10) ? 1 : 2);
  const problemText = (problem: ReturnType<typeof checkTurbine>[number]) => t(`problems.${problem.code}`, {
    rows: "rows" in problem ? problem.rows.join(", ") : "",
    speeds: "speeds" in problem ? f.numbers(problem.speeds, 2) : "",
    max: "maxKw" in problem ? f.number(problem.maxKw, 0) : "",
    rated: "ratedKw" in problem ? f.number(problem.ratedKw, 0) : "",
  });
  const replace = () => {
    if (!parsed.ok) return;
    onChange({ curve, ...(parsed.characteristics ?? {}), ...(ratedDiffers && setRated ? { rated_power_mw: curveMw } : {}) });
    setPasted("");
    setTab("points");
  };
  const setPoint = (index: number, key: keyof CurvePoint, value: number) => {
    const next: CurvePoint[] = structuredClone(turbine.curve);
    next[index][key] = value;
    onChange({ curve: next });
  };
  const addRow = () => {
    const last = turbine.curve.at(-1);
    onChange({ curve: [...turbine.curve, { wind_speed: (last?.wind_speed ?? -1) + 1, power_kw: last?.power_kw ?? 0, thrust_coefficient: last?.thrust_coefficient ?? 0.8 }] });
  };

  return (
    <Spec
      label={t("metrics.rated")}
      value={m.rated === null ? "–" : speed(m.rated)}
      unit="m/s"
      detail={<>
        {m.cutIn !== null && m.cutOut !== null && <span title={t("metrics.ratedInfo")}>{t("metrics.ratedHint", { cutIn: speed(m.cutIn), cutOut: speed(m.cutOut) })}</span>}
        {m.maxCp !== null && (
          <span className={m.maxCp > BETZ_LIMIT ? "ows-spec-bad" : undefined} title={`${t("metrics.maxCpHint", { ws: m.maxCpSpeed === null ? "–" : speed(m.maxCpSpeed), betz: f.number(BETZ_LIMIT, 3) })} · ${t("metrics.maxCpInfo")}`}>
            {t("rows.maxCp", { cp: f.number(m.maxCp, 3) })}
          </span>
        )}
      </>}
      tools={<HelpLink topic="power-curve" />}
    >
      {problems.length > 0 && (
        <Alert color={hasErrors(problems) ? "red" : "orange"} variant="light" title={t(hasErrors(problems) ? "problems.errors" : "problems.warnings")}>
          <List size="sm">{problems.map((problem, index) => <List.Item key={index}>{problemText(problem)}</List.Item>)}</List>
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl">
        <Stack gap="xs">
          <Text size="sm" fw={600}>{t("charts.power")}</Text>
          <Curves height={230} label={t("charts.powerLabel")} x={speedAxis} y={{ label: t("curve.power"), unit: "kW", digits: 0, from0: true }}
            curves={[{ key: "power", label: t("charts.powerSeries"), color: cssColor(CHART_COLORS.main), kind: "line", points: along((point) => point.power_kw) }]} />
        </Stack>
        <Stack gap="xs">
          <Text size="sm" fw={600}>{t("charts.coefficients")}</Text>
          <Curves height={230} label={t("charts.coefficientsLabel")} x={speedAxis} y={{ label: "", unit: "", digits: 3, from0: true }}
            curves={[
              { key: "ct", label: t("charts.ctSeries"), color: cssColor("forest.7"), kind: "line", points: along((point) => point.thrust_coefficient) },
              { key: "cp", label: t("charts.cpSeries"), color: cssColor("forest.4"), kind: "line", dashed: true, points: along((point) => powerCoefficient(turbine, point)) },
              ...(speeds.length ? [{ key: "betz", label: t("charts.betz"), color: cssColor(CHART_COLORS.limit), kind: "line" as const, dashed: true, points: [{ x: Math.min(...speeds), y: BETZ_LIMIT }, { x: Math.max(...speeds), y: BETZ_LIMIT }] }] : []),
            ]} />
        </Stack>
      </SimpleGrid>

      <Tabs value={tab} onChange={setTab}>
        <GlideTabsList>
          <Tabs.Tab value="points">{t("curve.points")}</Tabs.Tab>
          <Tabs.Tab value="paste">{t("curve.paste")}</Tabs.Tab>
          <Tabs.Tab value="wrf">{t("wrf.title")}</Tabs.Tab>
        </GlideTabsList>

        <Tabs.Panel value="points" pt="md">
          <Stack gap="sm">
            <ScrollArea.Autosize mah={440} type="auto" offsetScrollbars>
              <Table stickyHeader aria-label={t("curve.tableLabel", { n: number })} className="ows-curve-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("curve.speed")} (m/s)</Table.Th>
                    <Table.Th>{t("curve.power")} (kW)</Table.Th>
                    <Table.Th>{t("curve.ct")}</Table.Th>
                    <Table.Th>{t("curve.cp")}</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {turbine.curve.map((point, index) => (
                    <Table.Tr key={index}>
                      {(["wind_speed", "power_kw", "thrust_coefficient"] as const).map((key) => (
                        <Table.Td key={key}>
                          <NumberField size="xs" min={0} aria-label={t(key === "wind_speed" ? "curve.speedRow" : key === "power_kw" ? "curve.powerRow" : "curve.ctRow", { n: index + 1 })} value={point[key]} onValue={(value) => setPoint(index, key, value)} />
                        </Table.Td>
                      ))}
                      <Table.Td className="ows-num">{f.number(powerCoefficient(turbine, point), 3)}</Table.Td>
                      <Table.Td>
                        <ActionIcon variant="subtle" color="red" aria-label={t("curve.removeRow", { n: index + 1 })} onClick={() => onChange({ curve: turbine.curve.filter((_, i) => i !== index) })}><IconTrash size={16} /></ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea.Autosize>
            <Group gap="xs">
              <Button size="xs" variant="default" onClick={addRow}>{t("curve.add")}</Button>
              <Confirm title={t("curve.sort")} text={t("problems.notIncreasing", { rows: "" })} onConfirm={() => onChange({ curve: sortedCurve(turbine.curve) })} color="orange">
                {(open) => <Button size="xs" variant="default" onClick={open}>{t("curve.sort")}</Button>}
              </Confirm>
            </Group>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="paste" pt="md">
          <Stack gap="sm">
            <Textarea
              label={<FieldLabel label={t("paste.label")} info={t("paste.help")} />}
              autosize
              minRows={6}
              maxRows={14}
              value={pasted}
              onChange={(event) => setPasted(event.currentTarget.value)}
              error={pasted.trim() && !parsed.ok ? t(`paste.${parsed.error}`, { line: "line" in parsed ? parsed.line : "", text: "text" in parsed ? parsed.text : "" }) : undefined}
              styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }}
            />
            <Group justify="space-between" wrap="wrap" gap="sm">
              <Group gap="sm" wrap="wrap">
                <Group gap={8} wrap="nowrap">
                  <Text size="sm" c="dimmed">{t("paste.unit")}</Text>
                  <SegmentedControl size="xs" aria-label={t("paste.unit")} data={UNITS} value={parsed.ok && parsed.headerUnit ? parsed.headerUnit : unit} disabled={parsed.ok && Boolean(parsed.headerUnit)} onChange={(value) => setUnit(value as PowerUnit)} />
                </Group>
                <FileButton accept=".csv,.txt,.tbl" onChange={(file) => { if (file) void file.text().then((text) => { setPasted(text); setFileError(false); }).catch(() => setFileError(true)); }}>
                  {(props) => <Button {...props} size="xs" variant="default">{t("paste.file")}</Button>}
                </FileButton>
                <ExampleFile files={["courbe-puissance.csv", "wind-turbine-2.tbl"]} onUse={setPasted} />
              </Group>
              <Confirm title={t("paste.replace")} onConfirm={replace} color="orange">
                {(open) => <Button size="xs" disabled={!parsed.ok} onClick={open}>{t("paste.replace")}</Button>}
              </Confirm>
            </Group>
            {fileError && <Text size="sm" c="red">{t("paste.fileError")}</Text>}
            {parsed.ok && (
              <Text size="sm" c="dimmed">
                {t("paste.read", { n: curve.length, from: speed(curve[0].wind_speed), to: speed(curve.at(-1)!.wind_speed), max: f.number(Math.max(...curve.map((point) => point.power_kw)), 0) })}
                {parsed.characteristics ? ` ${t("paste.wrf")}` : ""}
              </Text>
            )}
            {ratedDiffers && <Checkbox size="sm" checked={setRated} onChange={(event) => setSetRated(event.currentTarget.checked)} label={t("paste.setRated", { mw: f.number(curveMw, 3) })} />}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="wrf" pt="md">
          {hasErrors(problems) ? <Text size="sm" c="dimmed">{t("wrf.fixFirst")}</Text> : (
            <QueryView query={table}>
              {(text) => (
                <Stack gap="sm">
                  <Group justify="space-between" wrap="wrap" gap="sm">
                    <Text size="sm" ff="monospace" c="dimmed"><FieldLabel label={`wind-turbine-${number}.tbl`} info={t("wrf.description", { n: number })} /></Text>
                    <Group gap="xs">
                      <Button size="xs" variant="default" onClick={async () => { try { await navigator.clipboard.writeText(text); setCopied(true); setCopyError(null); } catch (error) { setCopyError(error); } }}>{tc(copied ? "copied" : "copy")}</Button>
                      <Button size="xs" variant="default" onClick={() => downloadText(text, `wind-turbine-${number}.tbl`, "text/plain;charset=utf-8")}>{t("wrf.download")}</Button>
                    </Group>
                  </Group>
                  <Code block style={{ maxHeight: 360, overflow: "auto" }} aria-label={t("wrf.label", { n: number })}>{text}</Code>
                </Stack>
              )}
            </QueryView>
          )}
          {Boolean(copyError) && <ErrorState error={copyError} />}
        </Tabs.Panel>
      </Tabs>
    </Spec>
  );
}
