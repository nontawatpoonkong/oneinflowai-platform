"use server";

import { cookies } from "next/headers";

import { LOCALE_COOKIE, locales, type Locale } from "@/i18n/config";

/**
 * Server action to switch the UI language. A future <LocaleSwitcher> can call
 * this; the app re-renders in the selected locale on the next navigation.
 */
export async function setLocale(locale: Locale): Promise<void> {
  if (!locales.includes(locale)) return;
  const store = await cookies();
  store.set(LOCALE_COOKIE, locale, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  });
}
