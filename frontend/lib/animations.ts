import { useEffect } from "react";

/**
 * Hook that applies a gentle entrance animation to an element.
 * Respects prefers-reduced-motion by skipping motion entirely.
 */
export function useEntrance(
  ref: React.RefObject<HTMLElement>,
  { delay = 0 }: { delay?: number } = {}
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      el.style.opacity = "1";
      el.style.transform = "none";
      return;
    }

    el.style.opacity = "0";
    el.style.transform = "translateY(12px)";
    el.style.transition = `opacity 600ms ease ${delay}ms, transform 600ms ease ${delay}ms`;

    requestAnimationFrame(() => {
      el.style.opacity = "1";
      el.style.transform = "translateY(0)";
    });
  }, [delay]);
}

/**
 * Easing curve used for premium entrance/exit motion across the app.
 */
export const easeOutCubic = "cubic-bezier(0.23, 1, 0.32, 1)";
