import { LiveWaveform } from "@/components/ui/live-waveform";
import { bubbleLabel, deriveMode, modePalette } from "@/lib/overlay";
import type { OverlayState } from "@/types/overlay";

interface VoiceOverlayProps {
  state: OverlayState;
}

export function VoiceOverlay({ state }: VoiceOverlayProps) {
  if (!state.visible) return null;

  const level = Math.max(0, Math.min(1, Number.isFinite(state.level) ? state.level : 0));
  const mode = deriveMode(state, level);
  const palette = modePalette(mode);
  const bubbleText = bubbleLabel(state, mode);
  const isListening = mode === "listening_audio";
  const isProcessing = mode === "processing";
  const waveformLevel = level;
  const idleLineStyle = mode === "listening_wait" ? "solid" : "dotted";

  return (
    <div className="pointer-events-none relative select-none" style={{ width: 194, height: 126 }}>
      {bubbleText ? (
        <div className="absolute left-1/2 top-[14px] z-10 -translate-x-1/2">
          <div className="relative rounded-[7px] border border-[#75757566] bg-[#2c2c2cf2] px-3 py-[9px] text-[14px] leading-5 text-white shadow-[0_8px_16px_rgba(0,0,0,0.16)] backdrop-blur-[22px]">
            {bubbleText}
            <span className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 border-l-[7px] border-r-[7px] border-t-[7px] border-l-transparent border-r-transparent border-t-[#2c2c2cf2]" />
          </div>
        </div>
      ) : null}

      <div className="absolute bottom-4 left-1/2 h-[47px] w-[160px] -translate-x-1/2">
        <div className="absolute inset-0 rounded-[7px] bg-[#2e2e2eeb] shadow-[0_2px_6px_rgba(0,0,0,0.15),0_9px_18px_rgba(0,0,0,0.19)] backdrop-blur-[30px]" />
        <div className="absolute inset-0 rounded-[7px] border border-[#75757566]" />
        <div className="absolute left-2 right-2 top-[7px] h-px bg-[#3a3a3a]" />

        <div className="absolute inset-[1px] overflow-hidden rounded-[6px]">
          <LiveWaveform
            active={isListening}
            processing={isProcessing}
            level={waveformLevel}
            mode="static"
            barWidth={3}
            barGap={1.2}
            barRadius={1.5}
            barHeight={4}
            sensitivity={1.1}
            fadeEdges
            fadeWidth={26}
            updateRate={20}
            barColor={palette.main}
            idleLineStyle={idleLineStyle}
            className="h-full w-full"
          />
         
        </div>
         <span>mode: {mode}</span>
      </div>
    </div>
  );
}
