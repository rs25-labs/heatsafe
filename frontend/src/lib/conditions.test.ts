import { describe, expect, it } from "vitest";
import { summaryText } from "./conditions";

describe("summaryText", () => {
  it("same level in English", () => {
    expect(summaryText("extreme", "extreme", "en")).toBe("Extreme heat, in shade or sun");
  });

  it("split levels in English", () => {
    expect(summaryText("high", "extreme", "en")).toBe("High heat in shade, extreme in sun");
  });

  it("same level in Spanish", () => {
    expect(summaryText("extreme", "extreme", "es")).toBe("Calor extremo, al sol o a la sombra");
  });

  it("split levels in Spanish", () => {
    expect(summaryText("high", "moderate", "es")).toBe("Calor alto a la sombra, moderado al sol");
  });
});
