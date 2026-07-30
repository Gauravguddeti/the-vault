"use client";

interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  style?: React.CSSProperties;
}

/** A single shimmer skeleton block. Use width/height or className for sizing. */
export function Skeleton({ className = "", width, height, style }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width, height, ...style }}
      aria-hidden="true"
    />
  );
}

/** Pre-built skeleton matching a document card's exact layout. */
export function SkeletonDocCard() {
  return (
    <div
      className="rounded-xl p-4 flex items-center gap-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
      aria-hidden="true"
    >
      {/* Icon block */}
      <Skeleton width={40} height={40} className="rounded-lg flex-shrink-0" />

      {/* Text block */}
      <div className="flex-1 min-w-0 space-y-2">
        <Skeleton height={14} className="rounded" style={{ width: "55%" }} />
        <div className="flex items-center gap-3">
          <Skeleton width={64} height={20} className="rounded-full" />
          <Skeleton width={80} height={12} className="rounded" />
        </div>
      </div>

      {/* Actions placeholder */}
      <div className="flex gap-1">
        <Skeleton width={30} height={30} className="rounded-lg" />
        <Skeleton width={30} height={30} className="rounded-lg" />
      </div>
    </div>
  );
}

/** Pre-built skeleton row for a chat conversation sidebar item. */
export function SkeletonChatRow() {
  return (
    <div
      className="px-3 py-2.5 rounded-xl flex items-center gap-2"
      aria-hidden="true"
    >
      <div className="flex-1 space-y-1.5">
        <Skeleton height={13} className="rounded" style={{ width: "70%" }} />
        <Skeleton height={11} className="rounded" style={{ width: "40%" }} />
      </div>
    </div>
  );
}
