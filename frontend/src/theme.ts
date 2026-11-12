import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { createElement } from "react";

import { DURATION, dialogIn, dropIn, EASE_OUT, radialIn } from "./motion";

// Every floating layer opens the same way (see motion.ts)
const menuTransition = { transition: dropIn, duration: DURATION.menu, exitDuration: DURATION.micro, timingFunction: EASE_OUT };
// Menus (the lists of actions) open as a circle from their button
const radialMenu = { transition: radialIn, duration: 340, exitDuration: DURATION.micro, timingFunction: EASE_OUT };

// Green, the primary colour: shade 7 on white; on black, shade 8 is the one dark green;
// shades from light to dark
const forest: MantineColorsTuple = [
  "#eaf7ef",
  "#d4eedd",
  "#a9dcbb",
  "#7ac996",
  "#53b878",
  "#3aad66",
  "#2c9a58",
  "#1f7f48",
  "#17663b",
  "#0e4d2c",
];

// Dark mode, light to dark: text a green-tinted white (0 to 3), then what Mantine draws as borders
// (4), hovers (5) and filled surfaces (6 to 8): the dark green over the black, at 30, 20, 10.5,
// 7.5 and 5 %, down to the black (9)
const dark: MantineColorsTuple = [
  "#e6f3eb",
  "#c0d4c7",
  "#8fa99a",
  "#667d70",
  "#0a2416",
  "#091b11",
  "#07120c",
  "#060f0a",
  "#060d09",
  "#050806",
];

// Dark mode: shades 5 to 9 of the greens are the one dark green; the light ones stay for the
// lighter series of the charts
const deep = forest.map((color, index) => (index >= 5 ? forest[8] : color));

// Dark mode: the shades asked for as blue or cyan are greys that read on black (information
// marks, the measured series of the charts), light to dark
const mist = ["#f7f7f7", "#ececec", "#e0e0e0", "#d4d4d4", "#c8c8c8", "#bcbcbc", "#b0b0b0", "#a3a3a3", "#8f8f8f", "#7a7a7a"];

// Alerts and errors: one red, warm enough to sit with the greens
const danger: MantineColorsTuple = [
  "#fff0ef",
  "#fddcda",
  "#f5b4b0",
  "#ee8a84",
  "#e7685f",
  "#e25248",
  "#df463b",
  "#c6382e",
  "#b13027",
  "#9a251d",
];

// Neutral greys for queued states, formats and secondary series
const neutral: MantineColorsTuple = [
  "#f4f5f6",
  "#e7e9eb",
  "#cdd1d5",
  "#b0b6bc",
  "#979ea5",
  "#868e96",
  "#7d858d",
  "#6b737a",
  "#5e666d",
  "#4f575e",
];

// Manrope, bundled under the SIL OFL (styles.css @font-face), then system fallbacks
const font = '"Manrope Variable", "Segoe UI Variable Text", "Segoe UI", system-ui, Arial, sans-serif';

/** Dark mode: every green-family name fills, tints and outlines with the one dark green; text on
    its tints stays the light text. */
export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {},
  dark: Object.fromEntries([
    ...["forest", "green", "teal", "cyan", "blue", "lime"].flatMap((name) => [
      ...(name === "blue" || name === "cyan" ? mist : deep).map((color, index) => [`--mantine-color-${name}-${index}`, color]),
      [`--mantine-color-${name}-filled`, forest[8]],
      [`--mantine-color-${name}-filled-hover`, "#1b7244"],
      [`--mantine-color-${name}-light`, "rgba(23,102,59,0.255)"],
      [`--mantine-color-${name}-light-hover`, "rgba(23,102,59,0.38)"],
      [`--mantine-color-${name}-light-color`, dark[0]],
      [`--mantine-color-${name}-outline`, forest[8]],
      [`--mantine-color-${name}-outline-hover`, "rgba(23,102,59,0.16)"],
      [`--mantine-color-${name}-text`, dark[0]],
    ]),
    // Light and subtle red stay red on black (Mantine would write them almost white)
    ...["ember", "red", "orange", "yellow", "pink"].map((name) => [`--mantine-color-${name}-light-color`, danger[4]]),
  ]),
});

