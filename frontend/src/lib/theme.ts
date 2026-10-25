// Hex mirrors of the Tailwind v4 @theme tokens in index.css, for canvases
// (MapLibre GL, Cesium) that can't read CSS classes. Keep the two in sync.
export const theme = {
  ink: "#1a1a1a",
  muted: "#5c5c57",
  subtle: "#3d3d39",
  paper: "#ffffff",
  band: "#f7f7f5",
  rule: "#e3e3df",
  control: "#8c8c86",
  controlSoft: "#c9c9c4",
  accent: "#1d3557",
  accentHover: "#0f1e33",
  routeOther: "#6b7280",
  // Route stretches in direct sun: red, clearly lighter and warmer than the navy shade line.
  sun: "#d1352b",
  sunHover: "#b5443c",
  sunOther: "#e8928c",
  heat1: "#f3d9c2",
  heat2: "#e7a574",
  heat3: "#c8692a",
  heat4: "#8a3a0b",
  error: "#9b1c1c",
  // Walker dot (3D view and flat map); carried over from the pre-design palette.
  walker: "#b45309",
} as const;
