import { deriveMode } from "@/lib/overlay";
import type { OverlayState } from "@/types/overlay";

interface VoiceOverlayProps {
  state: OverlayState;
}

export function VoiceOverlay({ state }: VoiceOverlayProps) {
  if (!state.visible) return null;

  const level = Math.max(0, Math.min(1, Number.isFinite(state.level) ? state.level : 0));
  const mode = deriveMode(state, level);

  return (
    <div className="pointer-events-none relative flex h-[126px] w-[194px] items-center justify-center select-none">
      <div className="rounded-md border border-zinc-400/40 bg-zinc-900/90 px-3 py-2 text-center text-[13px] leading-5 text-white backdrop-blur">
        <div>{mode}</div>
        <div>{state.listening}</div>
        <div>{state.processing}</div>
        {state.message ? <div>{state.message}</div> : null}
      </div>
    </div>
  );
}