export const theme = createTheme({
  primaryColor: "forest",
  primaryShade: { light: 7, dark: 8 },
  // The application keeps to green, white (dark mode) and one alert red: every other Mantine
  // hue is mapped onto them, so that no component can bring purple, blue or orange back
  colors: {
    forest, dark, ember: danger, red: danger, orange: danger, yellow: danger, pink: danger,
    green: forest, teal: forest, cyan: forest, blue: forest, lime: forest,
    violet: neutral, grape: neutral, indigo: neutral,
  },
  autoContrast: true,
  respectReducedMotion: true,
  focusRing: "auto",
  defaultRadius: "md",
  radius: { xs: "5px", sm: "8px", md: "12px", lg: "14px", xl: "18px" },
  fontFamily: font,
  // Namelists, commands and logs only
  fontFamilyMonospace: '"Cascadia Mono", Consolas, "SFMono-Regular", Menlo, monospace',
  // Measured titles: one weight (600), natural spacing, sizes a step apart
  headings: {
    fontFamily: font,
    fontWeight: "600",
    sizes: {
      h1: { fontSize: "1.625rem", lineHeight: "1.25" },
      h2: { fontSize: "1.25rem", lineHeight: "1.35" },
      h3: { fontSize: "1.0625rem", lineHeight: "1.4" },
      h4: { fontSize: "0.90625rem", lineHeight: "1.45" },
    },
  },
  // Body text at 14.5 px for long sessions; labels and table headers one step smaller
  fontSizes: { xs: "0.75rem", sm: "0.8125rem", md: "0.90625rem", lg: "1.0625rem", xl: "1.25rem" },
  lineHeights: { xs: "1.45", sm: "1.5", md: "1.55", lg: "1.55", xl: "1.5" },
  spacing: { xs: "0.5rem", sm: "0.75rem", md: "1rem", lg: "1.5rem", xl: "2rem" },
  shadows: {
    xs: "0 1px 2px rgba(15, 30, 45, 0.06)",
    sm: "0 1px 3px rgba(15, 30, 45, 0.08), 0 1px 2px rgba(15, 30, 45, 0.04)",
    md: "0 4px 12px rgba(15, 30, 45, 0.08)",
  },
  components: {
    Card: { defaultProps: { withBorder: true, padding: "xl", radius: "lg" } },
    Paper: { defaultProps: { radius: "lg" } },
    Button: { defaultProps: { radius: "md", loaderProps: { type: "dots" } } },
    TextInput: { defaultProps: { radius: "md" } },
    Select: { defaultProps: { radius: "md" } },
    Tooltip: {
      defaultProps: {
        withArrow: true, arrowSize: 6, openDelay: 300, multiline: true, maw: 320,
        transitionProps: { transition: "fade", duration: DURATION.micro, timingFunction: EASE_OUT },
      },
    },
    Popover: { defaultProps: { transitionProps: menuTransition } },
    HoverCard: { defaultProps: { transitionProps: menuTransition } },
    Menu: { defaultProps: { transitionProps: radialMenu } },
    Combobox: { defaultProps: { transitionProps: menuTransition } },
    Modal: {
      defaultProps: {
        centered: true, radius: "lg",
        overlayProps: { backgroundOpacity: 0.45, blur: 6 },
        transitionProps: { transition: dialogIn, duration: DURATION.dialog, exitDuration: DURATION.state, timingFunction: EASE_OUT },
      },
    },
    Drawer: {
      defaultProps: {
        overlayProps: { backgroundOpacity: 0.3, blur: 2 },
        transitionProps: { duration: DURATION.large, exitDuration: DURATION.dialog, timingFunction: EASE_OUT },
      },
    },
    // Every section that opens has a + that turns into a ×
    Accordion: { defaultProps: { transitionDuration: DURATION.dialog, chevronSize: 16, chevron: createElement(IconPlus, { size: 16, stroke: 1.8 }) } },
    Collapse: { defaultProps: { transitionDuration: DURATION.dialog, transitionTimingFunction: EASE_OUT } },
    SegmentedControl: { defaultProps: { withItemsBorders: false } },
    Progress: { defaultProps: { transitionDuration: DURATION.large } },
    NumberInput: { defaultProps: { hideControls: true } },
    Table: { defaultProps: { verticalSpacing: "sm", highlightOnHover: true } },
    Tabs: { defaultProps: { keepMounted: false } },
  },
});
