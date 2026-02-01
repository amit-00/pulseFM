import { SynthesizerPlayer } from "@/components/SynthesizerPlayer";

export default function Home() {
  return (
    <div className="min-h-screen h-screen w-full bg-slate-950">
      <div className="h-[480px] max-w-5xl mx-auto">
        <SynthesizerPlayer />
      </div>
    </div>
  );
}
