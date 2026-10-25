import { useEffect } from "react";
import { useLang } from "../i18n";
import type { Lang } from "../types";

const OPTIONS: { lang: Lang; label: string }[] = [
  { lang: "en", label: "English" },
  { lang: "es", label: "Español" },
];

export default function LanguageToggle() {
  const [lang, setLang] = useLang();
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  return (
    <div role="group" aria-label="Language / Idioma" className="inline-flex rounded-md border border-control-soft text-sm">
      {OPTIONS.map((option) => (
        <button key={option.lang} type="button" lang={option.lang} aria-pressed={lang === option.lang}
          onClick={() => setLang(option.lang)}
          className="px-3 py-1 aria-pressed:bg-ink aria-pressed:text-paper focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
          {option.label}
        </button>
      ))}
    </div>
  );
}
