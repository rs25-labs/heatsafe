import { describe, expect, it } from "vitest";
import en from "./locales/en.json";
import es from "./locales/es.json";

const DEMO_PREFIXES = ["form.", "route.", "recommendation.", "exposure.", "nosafe.", "walk.", "later."];

describe("Spanish", () => {
  it("es_covers_demo_screens", () => {
    const needed = Object.keys(en).filter((key) => DEMO_PREFIXES.some((p) => key.startsWith(p)));
    const missing = needed.filter((key) => !(key in es));
    expect(missing).toEqual([]);
  });

  it("keeps the same {placeholders} as English", () => {
    const names = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    for (const [key, text] of Object.entries(es)) {
      expect(names(text), key).toEqual(names((en as Record<string, string>)[key] ?? ""));
    }
  });
});
