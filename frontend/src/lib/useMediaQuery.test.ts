import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMediaQuery } from "./useMediaQuery";

type Listener = (event: { matches: boolean }) => void;

function stubMatchMedia(initial: boolean) {
  const listeners = new Set<Listener>();
  const api = {
    listeners,
    setMatches(value: boolean) {
      act(() => {
        listeners.forEach((fn) => fn({ matches: value }));
      });
    },
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: initial,
      addEventListener: (_type: string, fn: Listener) => listeners.add(fn),
      removeEventListener: (_type: string, fn: Listener) => listeners.delete(fn),
    })),
  );
  return api;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMediaQuery", () => {
  it("flips when the query starts matching", () => {
    const api = stubMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 768px)"));
    expect(result.current).toBe(false);
    api.setMatches(true);
    expect(result.current).toBe(true);
  });

  it("flips back when the query stops matching", () => {
    const api = stubMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(min-width: 768px)"));
    expect(result.current).toBe(true);
    api.setMatches(false);
    expect(result.current).toBe(false);
  });
});
