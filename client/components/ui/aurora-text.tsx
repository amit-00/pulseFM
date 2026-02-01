"use client"

import React, { memo } from "react"

interface AuroraTextProps {
  children: React.ReactNode
  className?: string
  colors?: string[]
  speed?: number
  active?: boolean
}

export const AuroraText = memo(
  ({
    children,
    className = "",
    colors = ["#FF0080", "#7928CA", "#0070F3", "#38bdf8"],
    speed = 1,
    active = true,
  }: AuroraTextProps) => {
    const gradientStyle = {
      backgroundImage: `linear-gradient(135deg, ${colors.join(", ")}, ${colors[0]
        })`,
      WebkitBackgroundClip: "text",
      WebkitTextFillColor: "transparent",
      animationDuration: `${10 / speed}s`,
    }

    return (
      <span className={`relative inline-block ${className}`}>
        <span className="sr-only">{children}</span>
        {/* Grey text base layer */}
        <span
          className={`relative text-stone-500 transition-opacity duration-300 ${active ? "opacity-0" : "opacity-100"
            }`}
          aria-hidden="true"
        >
          {children}
        </span>
        {/* Aurora effect layer */}
        <span
          className={`absolute inset-0 animate-aurora bg-size-[200%_auto] bg-clip-text text-transparent transition-opacity duration-300 ${active ? "opacity-100" : "opacity-0"
            }`}
          style={gradientStyle}
          aria-hidden="true"
        >
          {children}
        </span>
      </span>
    )
  }
)

AuroraText.displayName = "AuroraText"

