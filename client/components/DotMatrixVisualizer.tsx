"use client";

import { useRef, useEffect, useState, useMemo } from "react";
import { cn } from "@/lib/utils";

interface DotMatrixVisualizerProps {
  frequencyData: Uint8Array;
  isActive: boolean;
  className?: string;
}

interface DotConfig {
  row: number;
  col: number;
  frequencyIndex: number;
}

export function DotMatrixVisualizer({
  frequencyData,
  isActive,
  className,
}: DotMatrixVisualizerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  
  // Dot configuration
  const dotSize = 10;
  const dotGap = 14;
  const dotSpacing = dotSize + dotGap;

  // Calculate grid dimensions based on container size
  const gridConfig = useMemo(() => {
    if (dimensions.width === 0 || dimensions.height === 0) {
      return { cols: 0, rows: 0, dots: [] as DotConfig[] };
    }

    const cols = Math.floor(dimensions.width / dotSpacing);
    const rows = Math.floor(dimensions.height / dotSpacing);
    
    const dots: DotConfig[] = [];
    
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        // Map columns to frequency bins (32 bins from analyser)
        // Distribute frequency bins across columns
        const frequencyIndex = Math.floor((col / cols) * frequencyData.length);
        dots.push({ row, col, frequencyIndex });
      }
    }
    
    return { cols, rows, dots };
  }, [dimensions.width, dimensions.height, dotSpacing, frequencyData.length]);

  // Update dimensions on resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const { width, height } = containerRef.current.getBoundingClientRect();
        setDimensions({ width, height });
      }
    };

    updateDimensions();
    
    const resizeObserver = new ResizeObserver(updateDimensions);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, []);

  // Calculate opacity for a dot based on frequency data and row position
  const getDotOpacity = (dot: DotConfig): number => {
    if (!isActive) return 0.25; // Inactive state - visible but dimmed
    
    const frequencyValue = frequencyData[dot.frequencyIndex] || 0;
    // Normalize frequency value (0-255) to percentage
    const normalizedFrequency = frequencyValue / 255;
    
    // Calculate how many rows should be lit based on frequency
    // Higher frequency values light up more rows from bottom to top
    const totalRows = gridConfig.rows;
    const litRows = Math.ceil(normalizedFrequency * totalRows);
    const rowFromBottom = totalRows - 1 - dot.row;
    
    if (rowFromBottom < litRows) {
      // Dot is active - full opacity with slight variation based on position
      const intensity = 0.7 + (normalizedFrequency * 0.3);
      return Math.min(1, intensity);
    }
    
    // Inactive dot during playback
    return 0.25;
  };

  // Calculate horizontal offset to center the grid
  const horizontalOffset = useMemo(() => {
    const gridWidth = gridConfig.cols * dotSpacing;
    return (dimensions.width - gridWidth) / 2;
  }, [dimensions.width, gridConfig.cols, dotSpacing]);

  // Calculate vertical offset to center the grid
  const verticalOffset = useMemo(() => {
    const gridHeight = gridConfig.rows * dotSpacing;
    return (dimensions.height - gridHeight) / 2;
  }, [dimensions.height, gridConfig.rows, dotSpacing]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative w-full h-full overflow-hidden",
        className
      )}
    >
      <svg
        className="absolute inset-0 w-full h-full"
        aria-hidden="true"
      >
        {gridConfig.dots.map((dot) => {
          const x = horizontalOffset + (dot.col * dotSpacing) + (dotSpacing / 2);
          const y = verticalOffset + (dot.row * dotSpacing) + (dotSpacing / 2);
          const opacity = getDotOpacity(dot);
          
          return (
            <circle
              key={`${dot.row}-${dot.col}`}
              cx={x}
              cy={y}
              r={dotSize / 2}
              className="fill-emerald-500 transition-opacity duration-75"
              style={{ opacity }}
            />
          );
        })}
      </svg>
    </div>
  );
}

