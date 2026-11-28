"use client";

import React, { useRef, useState } from "react";

interface PremiumCardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  bordered?: boolean;
  tilt?: boolean;
}

export function PremiumCard({
  children,
  className = "",
  hover = true,
  bordered = true,
  tilt = false,
}: PremiumCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState<string>("");
  const [sheen, setSheen] = useState<{ x: number; y: number; active: boolean }>({
    x: 50,
    y: 50,
    active: false,
  });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!tilt || !cardRef.current) return;
    if (
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }
    const rect = cardRef.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width;
    const py = (e.clientY - rect.top) / rect.height;
    const rotateY = (px - 0.5) * 8;
    const rotateX = (0.5 - py) * 8;
    setTransform(
      `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateZ(4px)`
    );
    setSheen({ x: px * 100, y: py * 100, active: true });
  };

  const handleMouseLeave = () => {
    if (!tilt) return;
    setTransform("");
    setSheen((prev) => ({ ...prev, active: false }));
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={
        tilt && transform
          ? { transform, transition: "transform 120ms ease-out" }
          : tilt
          ? { transition: "transform 320ms cubic-bezier(0.16, 1, 0.3, 1)" }
          : undefined
      }
      className={`
        relative overflow-hidden rounded-3xl p-6 transition-all duration-300
        ${bordered ? "border border-border" : ""}
        ${hover ? "hover:border-border-strong hover:shadow-xl hover:shadow-accent/10" : ""}
        bg-surface text-foreground
        ${className}
      `}
    >
      {tilt && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 transition-opacity duration-300"
          style={{
            opacity: sheen.active ? 1 : 0,
            background: `radial-gradient(circle 280px at ${sheen.x}% ${sheen.y}%, rgba(125, 211, 252, 0.12), transparent 70%)`,
          }}
        />
      )}
      <div className="relative z-10 flex h-full w-full flex-col">{children}</div>
    </div>
  );
}
