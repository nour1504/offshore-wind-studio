/**
 * Adding turbines to a farm, as in a layout tool: the settings on the left, the map preview on the
 * right, and at the bottom the key figures (turbines, installed power, spacing in rotor
 * diameters, area) with Add and Replace. Four ways, the same frame:
 * - paste: coordinates from a spreadsheet or a text file, read as they are typed;
 * - zone: a polygon drawn on the map, filled with a metric lattice by the server
 *   (core/geo.py, turbine_layout): spacing along and between the rows, orientation, staggered
 *   rows, setback from the edge; previewed as the settings change;
 * - grid: rows and columns around a centre placed on the map, the same settings;
 * - file: a GeoJSON, KML or shapefile: its points as turbines, or one of its polygons filled
 *   like a drawn zone.
 * The orientation is the angle of the rows clockwise from east, the same everywhere.
 */
import { Alert, Box, Button, FileButton, Grid, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconArrowBackUp, IconClipboardText, IconFileImport, IconGridDots, IconMapPin, IconPolygon, IconX } from "@tabler/icons-react";
import { useEffect, useMemo, useState } from "react";

import { useGeoImport, useGeoLayout, useParseCoordinates, type GeoLayoutRequest } from "../../../api/farms";
import type { Case, CoordinateOptions, Farm, FeatureCollection, Turbine } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { ExampleFile } from "../../../ui/ExampleFile";
import { Confirm, FieldLabel, NumberField } from "../../../ui/Inputs";
import { PathInput } from "../../../ui/PathInput";
import { ErrorState } from "../../../ui/States";
import { ProjectMap } from "../../../ui/map/ProjectMap";
import { useRunningNumber } from "../../../ui/Motion";
import { farmMessages } from "./messages";
import { gridLayout, innermostCentre, newTurbine, type TypeInfo } from "./model";

