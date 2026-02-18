"use client";

import { cn } from "@/lib/utils";

interface VotePanelProps {
  voteData: {
    options: Record<string, string>;
    tallies: Record<string, number>;
    status: "OPEN" | "CLOSED" | null;
    winnerOption: string | null;
  };
  formattedTime: string;
  isExpired: boolean;
  hasVoted: boolean;
  selectedOption: string | null;
  isSubmitting: boolean;
  error: string | null;
  onSubmitVote: (optionKey: string) => void;
}

export function VotePanel({
  voteData,
  formattedTime,
  isExpired,
  hasVoted,
  selectedOption,
  isSubmitting,
  error,
  onSubmitVote,
}: VotePanelProps) {
  const optionEntries = Object.entries(voteData.options);
  const totalVotes = Object.values(voteData.tallies).reduce((sum, n) => sum + n, 0);
  const voteClosed = voteData.status === "CLOSED" || isExpired;
  const disabled = hasVoted || isSubmitting || voteClosed;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-stone-400">
          {voteClosed ? "Vote Closed" : "Vote for Next Track"}
        </p>
        <span
          className={cn(
            "text-xs font-mono font-semibold tabular-nums",
            voteClosed ? "text-stone-500" : "text-stone-300",
          )}
        >
          {formattedTime}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {optionEntries.map(([key, label]) => {
          const count = voteData.tallies[key] ?? 0;
          const pct = totalVotes > 0 ? Math.round((count / totalVotes) * 100) : 0;
          const isSelected = selectedOption === key;
          const isWinner = voteClosed && voteData.winnerOption === key;

          return (
            <button
              key={key}
              onClick={() => onSubmitVote(key)}
              disabled={disabled}
              className={cn(
                "relative overflow-hidden",
                "flex items-center justify-between gap-2",
                "px-3 py-2 rounded-lg text-sm",
                "border transition-all duration-200",
                "focus:outline-none",
                !disabled &&
                  "bg-stone-800/30 border-stone-700/30 text-stone-200 hover:bg-stone-700/40 hover:border-stone-600/50 cursor-pointer",
                disabled && !isSelected &&
                  "bg-stone-800/20 border-stone-700/20 text-stone-500 cursor-default",
                isSelected &&
                  "bg-emerald-500/10 border-emerald-500/40 text-emerald-300 cursor-default",
                isWinner && "bg-amber-500/10 border-amber-400/50 text-amber-200",
              )}
            >
              {hasVoted && (
                <div
                  className={cn(
                    "absolute inset-y-0 left-0 transition-all duration-500",
                    isSelected ? "bg-emerald-500/10" : "bg-stone-700/10",
                  )}
                  style={{ width: `${pct}%` }}
                />
              )}

              <span className="relative z-10 truncate font-medium">
                {isSelected && <span className="mr-1.5">✓</span>}
                {isWinner && !isSelected && <span className="mr-1.5">★</span>}
                {label}
              </span>

              <span className="relative z-10 flex items-center gap-1.5 shrink-0">
                <span className="text-xs font-mono tabular-nums opacity-70">{count}</span>
                {hasVoted && (
                  <span className="text-xs font-mono tabular-nums opacity-50">({pct}%)</span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      {error && (
        <div className="p-2 rounded-lg text-xs bg-red-500/20 text-red-300 border border-red-500/30">
          {error}
        </div>
      )}
    </div>
  );
}
