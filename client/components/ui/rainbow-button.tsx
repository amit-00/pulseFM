import React from "react"
import { cn } from "@/lib/utils"

interface RainbowButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline"
  size?: "default" | "sm" | "lg" | "icon"
}

const RainbowButton = React.forwardRef<HTMLButtonElement, RainbowButtonProps>(
  ({ className, variant = "default", size = "default", children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "relative cursor-pointer group transition-all animate-rainbow",
          "inline-flex items-center justify-center gap-2 shrink-0",
          "rounded-sm outline-none",
          "text-sm font-medium whitespace-nowrap",
          "disabled:pointer-events-none disabled:opacity-50",
          "[&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 [&_svg]:shrink-0",
          // Variant styles
          variant === "default" &&
            "border-0 bg-[linear-gradient(#121213,#121213),linear-gradient(#121213_50%,rgba(18,18,19,0.6)_80%,rgba(18,18,19,0)),linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] bg-size-[200%] text-white [background-clip:padding-box,border-box,border-box] bg-origin-border [border:calc(0.125rem)_solid_transparent] before:absolute before:bottom-[-20%] before:left-1/2 before:z-0 before:h-1/5 before:w-3/5 before:-translate-x-1/2 before:animate-rainbow before:bg-[linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] before:bg-size-[200%] before:filter-[blur(0.75rem)]",
          variant === "outline" &&
            "border-0 bg-[linear-gradient(#0a0a0a,#0a0a0a),linear-gradient(#0a0a0a_50%,rgba(10,10,10,0.6)_80%,rgba(10,10,10,0)),linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] bg-size-[200%] text-white [background-clip:padding-box,border-box,border-box] bg-origin-border [border:calc(0.125rem)_solid_transparent] before:absolute before:bottom-[-20%] before:left-1/2 before:z-0 before:h-1/5 before:w-3/5 before:-translate-x-1/2 before:animate-rainbow before:bg-[linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] before:bg-size-[200%] before:filter-[blur(0.75rem)]",
          // Size styles
          size === "default" && "h-9 px-4 py-2",
          size === "sm" && "h-8 rounded-xl px-3 text-xs",
          size === "lg" && "h-11 rounded-xl px-8",
          size === "icon" && "size-9",
          className
        )}
        {...props}
      >
        {children}
      </button>
    )
  }
)

RainbowButton.displayName = "RainbowButton"

export { RainbowButton, type RainbowButtonProps }

