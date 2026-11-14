import { IconFocusCentered, type Icon } from "@tabler/icons-react";

import { type PillOption, Pills } from "../Pills";

/** A choice in a map's top left corner: an icon and a label, then one pill per option. */
export function MapChoice({ label, value, options, onChange, icon: Glyph = IconFocusCentered }: {
  label: string;
  value: string;
  options: PillOption[];
  onChange: (value: string) => void;
  icon?: Icon;
}) {
  return (
    <div className="ows-map-choice">
      <span className="ows-map-choice-label" aria-hidden="true"><Glyph size={14} />{label}</span>
      <Pills label={label} value={value} options={options} onChange={onChange} />
    </div>
  );
}
