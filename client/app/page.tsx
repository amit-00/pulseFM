import { SynthesizerPlayer } from "@/components/SynthesizerPlayer";

export default function Home() {
  return (
    <div className="min-h-screen h-screen w-full bg-stone-950">
      <div className="h-[480px] max-w-7xl mx-auto">
        <SynthesizerPlayer />
      </div>
    </div>
  );
}
