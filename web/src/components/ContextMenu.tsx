/** 轻量右键菜单（卡片右键 / 连线等共用）。 */
import { useEffect, useRef, useState } from "react";

export interface MenuItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}

export interface ContextMenuProps {
  x: number;
  y: number;
  items: MenuItem[];
  onClose: () => void;
  testId?: string;
}

export default function ContextMenu({ x, y, items, onClose, testId }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setPos({
      left: Math.max(4, Math.min(x, window.innerWidth - rect.width - 8)),
      top: Math.max(4, Math.min(y, window.innerHeight - rect.height - 8)),
    });
  }, [x, y]);

  useEffect(() => {
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key === "Escape") onClose();
      if (e.type === "mousedown" && ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [onClose]);

  return (
    <div
      className="ctxmenu"
      ref={ref}
      data-testid={testId ?? "ctxmenu"}
      style={{ left: pos.left, top: pos.top }}
    >
      {items.map((item) => (
        <button
          type="button"
          key={item.label}
          className={`ctx-item${item.danger ? " ctx-danger" : ""}`}
          disabled={item.disabled}
          onClick={() => {
            item.onClick();
            onClose();
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
