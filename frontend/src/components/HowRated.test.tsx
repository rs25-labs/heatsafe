import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangProvider } from "../i18n";
import HowRated from "./HowRated";

describe("HowRated", () => {
  it("lists all four levels with their thresholds", () => {
    render(
      <LangProvider>
        <HowRated />
      </LangProvider>,
    );
    for (const name of ["Low", "Moderate", "High", "Extreme"]) {
      expect(screen.getByText(name)).toBeTruthy();
    }
    for (const bound of ["90", "103", "115"]) {
      const hits = screen.getAllByText(new RegExp(bound), { exact: false });
      expect(hits.length).toBeGreaterThan(0);
    }
  });
});