const messages = defineMessages({
  en: {
    title: "Add turbines · {name}",
    modes: { paste: "Paste", zone: "Zone", grid: "Grid", file: "GIS file" },
    coordinates: "Coordinates",
    coordinatesInfo: "One turbine per line: name; latitude; longitude; model.",
    openFile: "Open a file",
    system: "Coordinate system",
    points: "{n|# turbine read|# turbines read} · {detected}",
    skipped: "Lines skipped: {lines}",
    draw: "Draw",
    finish: "Finish",
    undo: "Undo",
    clear: "Clear",
    corners: "{n|# corner|# corners}",
    spacing: "Spacing",
    spacingInfo: "Between neighbouring turbines of a row.",
    across: "Between rows",
    acrossInfo: "Between two neighbouring rows.",
    orientation: "Orientation",
    orientationInfo: "Angle of the rows, clockwise from east.",
    stagger: "Layout",
    aligned: "Aligned",
    staggered: "Staggered",
    staggerInfo: "Every other row shifted by half a spacing.",
    setback: "Edge setback",
    setbackInfo: "No turbine closer than this to the edge of the zone.",
    centre: "Centre",
    place: "Place on the map",
    placing: "Click the centre",
    lat: "Latitude",
    lon: "Longitude",
    rows: "Rows",
    columns: "Columns",
    model: "Model",
    path: "File",
    crs: "Projection (optional)",
    crsInfo: "EPSG code or WKT. Shapefile: .prj required, otherwise give the projection here. Keep .shp, .shx and .dbf together.",
    read: "Read",
    zone: "Zone",
    filePoints: "Points of the file",
    fileZone: "Fill a zone",
    turbines: "{n|# turbine|# turbines}",
    add: "Add",
    replace: "Replace",
    replaceTitle: "Replace the {n|turbine|# turbines} of {name}?",
    replaceText: "{m|# turbine|# turbines} instead.",
    none: "No position",
    diameters: "{v} D",
    map: "Preview of the turbines",
  },
  fr: {
    title: "Ajouter des éoliennes · {name}",
    modes: { paste: "Coller", zone: "Zone", grid: "Grille", file: "Fichier SIG" },
    coordinates: "Coordonnées",
    coordinatesInfo: "Une éolienne par ligne : nom ; latitude ; longitude ; modèle.",
    openFile: "Ouvrir un fichier",
    system: "Système de coordonnées",
    points: "{n|# éolienne lue|# éoliennes lues} · {detected}",
    skipped: "Lignes ignorées : {lines}",
    draw: "Dessiner",
    finish: "Terminer",
    undo: "Annuler",
    clear: "Effacer",
    corners: "{n|# sommet|# sommets}",
    spacing: "Espacement",
    spacingInfo: "Entre éoliennes voisines d'une rangée.",
    across: "Entre rangées",
    acrossInfo: "Entre deux rangées voisines.",
    orientation: "Orientation",
    orientationInfo: "Angle des rangées, dans le sens horaire depuis l'est.",
    stagger: "Disposition",
    aligned: "Alignée",
    staggered: "Quinconce",
    staggerInfo: "Une rangée sur deux décalée d'un demi-espacement.",
    setback: "Marge au bord",
    setbackInfo: "Aucune éolienne plus près que cela du bord de la zone.",
    centre: "Centre",
    place: "Placer sur la carte",
    placing: "Cliquez le centre",
    lat: "Latitude",
    lon: "Longitude",
    rows: "Rangées",
    columns: "Colonnes",
    model: "Modèle",
    path: "Fichier",
    crs: "Projection (facultatif)",
    crsInfo: "Code EPSG ou WKT. Shapefile : .prj requis, sinon indiquer la projection ici. Garder .shp, .shx et .dbf ensemble.",
    read: "Lire",
    zone: "Zone",
    filePoints: "Points du fichier",
    fileZone: "Remplir une zone",
    turbines: "{n|# éolienne|# éoliennes}",
    add: "Ajouter",
    replace: "Remplacer",
    replaceTitle: "Remplacer {n|l'éolienne|les # éoliennes} de {name} ?",
    replaceText: "{m|# éolienne|# éoliennes} à la place.",
    none: "Aucune position",
    diameters: "{v} D",
    map: "Aperçu des éoliennes",
  },
});

type Mode = "paste" | "zone" | "grid" | "file";
interface Lattice { spacing: number; across: number; orientation: number; stagger: boolean; setback: number }

/** Spacing, rows, orientation and stagger: the settings of a zone, a file polygon and a grid. */
function LatticeFields({ value, onChange, rotor, setback = true }: { value: Lattice; onChange: (value: Lattice) => void; rotor: number | null; setback?: boolean }) {
  const t = useT(messages);
  const f = useFormat();
  const diameters = (metres: number) => (rotor ? t("diameters", { v: f.number(metres / rotor, 1) }) : undefined);
  const set = (change: Partial<Lattice>) => onChange({ ...value, ...change });
  return (
    <Stack gap="sm">
      <SimpleGrid cols={2} spacing="sm">
        <NumberField label={<FieldLabel label={t("spacing")} info={t("spacingInfo")} />} unit="m" min={1} allowDecimal={false} value={value.spacing} description={diameters(value.spacing)} inputWrapperOrder={["label", "input", "description", "error"]} onValue={(spacing) => set({ spacing })} />
        <NumberField label={<FieldLabel label={t("across")} info={t("acrossInfo")} />} unit="m" min={1} allowDecimal={false} value={value.across} description={diameters(value.across)} inputWrapperOrder={["label", "input", "description", "error"]} onValue={(across) => set({ across })} />
        <NumberField label={<FieldLabel label={t("orientation")} info={t("orientationInfo")} />} unit="°" min={-360} max={360} decimalScale={1} value={value.orientation} onValue={(orientation) => set({ orientation })} />
        <Select label={<FieldLabel label={t("stagger")} info={t("staggerInfo")} />} value={value.stagger ? "staggered" : "aligned"} allowDeselect={false} data={[{ value: "aligned", label: t("aligned") }, { value: "staggered", label: t("staggered") }]} onChange={(choice) => set({ stagger: choice === "staggered" })} />
      </SimpleGrid>
      {setback && <NumberField label={<FieldLabel label={t("setback")} info={t("setbackInfo")} />} unit="m" min={0} allowDecimal={false} value={value.setback} onValue={(margin) => set({ setback: margin })} />}
    </Stack>
  );
}

