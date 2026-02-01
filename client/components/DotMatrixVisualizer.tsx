"use client";

import { useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";

interface DotMatrixVisualizerProps {
  frequencyData: Uint8Array;
  isActive: boolean;
  className?: string;
}

// Aurora gradient colors
const AURORA_COLORS = [
  { r: 255, g: 0, b: 128 },    // #FF0080
  { r: 121, g: 40, b: 202 },   // #7928CA
  { r: 0, g: 112, b: 243 },    // #0070F3
  { r: 56, g: 189, b: 248 },   // #38bdf8
];

export function DotMatrixVisualizer({
  frequencyData,
  isActive,
  className,
}: DotMatrixVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animationRef = useRef<number | null>(null);
  const frequencyDataRef = useRef<Uint8Array>(frequencyData);
  const isActiveRef = useRef(isActive);

  // Keep refs in sync
  frequencyDataRef.current = frequencyData;
  isActiveRef.current = isActive;

  // Calculate responsive dot size based on screen width
  const getResponsiveDotConfig = useCallback((width: number) => {
    // Scale dot size based on container width
    // Small screens (< 480px): 6px dots
    // Medium screens (480-768px): 8px dots
    // Large screens (768-1024px): 10px dots
    // XL screens (> 1024px): 12px dots
    let dotSize: number;
    let dotGap: number;

    if (width < 480) {
      dotSize = 6;
      dotGap = 10;
    } else if (width < 768) {
      dotSize = 8;
      dotGap = 12;
    } else if (width < 1024) {
      dotSize = 10;
      dotGap = 14;
    } else {
      dotSize = 12;
      dotGap = 16;
    }

    return { dotSize, dotGap, dotSpacing: dotSize + dotGap };
  }, []);

  // Get aurora color based on column position (interpolated)
  const getAuroraColor = useCallback((normalizedX: number, alpha: number): string => {
    const scaledPos = normalizedX * (AURORA_COLORS.length - 1);
    const index = Math.floor(scaledPos);
    const t = scaledPos - index;

    const c1 = AURORA_COLORS[Math.min(index, AURORA_COLORS.length - 1)];
    const c2 = AURORA_COLORS[Math.min(index + 1, AURORA_COLORS.length - 1)];

    const r = Math.round(c1.r + (c2.r - c1.r) * t);
    const g = Math.round(c1.g + (c2.g - c1.g) * t);
    const b = Math.round(c1.b + (c2.b - c1.b) * t);

    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }, []);

  // Main render function
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    // Set canvas size if changed
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(dpr, dpr);
    }

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Get responsive dot configuration
    const { dotSize, dotSpacing } = getResponsiveDotConfig(width);
    const dotRadius = dotSize / 2;

    // Calculate columns: first dot edge at x=0, last dot edge at x=width
    const availableWidth = width - dotSize; // space for dot centers
    const cols = Math.max(1, Math.floor(availableWidth / dotSpacing) + 1);
    const colSpacing = cols > 1 ? availableWidth / (cols - 1) : 0;

    // Calculate rows: similar approach for vertical
    const availableHeight = height - dotSize;
    const rows = Math.max(1, Math.floor(availableHeight / dotSpacing) + 1);
    const rowSpacing = rows > 1 ? availableHeight / (rows - 1) : 0;

    if (cols === 0 || rows === 0) return;

    const data = frequencyDataRef.current;
    const active = isActiveRef.current;

    // Draw dots
    for (let col = 0; col < cols; col++) {
      const frequencyIndex = Math.floor((col / cols) * data.length);
      const frequencyValue = data[frequencyIndex] || 0;
      const normalizedFrequency = frequencyValue / 255;
      const litRows = active ? Math.ceil(normalizedFrequency * rows) : 0;
      const normalizedX = cols > 1 ? col / (cols - 1) : 0.5;

      for (let row = 0; row < rows; row++) {
        // Position dots so edges align with container edges
        const x = dotRadius + col * colSpacing;
        const y = dotRadius + row * rowSpacing;
        const rowFromBottom = rows - 1 - row;
        const isLit = rowFromBottom < litRows;

        // Set color with appropriate alpha
        const alpha = isLit ? 1 : 0.15;
        ctx.fillStyle = getAuroraColor(normalizedX, alpha);

        // Draw dot (slightly larger if lit for emphasis)
        const radius = isLit ? dotSize / 2 + 0.5 : dotSize / 2;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();

        // Add subtle glow for lit dots (simple approach)
        if (isLit && normalizedFrequency > 0.3) {
          ctx.fillStyle = getAuroraColor(normalizedX, 0.3);
          ctx.beginPath();
          ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
          ctx.fill();

          // Redraw the solid dot on top
          ctx.fillStyle = getAuroraColor(normalizedX, 1);
          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    animationRef.current = requestAnimationFrame(render);
  }, [getResponsiveDotConfig, getAuroraColor]);

  // Start/stop animation loop
  useEffect(() => {
    // Initial render
    render();

    // Delayed render to catch late layout calculations
    const timeoutId = setTimeout(render, 100);

    return () => {
      clearTimeout(timeoutId);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [render]);

  // Handle resize
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver(() => {
      // Force re-render on resize
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      render();
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [render]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative w-full h-full min-h-[200px] overflow-hidden",
        className
      )}
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
      />
    </div>
  );
}
