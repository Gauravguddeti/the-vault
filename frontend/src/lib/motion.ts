/**
 * Motion design tokens — single source of truth for all animations in the app.
 * Use these constants for any inline `transition` or `animation` style strings
 * so every component moves with the same rhythm.
 */

export const DURATION = {
  fast: 150,   // micro-interactions: button press, badge cross-fade
  base: 200,   // standard: message fade-in, card hover
  slow: 300,   // larger: modal open, list item delete, skeleton shimmer cycle
} as const;

export const EASE = {
  out: "cubic-bezier(0.0, 0.0, 0.2, 1)",   // elements entering the screen
  in: "cubic-bezier(0.4, 0.0, 1, 1)",       // elements leaving the screen
  inOut: "cubic-bezier(0.4, 0.0, 0.2, 1)",  // elements changing in place
} as const;

/** Build a CSS transition string from our token system */
export function transition(
  props: string | string[] = "all",
  duration: number = DURATION.base,
  easing: string = EASE.out
): string {
  const propList = Array.isArray(props) ? props : [props];
  return propList.map(p => `${p} ${duration}ms ${easing}`).join(", ");
}

/**
 * React hook: returns true if the user has requested reduced motion at the OS level.
 * When true, suppress or simplify all non-essential animations.
 * Usage: const reduced = useReducedMotion(); if (reduced) skip animation.
 */
import { useEffect, useState } from "react";

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return reduced;
}
