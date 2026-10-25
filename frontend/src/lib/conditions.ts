import { translate } from "../i18n";
import type { ExposureLevel, Lang } from "../types";

/** "Extreme heat, in shade or sun" / "High heat in shade, extreme in sun" (and Spanish). */
export function summaryText(shade: ExposureLevel, sun: ExposureLevel, lang: Lang): string {
  const word = (level: ExposureLevel) => translate(lang, `conditions.level_${level}`);
  if (shade === sun) {
    return translate(lang, "conditions.same", { level: word(shade) });
  }
  return translate(lang, "conditions.split", {
    shade: word(shade),
    sun: word(sun).toLowerCase(),
  });
}