const ring = (vertices: [number, number][]) => (vertices.length >= 3 ? [...vertices, vertices[0]] : []);
const layoutBody = (rings: [number, number][][], lattice: Lattice, type: number): GeoLayoutRequest => ({
  polygon: rings[0],
  holes: rings.slice(1),
  spacing_m: lattice.spacing,
  spacing_across_m: lattice.across,
  rotation_deg: lattice.orientation,
  stagger: lattice.stagger ? 0.5 : 0,
  setback_m: lattice.setback,
  turbine_type: type,
});

export function AddTurbines({ draft, farm, types, info, geometry, onApply }: {
  draft: Case;
  farm: Farm;
  types: { value: string; label: string }[];
  info: Map<number, TypeInfo>;
  geometry: FeatureCollection | undefined;
  onApply: (items: Turbine[], replace: boolean) => void;
}) {
  const t = useT(messages);
  const tf = useT(farmMessages);
  const f = useFormat();
  const centreOfDomain = innermostCentre(draft, geometry);
  const [mode, setMode] = useState<Mode>("paste");
  const [type, setType] = useState(types[0]?.value ?? "1");
  const model = info.get(Number(type));
  const rotor = model?.rotorM ?? null;
  const usual = rotor ? Math.round(7 * rotor / 10) * 10 : 800;
  const [lattice, setLattice] = useState<Lattice>({ spacing: usual, across: usual, orientation: 0, stagger: false, setback: 0 });

  // Paste: read as typed
  const parser = useParseCoordinates();
  const [text, setText] = useState("");
  const [crs, setCrs] = useState("auto");
  const [epsg, setEpsg] = useState(25832);
  const [utmZone, setUtmZone] = useState(32);
  const [southern, setSouthern] = useState(false);
  const options: CoordinateOptions = { crs: crs === "utm" || crs === "epsg" ? "projected" : (crs as CoordinateOptions["crs"]), ...(crs === "utm" ? { utm_zone: utmZone, southern } : crs === "epsg" ? { epsg } : {}) };
  const [pasted] = useDebouncedValue(JSON.stringify({ text, options }), 400);
  useEffect(() => {
    const { text: value, options: chosen } = JSON.parse(pasted) as { text: string; options: CoordinateOptions };
    if (mode === "paste" && value.trim()) parser.mutate({ text: value, options: chosen, near: centreOfDomain });
    // Only when the text or the system changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pasted, mode]);

  // Zone: drawn corners, filled as the settings change
  const [vertices, setVertices] = useState<[number, number][]>([]);
  const [drawing, setDrawing] = useState(false);
  const layout = useGeoLayout();

  // File: read, then its points or one of its polygons
  const reader = useGeoImport();
  const [path, setPath] = useState("");
  const [fileCrs, setFileCrs] = useState("");
  const [polygonId, setPolygonId] = useState<string | null>(null);
  const [fileUse, setFileUse] = useState<"points" | "zone">("points");
  const fileData = reader.data && reader.variables?.path === path ? reader.data : null;
  const polygon = fileData?.polygons.find((item) => item.id === polygonId) ?? fileData?.polygons[0];

  // Grid: rows and columns around a centre placed on the map
  const [centre, setCentre] = useState(centreOfDomain);
  const [rows, setRows] = useState(5);
  const [columns, setColumns] = useState(5);
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    const stop = (event: KeyboardEvent) => { if (event.key === "Escape") { setDrawing(false); setPlacing(false); } };
    window.addEventListener("keydown", stop);
    return () => window.removeEventListener("keydown", stop);
  }, []);

  // The zone filled on the server, from the drawn ring or the file's polygon
  const rings: [number, number][][] = mode === "zone" ? (vertices.length >= 3 ? [ring(vertices)] : []) : mode === "file" && fileUse === "zone" && polygon ? (polygon.rings as [number, number][][]) : [];
  const body = rings.length && !drawing && lattice.spacing > 0 && lattice.across > 0 ? layoutBody(rings, lattice, Number(type)) : null;
  const [request] = useDebouncedValue(body ? JSON.stringify(body) : "", 350);
  useEffect(() => {
    if (request) layout.mutate(JSON.parse(request) as GeoLayoutRequest);
    else layout.reset();
    // Only when the request changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request]);
  const filled = body && layout.data && JSON.stringify(layout.variables) === JSON.stringify(body) ? layout.data : null;

  const items: Turbine[] = useMemo(() => {
    if (mode === "paste") return parser.data && text.trim() ? parser.data.points.map((point) => newTurbine(point.lat, point.lon, point.type ?? Number(type), point.name?.slice(0, 32))) : [];
    if (mode === "grid") {
      if (rows < 1 || columns < 1 || rows * columns > 10000 || lattice.spacing <= 0 || lattice.across <= 0) return [];
      return gridLayout({ ...centre, rows, columns, spacing: lattice.spacing, across: lattice.across, rotation: lattice.orientation, stagger: lattice.stagger ? 0.5 : 0 }).map((point) => newTurbine(point.lat, point.lon, Number(type)));
    }
    if (mode === "file" && fileUse === "points") return fileData ? fileData.points.map((point) => ({ ...point, type: Number(type) })) : [];
    return filled ? filled.points : [];
  }, [mode, parser.data, text, type, rows, columns, lattice, centre, fileUse, fileData, filled]);

  // Key figures: turbines, installed power, spacing in diameters, area
  const area = mode === "grid" ? (Math.max(0, columns - 1) * lattice.spacing * Math.max(0, rows - 1) * lattice.across) / 1e6 : filled?.area_km2 ?? null;
  // The figures run to their new value rather than jump
  const count = Math.round(useRunningNumber(items.length));
  const power = useRunningNumber(items.length * (model?.ratedMw ?? 0));
  const surface = useRunningNumber(area ?? 0);
  const figures = [
    t("turbines", { n: count }),
    model?.ratedMw ? `${f.number(power, 1)} MW` : null,
    mode !== "paste" && !(mode === "file" && fileUse === "points") && rotor ? `${f.number(lattice.spacing / rotor, 1)} × ${f.number(lattice.across / rotor, 1)} D` : null,
    area ? `${f.number(surface, 1)} km²` : null,
  ].filter(Boolean).join(" · ");

  const polygons: FeatureCollection = {
    type: "FeatureCollection",
    features: [
      ...(mode === "zone" && vertices.length >= 3 ? [{ type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: [ring(vertices)] }, properties: { kind: "domain" as const } }] : []),
      ...(mode === "file" && fileData ? fileData.polygons.map((item) => ({ type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: item.rings }, properties: { kind: "domain" as const } })) : []),
    ],
  };
  const shown = mode === "zone" && (drawing || !items.length) ? vertices.map(([lon, lat], index) => ({ lon, lat, label: String(index + 1) })) : items;

  const pickOnMap = mode === "zone" ? drawing && vertices.length < 200 : mode === "grid" && placing;
  const onPick = (lat: number, lon: number) => {
    if (mode === "zone") setVertices((value) => [...value, [lon, lat]]);
    if (mode === "grid") { setCentre({ lat, lon }); setPlacing(false); }
  };

  return (
    <Stack gap="md">
      <SegmentedControl value={mode} onChange={(value) => { setMode(value as Mode); setDrawing(false); setPlacing(false); }} data={([["paste", IconClipboardText], ["zone", IconPolygon], ["grid", IconGridDots], ["file", IconFileImport]] as const).map(([value, Icon]) => ({ value, label: <Group gap={6} wrap="nowrap" justify="center"><Icon size={16} /><span>{t(`modes.${value}`)}</span></Group> }))} />
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack gap="md">
            {mode === "paste" && <>
              <Textarea label={<FieldLabel label={t("coordinates")} info={t("coordinatesInfo")} />} value={text} onChange={(event) => setText(event.currentTarget.value)} autosize minRows={8} maxRows={14} placeholder={tf("import.placeholder")} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }} />
              <Group gap="xs">
                <FileButton accept=".csv,.txt,.tsv" onChange={(file) => { if (file) void file.text().then(setText); }}>{(props) => <Button {...props} variant="default" size="xs">{t("openFile")}</Button>}</FileButton>
                <ExampleFile files={["positions-eoliennes.csv"]} onUse={setText} />
              </Group>
              <Select label={t("system")} value={crs} allowDeselect={false} data={(["auto", "latlon", "lonlat", "utm", "epsg"] as const).map((value) => ({ value, label: tf(`import.${value}`) }))} onChange={(value) => setCrs(value ?? "auto")} />
              {crs === "epsg" && <NumberField label={tf("import.epsgCode")} min={1} allowDecimal={false} value={epsg} onValue={setEpsg} />}
              {crs === "utm" && <SimpleGrid cols={2} spacing="sm"><NumberField label={tf("import.zone")} min={1} max={60} allowDecimal={false} value={utmZone} onValue={setUtmZone} /><Select label={tf("import.hemisphere")} value={southern ? "south" : "north"} allowDeselect={false} data={[{ value: "north", label: tf("import.north") }, { value: "south", label: tf("import.south") }]} onChange={(value) => setSouthern(value === "south")} /></SimpleGrid>}
              {parser.error && text.trim() && <ErrorState error={parser.error} />}
              {parser.data && text.trim() && <Text size="sm" c="dimmed">{t("points", { n: parser.data.points.length, detected: parser.data.detected })}</Text>}
              {parser.data && text.trim() && parser.data.skipped.length > 0 && <Text size="sm" c="red">{t("skipped", { lines: parser.data.skipped.join(", ") })}</Text>}
            </>}
            {mode === "zone" && <>
              <Group gap="xs">
                <Button size="xs" variant={drawing ? "filled" : "default"} leftSection={<IconPolygon size={16} />} onClick={() => setDrawing((value) => !value)}>{t(drawing ? "finish" : "draw")}</Button>
                <Button size="xs" variant="subtle" color="gray" disabled={!vertices.length} leftSection={<IconArrowBackUp size={16} />} onClick={() => setVertices((value) => value.slice(0, -1))}>{t("undo")}</Button>
                <Button size="xs" variant="subtle" color="gray" disabled={!vertices.length} leftSection={<IconX size={16} />} onClick={() => { setVertices([]); setDrawing(false); }}>{t("clear")}</Button>
                <Text size="xs" c="dimmed" ml="auto" aria-live="polite">{t("corners", { n: vertices.length })}</Text>
              </Group>
              <LatticeFields value={lattice} onChange={setLattice} rotor={rotor} />
            </>}
            {mode === "grid" && <>
              <Stack gap={6}>
                <Group justify="space-between"><Text size="sm" fw={500}>{t("centre")}</Text><Button size="compact-xs" variant={placing ? "filled" : "default"} leftSection={<IconMapPin size={14} />} onClick={() => setPlacing((value) => !value)}>{t(placing ? "placing" : "place")}</Button></Group>
                <SimpleGrid cols={2} spacing="sm">
                  <NumberField aria-label={t("lat")} unit="°N" min={-90} max={90} decimalScale={5} value={Number(centre.lat.toFixed(5))} onValue={(lat) => setCentre((value) => ({ ...value, lat }))} />
                  <NumberField aria-label={t("lon")} unit="°E" min={-180} max={180} decimalScale={5} value={Number(centre.lon.toFixed(5))} onValue={(lon) => setCentre((value) => ({ ...value, lon }))} />
                </SimpleGrid>
              </Stack>
              <SimpleGrid cols={2} spacing="sm">
                <NumberField label={t("rows")} min={1} max={200} allowDecimal={false} value={rows} onValue={setRows} />
                <NumberField label={t("columns")} min={1} max={200} allowDecimal={false} value={columns} onValue={setColumns} />
              </SimpleGrid>
              <LatticeFields value={lattice} onChange={setLattice} rotor={rotor} setback={false} />
            </>}
            {mode === "file" && <>
              <PathInput kind="file" example="geo" label={t("path")} value={path} onChange={(value) => { setPath(value); reader.reset(); }} placeholder={"C:\\Données\\parc.geojson"} />
              <Group gap="xs" align="flex-end" wrap="nowrap">
                <TextInput style={{ flex: 1 }} label={<FieldLabel label={t("crs")} info={t("crsInfo")} />} value={fileCrs} onChange={(event) => { setFileCrs(event.currentTarget.value); reader.reset(); }} />
                <Button variant="default" loading={reader.isPending} disabled={!path.trim()} onClick={() => reader.mutate({ path, crs: fileCrs.trim() || null })}>{t("read")}</Button>
              </Group>
              <ExampleFile files={["zone-parc.geojson"]} />
              {reader.error && <ErrorState error={reader.error} />}
              {fileData && <>
                <SegmentedControl size="xs" value={fileUse} onChange={(value) => setFileUse(value as "points" | "zone")} data={[{ value: "points", label: `${t("filePoints")} · ${fileData.points.length}`, disabled: !fileData.points.length }, { value: "zone", label: `${t("fileZone")} · ${fileData.polygons.length}`, disabled: !fileData.polygons.length }]} />
                {fileUse === "zone" && polygon && <>
                  <Select label={t("zone")} value={polygon.id} allowDeselect={false} data={fileData.polygons.map((item) => ({ value: item.id, label: item.name || item.id }))} onChange={setPolygonId} />
                  <LatticeFields value={lattice} onChange={setLattice} rotor={rotor} />
                </>}
                {fileData.warnings.map((warning, index) => <Text key={index} size="xs" c="dimmed">{warning}</Text>)}
              </>}
            </>}
            <Select label={t("model")} value={type} data={types} allowDeselect={false} onChange={(value) => setType(value ?? "1")} />
            {layout.error && body && <ErrorState error={layout.error} />}
            {filled?.warnings.map((warning, index) => <Text key={index} size="xs" c="dimmed">{warning}</Text>)}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }} style={{ display: "flex" }}>
          <Box style={{ flex: 1, minHeight: 500, borderRadius: "var(--ows-surface-radius)", overflow: "hidden", border: "1px solid var(--ows-border-strong)" }}>
            <ProjectMap geometry={geometry} height="100%" fit="turbines" ariaLabel={t("map")} polygons={polygons} points={shown} fitPoints={items.length > 0} picking={pickOnMap} onPick={onPick} />
          </Box>
        </Grid.Col>
      </Grid>
      <Group justify="space-between" pt="sm" style={{ borderTop: "1px solid var(--ows-border)" }}>
        <Text size="sm" fw={600} className="ows-num" c={items.length ? undefined : "dimmed"}>{items.length ? figures : t("none")}</Text>
        <Group gap="xs">
          <Confirm title={t("replaceTitle", { n: farm.turbines.length, name: farm.name })} text={t("replaceText", { m: items.length })} color="orange" onConfirm={() => onApply(items, true)}>
            {(open) => <Button variant="default" disabled={!items.length || !farm.turbines.length} onClick={open}>{t("replace")}</Button>}
          </Confirm>
          <Button disabled={!items.length} onClick={() => onApply(items, false)}>{t("add")}</Button>
        </Group>
      </Group>
      {mode === "paste" && parser.data && !parser.data.points.length && text.trim() && <Alert color="red" variant="light">{t("none")}</Alert>}
    </Stack>
  );
}
