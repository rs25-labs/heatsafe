// Copy the ground-heat image from the processed data into the site's static files,
// so it's served as a plain file instead of through the Python API.
import { cpSync, existsSync, mkdirSync } from "node:fs";

const from = new URL("../../data/processed/overlay/", import.meta.url);
const to = new URL("../public/overlay/", import.meta.url);
if (existsSync(from)) {
  mkdirSync(to, { recursive: true });
  cpSync(from, to, { recursive: true });
}
