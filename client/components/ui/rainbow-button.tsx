import React from "react"
import { cn } from "@/lib/utils"

interface RainbowButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline"
}

const RainbowButton = React.forwardRef<HTMLButtonElement, RainbowButtonProps>(
  ({ className, variant = "default", children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "relative cursor-pointer group animate-rainbow",
          "inline-flex items-center justify-center gap-2 shrink-0",
          "rounded-lg outline-none",
          "text-sm font-medium whitespace-nowrap",
          "disabled:pointer-events-none disabled:opacity-50",
          variant === "default" &&
            "border-0 bg-[linear-gradient(#121213,#121213),linear-gradient(#121213_50%,rgba(18,18,19,0.6)_80%,rgba(18,18,19,0)),linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] bg-[length:200%] text-white [background-clip:padding-box,border-box,border-box] [background-origin:border-box] [border:2px_solid_transparent] before:absolute before:bottom-[-20%] before:left-1/2 before:z-0 before:h-1/5 before:w-3/5 before:-translate-x-1/2 before:animate-rainbow before:bg-[linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] before:bg-[length:200%] before:[filter:blur(0.75rem)]",
          variant === "outline" &&
            "border border-transparent bg-[linear-gradient(#0a0a0a,#0a0a0a),linear-gradient(#0a0a0a_50%,rgba(10,10,10,0.6)_80%,rgba(10,10,10,0)),linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] bg-[length:200%] text-white [background-clip:padding-box,border-box,border-box] [background-origin:border-box] before:absolute before:bottom-[-20%] before:left-1/2 before:z-0 before:h-1/5 before:w-3/5 before:-translate-x-1/2 before:animate-rainbow before:bg-[linear-gradient(90deg,hsl(330,100%,50%),hsl(260,80%,60%),hsl(210,100%,50%),hsl(195,90%,60%),hsl(330,100%,50%))] before:bg-[length:200%] before:[filter:blur(0.75rem)]",
          "px-4 py-2",
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

export { RainbowButton }

