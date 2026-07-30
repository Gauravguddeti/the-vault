"use client";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/**
 * Page transition wrapper.
 * Applies a fast fade-in when the route changes WITHOUT unmounting the page
 * (no key prop — that would destroy all component state and force re-fetches).
 * The animation is purely visual: a brief opacity 0→1 over 150ms.
 */
export default function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [visible, setVisible] = useState(true);
  const prevPathname = useRef(pathname);

  useEffect(() => {
    if (pathname === prevPathname.current) return;
    prevPathname.current = pathname;
    // Flash opacity to 0 then back to 1 — purely CSS, no unmount
    setVisible(false);
    const t = requestAnimationFrame(() => {
      requestAnimationFrame(() => setVisible(true));
    });
    return () => cancelAnimationFrame(t);
  }, [pathname]);

  return (
    <div
      style={{
        opacity: visible ? 1 : 0,
        transition: "opacity 150ms cubic-bezier(0.0, 0.0, 0.2, 1)",
        height: "100%",
      }}
    >
      {children}
    </div>
  );
}
