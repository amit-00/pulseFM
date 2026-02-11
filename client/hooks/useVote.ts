"use client";

import { useState, useEffect, useCallback, useMemo } from "react";

export interface VoteData {
  options: Record<string, string>;
  tallies: Record<string, number>;
  endTime: number; // Unix timestamp in ms
}

// Dummy data — will be replaced by Firestore listener
function createDummyVoteData(): VoteData {
  return {
    options: {
      a: "Lo-Fi Chill",
      b: "Jazz Fusion",
      c: "Synthwave",
      d: "Ambient Piano",
    },
    tallies: {
      a: 12,
      b: 8,
      c: 15,
      d: 5,
    },
    endTime: Date.now() + 2 * 60 * 1000, // 2 minutes from now
  };
}

function formatTime(seconds: number): string {
  if (seconds <= 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function useVote() {
  const [voteData] = useState<VoteData>(createDummyVoteData);
  const [timeRemaining, setTimeRemaining] = useState<number>(() =>
    Math.max(0, Math.ceil((createDummyVoteData().endTime - Date.now()) / 1000))
  );
  const [hasVoted, setHasVoted] = useState(false);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Countdown timer
  useEffect(() => {
    const endTime = voteData.endTime;

    const tick = () => {
      const remaining = Math.max(0, Math.ceil((endTime - Date.now()) / 1000));
      setTimeRemaining(remaining);
    };

    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [voteData.endTime]);

  const isExpired = timeRemaining <= 0;
  const formattedTime = useMemo(() => formatTime(timeRemaining), [timeRemaining]);

  const submitVote = useCallback(
    async (optionKey: string) => {
      if (hasVoted || isSubmitting || isExpired) return;

      setIsSubmitting(true);
      setError(null);

      try {
        const response = await fetch("/api/vote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ option: optionKey }),
        });

        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.error || "Vote failed");
        }

        setHasVoted(true);
        setSelectedOption(optionKey);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Vote failed");
      } finally {
        setIsSubmitting(false);
      }
    },
    [hasVoted, isSubmitting, isExpired]
  );

  return {
    voteData,
    timeRemaining,
    formattedTime,
    isExpired,
    hasVoted,
    selectedOption,
    isSubmitting,
    error,
    submitVote,
  };
}

