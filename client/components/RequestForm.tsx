"use client"

import { useState } from "react"
import { MagicCard } from "@/components/ui/magic-card"
import { ShimmerButton } from "@/components/ui/shimmer-button"
import { cn } from "@/lib/utils"

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

export function RequestForm() {
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
    <MagicCard className="p-6">
      <h2 className="text-2xl font-semibold mb-6 text-slate-50">Request a Song</h2>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label htmlFor="genre" className="block text-sm font-medium text-slate-300 mb-2">
            Genre
          </label>
          <select
            id="genre"
            value={genre}
            onChange={(e) => setGenre(e.target.value as Genre)}
            className={cn(
              "w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700",
              "text-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-500",
              "transition-colors"
            )}
            required
          >
            <option value="">Select a genre</option>
            {genres.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="mood" className="block text-sm font-medium text-slate-300 mb-2">
            Mood
          </label>
          <select
            id="mood"
            value={mood}
            onChange={(e) => setMood(e.target.value as Mood)}
            className={cn(
              "w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700",
              "text-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-500",
              "transition-colors"
            )}
            required
          >
            <option value="">Select a mood</option>
            {moods.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="energy" className="block text-sm font-medium text-slate-300 mb-2">
            Energy Level
          </label>
          <select
            id="energy"
            value={energy}
            onChange={(e) => setEnergy(e.target.value as Energy)}
            className={cn(
              "w-full px-4 py-2 rounded-lg bg-slate-900 border border-slate-700",
              "text-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-500",
              "transition-colors"
            )}
          >
            {energyLevels.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </div>

        {message && (
          <div
            className={cn(
              "p-3 rounded-lg text-sm",
              message.type === "success"
                ? "bg-green-500/20 text-green-300 border border-green-500/30"
                : "bg-red-500/20 text-red-300 border border-red-500/30"
            )}
          >
            {message.text}
          </div>
        )}

        <ShimmerButton
          type="submit"
          disabled={isSubmitting}
          background="rgba(15, 23, 42, 0.8)"
          shimmerColor="#ffffff"
          className="w-full"
        >
          {isSubmitting ? "Submitting..." : "Submit Request"}
        </ShimmerButton>
      </form>
    </MagicCard>
  )
}

