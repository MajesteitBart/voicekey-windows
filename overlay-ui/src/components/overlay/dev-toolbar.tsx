import type { OverlayState } from "@/types/overlay";
import { Button } from "@/components/ui/button";

interface DevToolbarProps {
  onSetState: (next: OverlayState) => void;
}

const states: Array<{ label: string; value: OverlayState }> = [
  {
    label: "Listening (quiet)",
    value: {
      connection: "online",
      listening: "listening",
      processing: "idle",
      target: "selected",
      level: 0.03,
      visible: true,
      message: "Listening...",
    },
  },
  {
    label: "Listening (audio)",
    value: {
      connection: "online",
      listening: "listening",
      processing: "idle",
      target: "selected",
      level: 0.74,
      visible: true,
      message: null,
    },
  },
  {
    label: "Processing",
    value: {
      connection: "online",
      listening: "ready",
      processing: "processing",
      target: "selected",
      level: 0,
      visible: true,
      message: "Processing...",
    },
  },
  {
    label: "Ready (hidden)",
    value: {
      connection: "online",
      listening: "ready",
      processing: "idle",
      target: "selected",
      level: 0,
      visible: false,
      message: null,
    },
  },
  {
    label: "No target",
    value: {
      connection: "online",
      listening: "ready",
      processing: "idle",
      target: "not_selected",
      level: 0,
      visible: true,
      message: null,
    },
  },
];

export function DevToolbar({ onSetState }: DevToolbarProps) {
  return (
    <div className="pointer-events-auto absolute bottom-3 left-3 right-3 z-10 flex flex-wrap gap-2 rounded-lg border border-border/60 bg-card/85 p-2 shadow-lg backdrop-blur-sm">
      {states.map((item) => (
        <Button key={item.label} size="sm" variant="secondary" onClick={() => onSetState(item.value)}>
          {item.label}
        </Button>
      ))}
    </div>
  );
}
