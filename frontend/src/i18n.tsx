import { createContext, useContext, useState, type ReactNode } from "react";
import en from "./locales/en.json";
import es from "./locales/es.json";
import type { Lang } from "./types";

type Dictionary = Record<string, string>;
const dictionaries: Record<Lang, Dictionary> = { en, es };

export function translate(
  lang: Lang,
  key: string,
  vars: Record<string, string | number> = {},
): string {
  const template = dictionaries[lang][key] ?? dictionaries.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

const LangContext = createContext<[Lang, (lang: Lang) => void]>(["en", () => {}]);

export function LangProvider({ children }: { children: ReactNode }) {
  const state = useState<Lang>("en");
  return <LangContext.Provider value={state}>{children}</LangContext.Provider>;
}

export function useLang(): [Lang, (lang: Lang) => void] {
  return useContext(LangContext);
}

export function useT(): (key: string, vars?: Record<string, string | number>) => string {
  const [lang] = useLang();
  return (key, vars) => translate(lang, key, vars);
}
