"use client";

import { useEffect, useState } from "react";

/** Returns true after first client mount — avoids hydration mismatches. */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}
