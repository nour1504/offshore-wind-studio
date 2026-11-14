/**
 * A row of pills where one is chosen, as the segmented selectors: a pill in the green of the
 * filled buttons glides to the one clicked. Clicking the chosen pill again still calls onChange
 * (the map frames it again).
 */
import { Box } from "@mantine/core";
import type { ReactNode } from "react";

import { Glide, useGlide } from "./Glide";

export interface PillOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

export function Pills({ options, value, onChange, label }: { options: PillOption[]; value: string; onChange: (value: string) => void; label?: string }) {
  const glide = useGlide();
  return (
    <Box ref={glide.parent} className="ows-pills" role="group" aria-label={label}>
      <Glide glide={glide} active={options.some((option) => option.value === value && !option.disabled) ? value : null} className="ows-pill-glide" pill />
      {options.map((option) => (
        <button
          key={option.value}
          ref={glide.item(option.value)}
          type="button"
          className="ows-pill"
          data-active={option.value === value || undefined}
          aria-pressed={option.value === value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </Box>
  );
}
