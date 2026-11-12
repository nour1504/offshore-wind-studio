/** Deterministic display checks; no browser, network, user data or WRF process.
 * Run from the repository with Node 24: node tools/check_map_display.mjs
 */
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { farmAppearance, farmDisplay } from "../frontend/src/ui/map/farms.ts";

let passed = 0;
function check(name, run) {
  run(); passed += 1; console.log(`PASS ${name}`);
}
const point = (farm, i, coordinates, extra = {}) => ({
  type: "Feature",
  geometry: { type: "Point", coordinates },
  properties: { kind: "turbine", farm, farm_name: `Farm ${farm}`, label: `${farm}-${i}`, ...extra },
});
const grid = (farm, lon, lat, appearance = {}) => Array.from({ length: 500 }, (_, i) =>
  point(farm, i, [lon + (i % 25) * 0.002, lat + Math.floor(i / 25) * 0.002], appearance));
const source = { type: "FeatureCollection", features: [
  ...grid("CM1", -0.5, 50.2, { farm_color: "#209854", farm_symbol: "cross" }),
  ...grid("CM2", -0.2, 50.4, { farm_color: "#7853A0", farm_symbol: "triangle", enabled: false }),
] };
const before = structuredClone(source);
const far = ([lon, lat]) => ({ x: lon * 80, y: lat * 80 });
const mid = ([lon, lat]) => ({ x: lon * 1200, y: lat * 1200 });
const close = ([lon, lat]) => ({ x: lon * 10000, y: lat * 10000 });
const near = ([lon, lat]) => ({ x: lon * 100000, y: lat * 100000 });
const started = performance.now();
const overview = farmDisplay(source, ["CM1", "CM2"], far);
const named = farmDisplay(source, ["CM1", "CM2"], mid);
const detailed = farmDisplay(source, ["CM1", "CM2"], near);
const levels = (display) => display.tags.map((tag) => tag.level);

check("from afar, two dense farms are two small marks, without names drawn or turbines", () => {
  assert.equal(overview.details.features.length, 0);
  assert.deepEqual(levels(overview), ["icon", "icon"]);
  assert.deepEqual(overview.tags.map(({ id, name, count, enabled }) => ({ id, name, count, enabled })), [
    { id: "CM1", name: "Farm CM1", count: 500, enabled: true },
    { id: "CM2", name: "Farm CM2", count: 500, enabled: false },
  ]);
});
check("closer, each farm is named before its turbines are drawn", () => {
  assert.equal(named.details.features.length, 0);
  assert.deepEqual(levels(named), ["name", "name"]);
});
check("closer still, every turbine is drawn; names wait until they have room", () => {
  const turbines = farmDisplay(source, ["CM1", "CM2"], close);
  assert.deepEqual(levels(turbines), ["turbines", "turbines"]);
  assert.equal(turbines.details.features.length, 1000);
  assert.ok(turbines.details.features.every((f) => f.properties.showLabel === false));
});
check("zooming in restores all 1000 original locations with their names", () => {
  assert.equal(detailed.details.features.length, 1000);
  assert.deepEqual(levels(detailed), ["turbines", "turbines"]);
  assert.ok(detailed.details.features.every((f) => f.properties.showLabel === true));
  assert.deepEqual(detailed.details.features.map((f) => [f.geometry, f.properties.label]), source.features.map((f) => [f.geometry, f.properties.label]));
});
check("the farm name sits above the farm once its turbines are drawn", () => {
  const [tag] = detailed.tags;
  assert.ok(tag.top[1] > tag.center[1]);
  assert.equal(tag.top[0], tag.center[0]);
});
check("all-turbines mode retains every position even at overview scale", () => {
  const all = farmDisplay(source, ["CM1", "CM2"], far, "all");
  assert.equal(all.details.features.length, 1000);
  assert.deepEqual(levels(all), ["turbines", "turbines"]);
  assert.deepEqual(all.details.features.map((f) => f.geometry), source.features.map((f) => f.geometry));
});
check("custom colors and symbols survive every display scale", () => {
  assert.deepEqual(overview.tags.map(({ color, symbol }) => ({ color, symbol })), [
    { color: "#209854", symbol: "cross" }, { color: "#7853A0", symbol: "triangle" },
  ]);
  for (const feature of detailed.details.features) {
    assert.equal(feature.properties.color, feature.properties.farm_color);
    assert.equal(feature.properties.symbol, feature.properties.farm_symbol);
  }
});
check("old projects receive distinct automatic markers", () => {
  const first = farmAppearance({}, 0), second = farmAppearance({}, 1);
  assert.notEqual(first.color, second.color);
  assert.notEqual(first.symbol, second.symbol);
  assert.deepEqual(farmAppearance({ appearance: { color: null, symbol: "auto" } }, 0), first);
});
check("a sparse farm remains detailed beside a dense farm", () => {
  const sparse = grid("open", 8, 54).slice(0, 2);
  const mixed = farmDisplay({ type: "FeatureCollection", features: [...source.features.slice(0, 500), ...sparse] }, ["CM1", "open"], far);
  assert.deepEqual(levels(mixed), ["icon", "turbines"]);
  assert.equal(mixed.tags[0].count, 500);
  assert.equal(mixed.details.features.length, 2);
});
check("geometry and project metadata are never mutated", () => {
  assert.deepEqual(source, before);
  const freeze = (value) => {
    if (value && typeof value === "object") { Object.freeze(value); Object.values(value).forEach(freeze); }
    return value;
  };
  assert.doesNotThrow(() => farmDisplay(freeze(structuredClone(source)), ["CM1", "CM2"], far));
});
const acrossDateLine = [[179.98, 10], [-179.98, 10], [-179.98, 10.04], [179.98, 10.04], [179.99, 10.02]];
const wrapProjection = ([lon, lat]) => ({ x: ((lon + 360) % 360), y: lat });
check("farms across the date line keep a local center", () => {
  const data = { type: "FeatureCollection", features: acrossDateLine.map((coords, i) => point("date", i, coords)) };
  const display = farmDisplay(data, ["date"], wrapProjection);
  assert.equal(display.tags.length, 1);
  assert.equal(display.tags[0].level, "icon");
  assert.ok(Math.abs(Math.abs(display.tags[0].center[0]) - 180) < 0.01);
  assert.equal(display.tags[0].count, 5);
});
check("empty geometry stays empty", () => {
  const empty = farmDisplay({ type: "FeatureCollection", features: [] }, [], far);
  assert.deepEqual(empty, { details: { type: "FeatureCollection", features: [] }, tags: [] });
});
console.log(`${passed} display checks passed (${Math.round(performance.now() - started)} ms, indicative local duration only).`);
