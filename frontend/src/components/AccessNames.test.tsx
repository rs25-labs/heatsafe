import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LangProvider } from "../i18n";
import TripForm from "./TripForm";

function renderForm() {
  render(
    <LangProvider>
      <TripForm
        presets={[]} demoDate={null} start={null} end={null} picking={null}
        loading={false} error={null} onPlace={() => {}} onPick={() => {}} onSubmit={() => {}}
      />
    </LangProvider>,
  );
}

describe("TripForm leave radios", () => {
  it("announces each radio by name, not just on", () => {
    renderForm();
    expect(screen.getByRole("radio", { name: "Now" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "At a set time" })).toBeTruthy();
  });
});
