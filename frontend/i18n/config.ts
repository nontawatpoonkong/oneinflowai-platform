/** Supported locales. Add a locale here + a messages/<locale>.json file. */
export const locales = ["th", "en"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "th";

export const LOCALE_COOKIE = "NEXT_LOCALE";

export const localeNames: Record<Locale, string> = {
  th: "ไทย",
  en: "English",
};
