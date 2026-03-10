"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { RainbowButton } from "@/components/ui/rainbow-button"

type Genre = "pop" | "rock" | "hip_hop" | "jazz" | "classical" | "electronic" | "lofi" | "rnb"
type Mood = "happy" | "sad" | "calm" | "exciting" | "romantic" | "party"
type Energy = "low" | "mid" | "high"

const genres: { value: Genre; label: string }[] = [
  { value: "pop", label: "Pop" },
  { value: "rock", label: "Rock" },
  { value: "hip_hop", label: "Hip Hop" },
  { value: "jazz", label: "Jazz" },
  { value: "classical", label: "Classical" },
  { value: "electronic", label: "Electronic" },
  { value: "lofi", label: "Lo-Fi" },
  { value: "rnb", label: "R&B" },
]

const moods: { value: Mood; label: string }[] = [
  { value: "happy", label: "Happy" },
  { value: "sad", label: "Sad" },
  { value: "calm", label: "Calm" },
  { value: "exciting", label: "Exciting" },
  { value: "romantic", label: "Romantic" },
  { value: "party", label: "Party" },
]

const energyLevels: { value: Energy; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "mid", label: "Mid" },
  { value: "high", label: "High" },
]

interface RequestFormProps {
  isPlaying?: boolean
}

export function RequestForm({ isPlaying = false }: RequestFormProps) {
  const [genre, setGenre] = useState<Genre | "">("")
  const [mood, setMood] = useState<Mood | "">("")
  const [energy, setEnergy] = useState<Energy>("mid")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!genre || !mood) {
      setMessage({ type: "error", text: "Please select both genre and mood" })
      return
    }

    setIsSubmitting(true)
    setMessage(null)

    try {
      const response = await fetch("/api/requests", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          genre,
          mood,
          energy,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || "Failed to create request")
      }

      const data = await response.json()
      setMessage({
        type: "success",
        text: `Request created! ID: ${data.request_id}`,
      })

      // Reset form
      setGenre("")
      setMood("")
      setEnergy("mid")
    } catch (error) {
      setMessage({
        type: "error",
        text: error instanceof Error ? error.message : "Failed to create request",
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div>
      <p className="text-xs font-medium text-stone-400 mb-2">Request a Song</p>

      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <div className="flex-1 flex flex-col sm:flex-row gap-2">
          <select
            id="genre"
            value={genre}
            onChange={(e) => setGenre(e.target.value as Genre)}
            className={cn(
              "flex-1 pl-3 pr-8 py-2 rounded-lg bg-stone-800/30 border border-stone-700/30",
              "text-stone-50 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50",
              "transition-colors appearance-none cursor-pointer",
              "bg-[url('data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2012%2012%22%3E%3Cpath%20fill%3D%22%23a8a29e%22%20d%3D%22M2%204l4%204%204-4%22%2F%3E%3C%2Fsvg%3E')]",
              "bg-no-repeat bg-position-[right_0.75rem_center]"
            )}
            required
          >
            <option value="">Genre</option>
            {genres.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>

          <select
            id="mood"
            value={mood}
            onChange={(e) => setMood(e.target.value as Mood)}
            className={cn(
              "flex-1 pl-3 pr-8 py-2 rounded-lg bg-stone-800/30 border border-stone-700/30",
              "text-stone-50 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50",
              "transition-colors appearance-none cursor-pointer",
              "bg-[url('data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2012%2012%22%3E%3Cpath%20fill%3D%22%23a8a29e%22%20d%3D%22M2%204l4%204%204-4%22%2F%3E%3C%2Fsvg%3E')]",
              "bg-no-repeat bg-position-[right_0.75rem_center]"
            )}
            required
          >
            <option value="">Mood</option>
            {moods.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>

          <select
            id="energy"
            value={energy}
            onChange={(e) => setEnergy(e.target.value as Energy)}
            className={cn(
              "flex-1 pl-3 pr-8 py-2 rounded-lg bg-stone-800/30 border border-stone-700/30",
              "text-stone-50 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50",
              "transition-colors appearance-none cursor-pointer",
              "bg-[url('data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2012%2012%22%3E%3Cpath%20fill%3D%22%23a8a29e%22%20d%3D%22M2%204l4%204%204-4%22%2F%3E%3C%2Fsvg%3E')]",
              "bg-no-repeat bg-position-[right_0.75rem_center]"
            )}
          >
            {energyLevels.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </div>

        {/* Request Button with Rainbow outline effect when playing */}
        <div className="relative">
          {/* Base button - always visible, behind rainbow effect */}
          <button
            type="submit"
            disabled={!isPlaying || isSubmitting}
            className={cn(
              "relative flex items-center justify-center",
              "px-4 py-2 rounded-sm",
              "transition-all duration-200",
              "focus:outline-none",
              "active:scale-95",
              "bg-stone-800/50",
              "text-sm font-medium whitespace-nowrap",
              "transition-colors duration-700",
              isPlaying ? "text-white" : "text-stone-100",
              "disabled:pointer-events-none disabled:opacity-50",
              "z-0"
            )}
          >
            {isSubmitting ? "..." : "Request"}
          </button>

          {/* Rainbow button overlay - fades in/out when playing */}
          <div
            className={cn(
              "absolute inset-0 transition-opacity duration-700 ease-in-out z-10",
              isPlaying && !isSubmitting ? "opacity-100" : "opacity-0 pointer-events-none"
            )}
          >
            <RainbowButton
              type="submit"
              disabled={isSubmitting}
              variant="outline"
              className="w-full"
            >
              {isSubmitting ? "..." : "Request"}
            </RainbowButton>
          </div>
        </div>
      </form>

      {message && (
        <div
          className={cn(
            "mt-2 p-2 rounded-lg text-xs",
            message.type === "success"
              ? "bg-green-500/20 text-green-300 border border-green-500/30"
              : "bg-red-500/20 text-red-300 border border-red-500/30"
          )}
        >
          {message.text}
        </div>
      )}
    </div>
  )
}



