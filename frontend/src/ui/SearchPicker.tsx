import { Combobox, Group, Loader, Stack, Text, TextInput, useCombobox } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import type { ReactNode } from "react";

/** One proposal of a search field: a plain title, its code, a short detail and a right-hand note. */
export interface PickerItem {
  value: string;
  title: ReactNode;
  code?: string;
  detail?: ReactNode;
  aside?: ReactNode;
  disabled?: boolean;
}

interface Props {
  label?: ReactNode;
  description?: ReactNode;
  placeholder?: string;
  search: string;
  onSearch: (text: string) => void;
  items: PickerItem[];
  onPick: (value: string) => void;
  /** Shown above the proposals, e.g. "Suggestions" while nothing is typed */
  heading?: ReactNode;
  loading?: boolean;
  empty?: ReactNode;
  /** Enter with no proposal highlighted: what was typed, for names the list does not know */
  onEnter?: (text: string) => void;
  error?: ReactNode;
  "aria-label"?: string;
}

/**
 * A search field that proposes matching entries from the first letters, as a list of readable
 * rows (title, code, detail). Arrow keys move, Enter or a click chooses.
 */
export function SearchPicker({ label, description, placeholder, search, onSearch, items, onPick, heading, loading, empty, onEnter, error, ...rest }: Props) {
  const combobox = useCombobox({ onDropdownClose: () => combobox.resetSelectedOption() });
  return (
    <Combobox store={combobox} onOptionSubmit={(value) => { onPick(value); combobox.closeDropdown(); }} withinPortal position="bottom-start" offset={6}>
      <Combobox.Target>
        <TextInput
          label={label}
          description={description}
          placeholder={placeholder}
          aria-label={rest["aria-label"]}
          value={search}
          error={error}
          leftSection={<IconSearch size={15} stroke={1.7} />}
          rightSection={loading ? <Loader size={14} /> : undefined}
          onChange={(event) => { onSearch(event.currentTarget.value); combobox.openDropdown(); combobox.updateSelectedOptionIndex("active"); }}
          onClick={() => combobox.openDropdown()}
          onFocus={() => combobox.openDropdown()}
          onBlur={() => combobox.closeDropdown()}
          onKeyDown={(event) => {
            if (event.key === "Enter" && combobox.getSelectedOptionIndex() < 0 && onEnter && search.trim()) {
              event.preventDefault();
              onEnter(search.trim());
              combobox.closeDropdown();
            }
          }}
        />
      </Combobox.Target>
      <Combobox.Dropdown className="ows-picker">
        <Combobox.Options mah={340} style={{ overflowY: "auto" }}>
          {heading && items.length > 0 && <Combobox.Header><Text size="xs" c="dimmed">{heading}</Text></Combobox.Header>}
          {items.length === 0
            ? <Combobox.Empty>{loading ? "…" : empty}</Combobox.Empty>
            : items.map((item) => (
              <Combobox.Option key={item.value} value={item.value} disabled={item.disabled} className="ows-picker-option">
                <Group wrap="nowrap" justify="space-between" gap="md" align="flex-start">
                  <Stack gap={2} style={{ minWidth: 0 }}>
                    <Text size="sm" fw={500} lineClamp={1}>{item.title}</Text>
                    <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
                      {item.code && <Text size="xs" ff="monospace" className="ows-picker-code">{item.code}</Text>}
                      {item.detail && <Text size="xs" c="dimmed" lineClamp={1}>{item.detail}</Text>}
                    </Group>
                  </Stack>
                  {item.aside && <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>{item.aside}</Group>}
                </Group>
              </Combobox.Option>
            ))}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}
