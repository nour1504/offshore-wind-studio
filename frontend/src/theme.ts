import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from "@mantine/core";

import { DURATION, dialogIn, dropIn, EASE_OUT } from "./motion";

// Every floating layer opens the same way (see motion.ts)
const menuTransition = { transition: dropIn, duration: DURATION.menu, exitDuration: DURATION.micro, timingFunction: EASE_OUT };

// Green, the primary colour: green on white in light mode, on deep green in dark mode;
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

// Dark mode: near-black neutral surfaces (glass on black), not tinted
const dark: MantineColorsTuple = [
  "#ececef",
  "#c1c2c7",
  "#94959c",
  "#6c6d74",
  "#3b3c42",
  "#2b2c31",
  "#1e1f23",
  "#16171a",
  "#101113",
  "#0a0a0c",
];

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

/** Charts and explicit shade names obey the monochrome dark palette as well as buttons. */
export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {},
  dark: Object.fromEntries(
    ["forest", "green", "teal", "cyan", "blue", "lime"].flatMap((name) => [
      ...["#f5f5f5", "#e8e8e8", "#d9d9d9", "#ccc", "#8c8c8c", "#eee", "#ddd", "#ffffff", "#bbb", "#aaa"].map((color, index) => [`--mantine-color-${name}-${index}`, color]),
      [`--mantine-color-${name}-filled`, "#f1f1f1"],
      [`--mantine-color-${name}-filled-hover`, "#ffffff"],
      [`--mantine-color-${name}-light`, "rgba(255,255,255,0.08)"],
      [`--mantine-color-${name}-light-hover`, "rgba(255,255,255,0.13)"],
      [`--mantine-color-${name}-light-color`, "#f1f1f1"],
      [`--mantine-color-${name}-outline`, "rgba(255,255,255,0.7)"],
      [`--mantine-color-${name}-outline-hover`, "rgba(255,255,255,0.08)"],
      [`--mantine-color-${name}-text`, "#f1f1f1"],
    ]),
  ),
});

export const theme = createTheme({
  primaryColor: "forest",
  primaryShade: { light: 7, dark: 5 },
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
      h2: { fontSize: "1.1875rem", lineHeight: "1.35" },
      h3: { fontSize: "1.0625rem", lineHeight: "1.4" },
      h4: { fontSize: "0.9375rem", lineHeight: "1.45" },
    },
  },
  // Body text at 14.5 px for long sessions; labels and table headers one step smaller
  fontSizes: { xs: "0.78rem", sm: "0.84rem", md: "0.9063rem", lg: "1.0313rem", xl: "1.1563rem" },
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
    Button: { defaultProps: { radius: "md" } },
    TextInput: { defaultProps: { radius: "md" } },
    Select: { defaultProps: { radius: "md" } },
    Badge: { defaultProps: { variant: "light", radius: "sm" }, styles: { root: { textTransform: "none", fontWeight: 600 } } },
    Tooltip: {
      defaultProps: {
        withArrow: true, arrowSize: 6, openDelay: 300, multiline: true, maw: 320,
        transitionProps: { transition: "fade", duration: DURATION.micro, timingFunction: EASE_OUT },
      },
    },
    Popover: { defaultProps: { transitionProps: menuTransition } },
    HoverCard: { defaultProps: { transitionProps: menuTransition } },
    Menu: { defaultProps: { transitionProps: menuTransition } },
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
    Accordion: { defaultProps: { transitionDuration: DURATION.dialog, chevronSize: 16 } },
    Collapse: { defaultProps: { transitionDuration: DURATION.dialog, transitionTimingFunction: EASE_OUT } },
    SegmentedControl: { defaultProps: { transitionDuration: DURATION.dialog, transitionTimingFunction: EASE_OUT } },
    Progress: { defaultProps: { transitionDuration: DURATION.large } },
    NumberInput: { defaultProps: { hideControls: true } },
    Table: { defaultProps: { verticalSpacing: "sm", highlightOnHover: true } },
    Tabs: { defaultProps: { keepMounted: false } },
  },
});
