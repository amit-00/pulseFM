"use client";

import { useRef, useEffect, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import { AnimatedBeam } from "./ui/animated-beam";

interface WaveformVisualizerProps {
  frequencyData: Uint8Array;
  isActive: boolean;
  className?: string;
}

// Inactive beam component (static grey line)
function InactiveBeamLine() {
  return (
    <div 
      className="absolute left-0 top-1/2 -translate-y-1/2 h-[2px] w-[calc(50%-5px)]"
      style={{
        background: "linear-gradient(to right, transparent 0%, rgba(120, 120, 120, 0.3) 20%, rgba(120, 120, 120, 0.5) 100%)"
      }}
    />
  );
}

// Bar data structure
interface FlowingBar {
  x: number; // Position relative to center (starts at 0, moves right)
  height: number; // Height of the bar (0-1 normalized)
  id: number; // Unique identifier
}

// Aurora gradient colors for the flowing bars
const AURORA_COLORS = [
  { r: 255, g: 0, b: 128 }, // #FF0080
  { r: 121, g: 40, b: 202 }, // #7928CA
  { r: 0, g: 112, b: 243 }, // #0070F3
  { r: 56, g: 189, b: 248 }, // #38bdf8
];

export function WaveformVisualizer({
  frequencyData,
  isActive,
  className,
}: WaveformVisualizerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const beamFromRef = useRef<HTMLDivElement>(null);
  const beamToRef = useRef<HTMLDivElement>(null);
  const animationRef = useRef<number | null>(null);
  const barsRef = useRef<FlowingBar[]>([]);
  const lastBarTimeRef = useRef<number>(0);
  const barIdRef = useRef<number>(0);
  const frequencyDataRef = useRef<Uint8Array>(frequencyData);
  const isActiveRef = useRef(isActive);

  // Keep refs in sync
  frequencyDataRef.current = frequencyData;
  isActiveRef.current = isActive;

  // Configuration
  const BAR_WIDTH = 5;
  const BAR_GAP = 3;
  const BAR_INTERVAL = 60; // ms between creating new bars
  const BAR_SPEED = 2.5; // pixels per frame
  const CENTER_BAR_WIDTH = 10;
  const CENTER_BAR_BASE_HEIGHT = 50;
  const MAX_BAR_HEIGHT_RATIO = 0.65; // Max bar height as ratio of canvas height
  const MAGNITUDE_MULTIPLIER = 1.8; // Multiplier to make bars appear larger

  // Get aurora color based on position
  const getAuroraColor = useCallback(
    (normalizedX: number, alpha: number = 1): string => {
      const scaledPos = Math.max(0, Math.min(1, normalizedX)) * (AURORA_COLORS.length - 1);
      const index = Math.floor(scaledPos);
      const t = scaledPos - index;

      const c1 = AURORA_COLORS[Math.min(index, AURORA_COLORS.length - 1)];
      const c2 = AURORA_COLORS[Math.min(index + 1, AURORA_COLORS.length - 1)];

      const r = Math.round(c1.r + (c2.r - c1.r) * t);
      const g = Math.round(c1.g + (c2.g - c1.g) * t);
      const b = Math.round(c1.b + (c2.b - c1.b) * t);

      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    },
    []
  );

  // Calculate average frequency value
  const getAverageFrequency = useCallback((data: Uint8Array): number => {
    if (data.length === 0) return 0;
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      sum += data[i];
    }
    return sum / data.length / 255; // Normalized 0-1
  }, []);

  // Main render function
  const render = useCallback(
    (timestamp: number) => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) {
        animationRef.current = requestAnimationFrame(render);
        return;
      }

      const ctx = canvas.getContext("2d");
      if (!ctx) {
        animationRef.current = requestAnimationFrame(render);
        return;
      }

      const { width, height } = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;

      // Set canvas size if changed
      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(dpr, dpr);
      }

      const centerX = width / 2;
      const centerY = height / 2;
      const maxBarHeight = height * MAX_BAR_HEIGHT_RATIO;

      // Clear canvas
      ctx.clearRect(0, 0, width, height);

      const data = frequencyDataRef.current;
      const active = isActiveRef.current;
      const avgFreq = getAverageFrequency(data);

      // Create new bar if music is playing
      if (active && timestamp - lastBarTimeRef.current > BAR_INTERVAL) {
        if (avgFreq > 0.02) {
          // Apply magnitude multiplier and clamp to max of 1
          const amplifiedHeight = Math.min(1, Math.max(0.15, avgFreq * MAGNITUDE_MULTIPLIER));
          barsRef.current.push({
            x: CENTER_BAR_WIDTH / 2 + BAR_GAP,
            height: amplifiedHeight,
            id: barIdRef.current++,
          });
          lastBarTimeRef.current = timestamp;
        }
      }

      // Update bar positions and remove off-screen bars
      const rightEdge = width - centerX;
      barsRef.current = barsRef.current
        .map((bar) => ({ ...bar, x: bar.x + BAR_SPEED }))
        .filter((bar) => bar.x < rightEdge + BAR_WIDTH);

      // === DRAW CENTER BAR (red when active, grey when inactive) ===
      const centerBarHeight = CENTER_BAR_BASE_HEIGHT + (active ? avgFreq * 40 : 0);

      // Center bar gradient - red when active, grey when inactive
      const centerBarGradient = ctx.createLinearGradient(
        centerX,
        centerY - centerBarHeight / 2,
        centerX,
        centerY + centerBarHeight / 2
      );
      
      if (active) {
        centerBarGradient.addColorStop(0, "rgba(239, 68, 68, 0.7)"); // red-500
        centerBarGradient.addColorStop(0.5, "rgba(220, 38, 38, 1)"); // red-600
        centerBarGradient.addColorStop(1, "rgba(239, 68, 68, 0.7)"); // red-500
      } else {
        centerBarGradient.addColorStop(0, "rgba(120, 120, 120, 0.5)"); // grey
        centerBarGradient.addColorStop(0.5, "rgba(100, 100, 100, 0.7)"); // grey
        centerBarGradient.addColorStop(1, "rgba(120, 120, 120, 0.5)"); // grey
      }

      // Glow effect for center bar (only when active)
      ctx.save();
      ctx.shadowColor = active ? "rgba(239, 68, 68, 0.6)" : "rgba(100, 100, 100, 0.3)";
      ctx.shadowBlur = active ? 25 : 8;
      ctx.fillStyle = centerBarGradient;

      // Draw rounded center bar
      const centerBarX = centerX - CENTER_BAR_WIDTH / 2;
      const centerBarY = centerY - centerBarHeight / 2;
      const radius = CENTER_BAR_WIDTH / 2;
      
      ctx.beginPath();
      ctx.roundRect(centerBarX, centerBarY, CENTER_BAR_WIDTH, centerBarHeight, radius);
      ctx.fill();
      ctx.restore();

      // === DRAW FLOWING BARS (right side) ===
      barsRef.current.forEach((bar) => {
        const barX = centerX + bar.x;
        const barHeight = Math.max(8, bar.height * maxBarHeight);
        const normalizedPos = Math.min(1, bar.x / (width / 2));

        // Calculate opacity - fade out as bars move further right
        const opacity = Math.max(0.3, 1 - normalizedPos * 0.5);

        // Bar gradient
        const barGradient = ctx.createLinearGradient(
          barX,
          centerY - barHeight / 2,
          barX,
          centerY + barHeight / 2
        );

        const colorPos = 0.3 + normalizedPos * 0.5;
        barGradient.addColorStop(0, getAuroraColor(colorPos - 0.1, opacity * 0.7));
        barGradient.addColorStop(0.5, getAuroraColor(colorPos, opacity));
        barGradient.addColorStop(1, getAuroraColor(colorPos + 0.1, opacity * 0.7));

        ctx.fillStyle = barGradient;

        // Draw bar centered vertically with rounded corners
        const barRadius = BAR_WIDTH / 2;
        ctx.beginPath();
        ctx.roundRect(
          barX - BAR_WIDTH / 2,
          centerY - barHeight / 2,
          BAR_WIDTH,
          barHeight,
          barRadius
        );
        ctx.fill();
      });

      // === DRAW DECORATIVE ELEMENTS ===
      
      // Subtle horizontal baseline on right side
      ctx.strokeStyle = "rgba(56, 189, 248, 0.1)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 8]);
      ctx.beginPath();
      ctx.moveTo(centerX + CENTER_BAR_WIDTH / 2, centerY);
      ctx.lineTo(width, centerY);
      ctx.stroke();
      ctx.setLineDash([]);

      animationRef.current = requestAnimationFrame(render);
    },
    [getAuroraColor, getAverageFrequency]
  );

  // Start animation loop
  useEffect(() => {
    animationRef.current = requestAnimationFrame(render);

    return () => {
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
      // Clear bars on resize to prevent visual glitches
      barsRef.current = [];
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative w-full h-full min-h-[200px] overflow-hidden",
        className
      )}
    >
      {/* Canvas for flowing bars */}
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
      
      {/* Beam source point (off-screen left) */}
      <div
        ref={beamFromRef}
        className="absolute -left-4 top-1/2 -translate-y-1/2 w-2 h-2"
      />
      
      {/* Beam target point (center bar) */}
      <div
        ref={beamToRef}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-2 h-2"
      />
      
      {/* Show animated beam only when active, otherwise show static grey line */}
      {isActive ? (
        <AnimatedBeam
          containerRef={containerRef}
          fromRef={beamFromRef}
          toRef={beamToRef}
          pathColor="rgba(239, 68, 68, 0.3)"
          pathWidth={3}
          pathOpacity={0.4}
          gradientStartColor="#ef4444"
          gradientStopColor="#dc2626"
          duration={1.5}
          curvature={0}
        />
      ) : (
        <InactiveBeamLine />
      )}
    </div>
  );
}
