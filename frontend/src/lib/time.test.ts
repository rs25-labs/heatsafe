import { describe, expect, it } from "vitest";
import { santaAnaIso } from "./time";

describe("santaAnaIso", () => {
  it("uses PDT in September", () => {
    expect(santaAnaIso("2026-09-10", "15:30")).toBe("2026-09-10T15:30:00-07:00");
  });

  it("uses PST in January", () => {
    expect(santaAnaIso("2026-01-15", "15:30")).toBe("2026-01-15T15:30:00-08:00");
  });
});
