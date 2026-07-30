"use client";
import { usePathname } from "next/navigation";

/** Wraps page content with a per-route fade-in so route changes don't flash blank. */
export default function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="animate-fade-in h-full">
      {children}
    </div>
  );
}
