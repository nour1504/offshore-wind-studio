/**
 * Adding turbines to a farm, four ways in one frame: paste (CoordinateSheet, read by the server in
 * the chosen coordinate system), zone (a drawn polygon filled by core/geo.py turbine_layout), grid
 * (rows around a centre on the map), file (GeoJSON, KML, shapefile: points or a polygon). Lattice
 * settings: the way's own, spacings, row orientation (clockwise from east), stagger.
 */
import { Alert, Box, Button, FileButton, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconArrowBackUp, IconClipboardText, IconFileImport, IconGridDots, IconMapPin, IconPolygon, IconPropeller, IconX } from "@tabler/icons-react";
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
import { CoordinateSheet, readRow, type SheetRow } from "./CoordinateSheet";
import { farmMessages } from "./messages";
import { gridLayout, innermostCentre, newTurbine, type TypeInfo } from "./model";

const messages = defineMessages({
  en: {
    modes: { paste: "Paste", zone: "Zone", grid: "Grid", file: "GIS file" },
    openFile: "Open a file",
    clearSheet: "Clear",
    system: "Coordinate system",
    systemInfo: "Of what is pasted or opened; the table is in WGS 84.",
    skipped: "Lines skipped: {lines}",
    outline: "Outline",
    draw: "Draw",
    finish: "Finish",
    undo: "Undo",
    clear: "Clear",
    corners: "{n|# corner|# corners}",
    spacing: "In the row",
    spacingInfo: "Between neighboring turbines of a row.",
    across: "Between rows",
    acrossInfo: "Between two neighboring rows.",
    orientation: "Orientation of the rows",
    orientationInfo: "Angle of the rows, clockwise from east.",
    stagger: "Rows",
    aligned: "Aligned",
    staggered: "Staggered",
    staggerInfo: "Every other row shifted by half a spacing.",
    setback: "Edge setback",
    setbackInfo: "No turbine closer than this to the edge of the zone.",
    centre: "Center",
    place: "Place on the map",
    placing: "Click the center",
    lat: "Latitude",
    lon: "Longitude",
    rows: "Rows",
    columns: "Turbines per row",
    model: "Type",
    path: "File",
    crs: "Projection (optional)",
    crsInfo: "EPSG code or WKT. Shapefile: .prj required, otherwise give the projection here. Keep .shp, .shx and .dbf together.",
    read: "Read",
    zone: "Zone",
    filePoints: "Points of the file",
    fileZone: "Fill a zone",
    figures: { turbines: "Turbines", power: "Power", spacing: "Spacing", area: "Area", system: "Coordinates" },
    add: "Add",
    replace: "Replace",
    replaceTitle: "Replace the {n|turbine|# turbines} of {name}?",
    replaceText: "{m|# turbine|# turbines} instead.",
    none: "No position",
    diameters: "{v} D",
    map: "Preview of the turbines",
  },
  fr: {
    modes: { paste: "Coller", zone: "Zone", grid: "Grille", file: "Fichier SIG" },
    openFile: "Ouvrir un fichier",
    clearSheet: "Effacer",
    system: "Système de coordonnées",
    systemInfo: "De ce qui est collé ou ouvert ; le tableau est en WGS 84.",
    skipped: "Lignes ignorées : {lines}",
    outline: "Contour",
    draw: "Dessiner",
    finish: "Terminer",
    undo: "Annuler",
    clear: "Effacer",
    corners: "{n|# sommet|# sommets}",
    spacing: "Dans la rangée",
    spacingInfo: "Entre éoliennes voisines d'une rangée.",
    across: "Entre rangées",
    acrossInfo: "Entre deux rangées voisines.",
    orientation: "Orientation des rangées",
    orientationInfo: "Angle des rangées, dans le sens horaire depuis l'est.",
    stagger: "Rangées",
    aligned: "Alignées",
    staggered: "En quinconce",
    staggerInfo: "Une rangée sur deux décalée d'un demi-espacement.",
    setback: "Marge au bord",
    setbackInfo: "Aucune éolienne plus près que cela du bord de la zone.",
    centre: "Centre",
    place: "Placer sur la carte",
    placing: "Clic sur le centre",
    lat: "Latitude",
    lon: "Longitude",
    rows: "Rangées",
    columns: "Éoliennes par rangée",
    model: "Type",
    path: "Fichier",
    crs: "Projection (facultatif)",
    crsInfo: "Code EPSG ou WKT. Shapefile : .prj requis, sinon indiquer la projection ici. Garder .shp, .shx et .dbf ensemble.",
    read: "Lire",
    zone: "Zone",
    filePoints: "Points du fichier",
    fileZone: "Remplir une zone",
    figures: { turbines: "Éoliennes", power: "Puissance", spacing: "Espacement", area: "Surface", system: "Coordonnées" },
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

/** The spacings in the row and between rows, then the orientation and stagger of the rows. */
function LatticeFields({ value, onChange, rotor }: { value: Lattice; onChange: (value: Lattice) => void; rotor: number | null }) {
  const t = useT(messages);
  const f = useFormat();
  const diameters = (metres: number) => (rotor ? t("diameters", { v: f.number(metres / rotor, 1) }) : undefined);
  const set = (change: Partial<Lattice>) => onChange({ ...value, ...change });
  return <>
    <SimpleGrid cols={2} spacing="md">
      <NumberField label={<FieldLabel label={t("spacing")} info={t("spacingInfo")} />} unit="m" min={1} allowDecimal={false} value={value.spacing} description={diameters(value.spacing)} inputWrapperOrder={["label", "input", "description", "error"]} onValue={(spacing) => set({ spacing })} />
      <NumberField label={<FieldLabel label={t("across")} info={t("acrossInfo")} />} unit="m" min={1} allowDecimal={false} value={value.across} description={diameters(value.across)} inputWrapperOrder={["label", "input", "description", "error"]} onValue={(across) => set({ across })} />
    </SimpleGrid>
    <SimpleGrid cols={2} spacing="md">
      <NumberField label={<FieldLabel label={t("orientation")} info={t("orientationInfo")} />} unit="°" min={-360} max={360} decimalScale={1} value={value.orientation} onValue={(orientation) => set({ orientation })} />
      <Select label={<FieldLabel label={t("stagger")} info={t("staggerInfo")} />} value={value.stagger ? "staggered" : "aligned"} allowDeselect={false} data={[{ value: "aligned", label: t("aligned") }, { value: "staggered", label: t("staggered") }]} onChange={(choice) => set({ stagger: choice === "staggered" })} />
    </SimpleGrid>
  </>;
}

/** A key figure of the bottom band: its name over its value. */
function Figure({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return <div className="ows-figure"><span className="ows-figure-label">{label}</span><span className="ows-figure-value ows-num">{value}{unit && <small>{unit}</small>}</span></div>;
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

  // Paste: the sheet, and a block waiting to be read in the coordinate system chosen
  const parser = useParseCoordinates();
  const [rows, setRows] = useState<SheetRow[]>([]);
  const [block, setBlock] = useState<{ text: string; row: number; all: boolean } | null>(null);
  const [crs, setCrs] = useState("auto");
  const [epsg, setEpsg] = useState(25832);
  const [utmZone, setUtmZone] = useState(32);
  const [southern, setSouthern] = useState(false);
  const options: CoordinateOptions = { crs: crs === "utm" || crs === "epsg" ? "projected" : (crs as CoordinateOptions["crs"]), ...(crs === "utm" ? { utm_zone: utmZone, southern } : crs === "epsg" ? { epsg } : {}) };
  const optionsKey = JSON.stringify(options);
  useEffect(() => {
    if (!block) return;
    parser.mutate({ text: block.text, options, near: centreOfDomain }, {
      onSuccess: (data) => {
        const read: SheetRow[] = data.points.map((point) => [point.name ?? "", String(point.lat), String(point.lon), point.type ? String(point.type) : ""]);
        setRows((now) => {
          if (block.all) return read;
          const next = [...now];
          read.forEach((row, k) => { next[block.row + k] = row; });
          return Array.from(next, (row) => row ?? ["", "", "", ""]);
        });
        setBlock(null);
      },
    });
    // Read again when the coordinate system changes, until it reads
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block, optionsKey]);
  const take = (text: string, row = 0, all = true) => { if (text.trim()) setBlock({ text, row, all }); };

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

  // Grid: rows and turbines per row around a centre placed on the map
  const [centre, setCentre] = useState(centreOfDomain);
  const [gridRows, setGridRows] = useState(5);
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
    if (mode === "paste") return rows.flatMap((row) => { const one = readRow(row, Number(type)); return typeof one === "object" ? [newTurbine(one.lat, one.lon, one.type, one.name)] : []; });
    if (mode === "grid") {
      if (gridRows < 1 || columns < 1 || gridRows * columns > 10000 || lattice.spacing <= 0 || lattice.across <= 0) return [];
      return gridLayout({ ...centre, rows: gridRows, columns, spacing: lattice.spacing, across: lattice.across, rotation: lattice.orientation, stagger: lattice.stagger ? 0.5 : 0 }).map((point) => newTurbine(point.lat, point.lon, Number(type)));
    }
    if (mode === "file" && fileUse === "points") return fileData ? fileData.points.map((point) => ({ ...point, type: Number(type) })) : [];
    return filled ? filled.points : [];
  }, [mode, rows, type, gridRows, columns, lattice, centre, fileUse, fileData, filled]);

  // Key figures: turbines, installed power, spacing in diameters, area; they run to their new value
  const area = mode === "grid" ? (Math.max(0, columns - 1) * lattice.spacing * Math.max(0, gridRows - 1) * lattice.across) / 1e6 : filled?.area_km2 ?? null;
  const count = Math.round(useRunningNumber(items.length));
  const power = useRunningNumber(items.length * (model?.ratedMw ?? 0));
  const surface = useRunningNumber(area ?? 0);
  const lattices = mode !== "paste" && !(mode === "file" && fileUse === "points");
  // What the other ways produce, listed as the paste sheet down to the bottom of the map
  const listed = useMemo(() => (mode === "paste" ? [] : items.map((item): SheetRow => [item.id ?? "", String(item.lat), String(item.lon), String(item.type)])), [mode, items]);

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
  const parsed = parser.data && !block ? parser.data : null;

  return (
    <Stack gap="lg">
      <Group justify="space-between" gap="md">
        <SegmentedControl value={mode} onChange={(value) => { setMode(value as Mode); setDrawing(false); setPlacing(false); }} data={([["paste", IconClipboardText], ["zone", IconPolygon], ["grid", IconGridDots], ["file", IconFileImport]] as const).map(([value, Icon]) => ({ value, label: <Group gap={6} wrap="nowrap" justify="center"><Icon size={16} /><span>{t(`modes.${value}`)}</span></Group> }))} />
        <Select w={300} aria-label={t("model")} leftSection={<IconPropeller size={16} />} value={type} data={types} allowDeselect={false} onChange={(value) => setType(value ?? "1")} />
      </Group>
      <div className="ows-add-body">
        <div className="ows-add-side">
          {mode === "paste" && <>
            <CoordinateSheet rows={rows} model={Number(type)} onChange={setRows} onPasteBlock={(text, row) => take(text, row, false)} />
            <Group gap="xs">
              <FileButton accept=".csv,.txt,.tsv" onChange={(file) => { if (file) void file.text().then((text) => take(text)); }}>{(props) => <Button {...props} variant="default" size="xs">{t("openFile")}</Button>}</FileButton>
              <ExampleFile files={["positions-eoliennes.csv"]} onUse={(text) => take(text)} />
              <Button variant="default" size="xs" ml="auto" disabled={!rows.length} onClick={() => { setRows([]); setBlock(null); }}>{t("clearSheet")}</Button>
            </Group>
            <SimpleGrid cols={crs === "utm" ? 3 : crs === "epsg" ? 2 : 1} spacing="md">
              <Select label={<FieldLabel label={t("system")} info={t("systemInfo")} />} value={crs} allowDeselect={false} data={(["auto", "latlon", "lonlat", "utm", "epsg"] as const).map((value) => ({ value, label: tf(`import.${value}`) }))} onChange={(value) => setCrs(value ?? "auto")} />
              {crs === "epsg" && <NumberField label={tf("import.epsgCode")} min={1} allowDecimal={false} value={epsg} onValue={setEpsg} />}
              {crs === "utm" && <NumberField label={tf("import.zone")} min={1} max={60} allowDecimal={false} value={utmZone} onValue={setUtmZone} />}
              {crs === "utm" && <Select label={tf("import.hemisphere")} value={southern ? "south" : "north"} allowDeselect={false} data={[{ value: "north", label: tf("import.north") }, { value: "south", label: tf("import.south") }]} onChange={(value) => setSouthern(value === "south")} />}
            </SimpleGrid>
            {parser.error && block && <ErrorState error={parser.error} />}
            {parsed && parsed.skipped.length > 0 && <Text size="sm" c="red">{t("skipped", { lines: parsed.skipped.join(", ") })}</Text>}
          </>}
          {mode === "zone" && <>
            <SimpleGrid cols={2} spacing="md">
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("outline")}</Text>
                <Group gap={6} wrap="nowrap">
                  <Button variant={drawing ? "filled" : "default"} leftSection={<IconPolygon size={16} />} onClick={() => setDrawing((value) => !value)}>{t(drawing ? "finish" : "draw")}</Button>
                  <Tooltip label={t("undo")}><Button variant="default" px={10} aria-label={t("undo")} disabled={!vertices.length} onClick={() => setVertices((value) => value.slice(0, -1))}><IconArrowBackUp size={16} /></Button></Tooltip>
                  <Tooltip label={t("clear")}><Button variant="default" px={10} aria-label={t("clear")} disabled={!vertices.length} onClick={() => { setVertices([]); setDrawing(false); }}><IconX size={16} /></Button></Tooltip>
                </Group>
                <Text size="xs" c="dimmed" aria-live="polite" className="ows-num">{t("corners", { n: vertices.length })}</Text>
              </Stack>
              <NumberField label={<FieldLabel label={t("setback")} info={t("setbackInfo")} />} unit="m" min={0} allowDecimal={false} value={lattice.setback} onValue={(setback) => setLattice((value) => ({ ...value, setback }))} />
            </SimpleGrid>
            <LatticeFields value={lattice} onChange={setLattice} rotor={rotor} />
          </>}
          {mode === "grid" && <>
            <Stack gap={6}>
              <Group justify="space-between"><Text size="sm" fw={500}>{t("centre")}</Text><Button size="compact-xs" variant={placing ? "filled" : "default"} leftSection={<IconMapPin size={14} />} onClick={() => setPlacing((value) => !value)}>{t(placing ? "placing" : "place")}</Button></Group>
              <SimpleGrid cols={2} spacing="md">
                <NumberField aria-label={t("lat")} unit="°N" min={-90} max={90} decimalScale={5} value={Number(centre.lat.toFixed(5))} onValue={(lat) => setCentre((value) => ({ ...value, lat }))} />
                <NumberField aria-label={t("lon")} unit="°E" min={-180} max={180} decimalScale={5} value={Number(centre.lon.toFixed(5))} onValue={(lon) => setCentre((value) => ({ ...value, lon }))} />
              </SimpleGrid>
            </Stack>
            <SimpleGrid cols={2} spacing="md">
              <NumberField label={t("rows")} min={1} max={200} allowDecimal={false} value={gridRows} onValue={setGridRows} />
              <NumberField label={t("columns")} min={1} max={200} allowDecimal={false} value={columns} onValue={setColumns} />
            </SimpleGrid>
            <LatticeFields value={lattice} onChange={setLattice} rotor={rotor} />
          </>}
          {mode === "file" && <>
            <PathInput kind="file" example="geo" label={t("path")} value={path} onChange={(value) => { setPath(value); reader.reset(); }} placeholder={"C:\\Données\\parc.geojson"} />
            <Group gap="xs" align="flex-end" wrap="nowrap">
              <TextInput style={{ flex: 1 }} label={<FieldLabel label={t("crs")} info={t("crsInfo")} />} value={fileCrs} onChange={(event) => { setFileCrs(event.currentTarget.value); reader.reset(); }} />
              <Button variant="default" loading={reader.isPending} disabled={!path.trim()} onClick={() => reader.mutate({ path, crs: fileCrs.trim() || null })}>{t("read")}</Button>
            </Group>
            <Box><ExampleFile files={["zone-parc.geojson"]} /></Box>
            {reader.error && <ErrorState error={reader.error} />}
            {fileData && <>
              <SegmentedControl fullWidth value={fileUse} onChange={(value) => setFileUse(value as "points" | "zone")} data={[{ value: "points", label: `${t("filePoints")} · ${fileData.points.length}`, disabled: !fileData.points.length }, { value: "zone", label: `${t("fileZone")} · ${fileData.polygons.length}`, disabled: !fileData.polygons.length }]} />
              {fileUse === "zone" && polygon && <>
                <SimpleGrid cols={2} spacing="md">
                  <Select label={t("zone")} value={polygon.id} allowDeselect={false} data={fileData.polygons.map((item) => ({ value: item.id, label: item.name || item.id }))} onChange={setPolygonId} />
                  <NumberField label={<FieldLabel label={t("setback")} info={t("setbackInfo")} />} unit="m" min={0} allowDecimal={false} value={lattice.setback} onValue={(setback) => setLattice((value) => ({ ...value, setback }))} />
                </SimpleGrid>
                <LatticeFields value={lattice} onChange={setLattice} rotor={rotor} />
              </>}
              {fileData.warnings.map((warning, index) => <Text key={index} size="xs" c="dimmed">{warning}</Text>)}
            </>}
          </>}
          {layout.error && body && <ErrorState error={layout.error} />}
          {filled?.warnings.map((warning, index) => <Text key={index} size="xs" c="dimmed">{warning}</Text>)}
          {mode !== "paste" && <CoordinateSheet rows={listed} model={Number(type)} readOnly />}
        </div>
        <div className="ows-add-map">
          <ProjectMap geometry={geometry} height="100%" fit="turbines" ariaLabel={t("map")} polygons={polygons} points={shown} fitPoints={items.length > 0} picking={pickOnMap} onPick={onPick} />
        </div>
      </div>
      <div className="ows-add-foot">
        <div className="ows-figures" aria-live="polite">
          <Figure label={t("figures.turbines")} value={f.number(count, 0)} />
          <Figure label={t("figures.power")} value={model?.ratedMw ? f.number(power, 1) : "–"} unit={model?.ratedMw ? "MW" : undefined} />
          {lattices ? <>
            <Figure label={t("figures.spacing")} value={rotor ? `${f.number(lattice.spacing / rotor, 1)} × ${f.number(lattice.across / rotor, 1)}` : "–"} unit={rotor ? "D" : undefined} />
            <Figure label={t("figures.area")} value={area ? f.number(surface, 1) : "–"} unit={area ? "km²" : undefined} />
          </> : <Figure label={t("figures.system")} value={mode === "paste" ? "WGS 84" : fileData?.crs || "WGS 84"} />}
        </div>
        <Group gap="xs">
          <Confirm title={t("replaceTitle", { n: farm.turbines.length, name: farm.name })} text={t("replaceText", { m: items.length })} color="orange" onConfirm={() => onApply(items, true)}>
            {(open) => <Button variant="default" disabled={!items.length || !farm.turbines.length} onClick={open}>{t("replace")}</Button>}
          </Confirm>
          <Button disabled={!items.length} onClick={() => onApply(items, false)}>{t("add")}</Button>
        </Group>
      </div>
      {mode === "paste" && parsed && !parsed.points.length && <Alert color="red" variant="light">{t("none")}</Alert>}
    </Stack>
  );
}
