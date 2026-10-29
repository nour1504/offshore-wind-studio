import { ScrollArea, Table, Text, UnstyledButton } from "@mantine/core";
import { IconArrowDown, IconArrowUp, IconArrowsSort } from "@tabler/icons-react";
import { type ReactNode, useMemo, useState } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Cell content; defaults to row[key] */
  render?: (row: T) => ReactNode;
  /** Value used for sorting; sorting is enabled when given */
  sortValue?: (row: T) => number | string | null | undefined;
  align?: "left" | "right" | "center";
  width?: number | string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  selected?: string | null;
  maxHeight?: number;
  caption?: string;
}

/** A sortable table with a sticky header, readable numbers and keyboard-reachable rows. */
export function DataTable<T>({ columns, rows, rowKey, empty, onRowClick, selected, maxHeight, caption }: DataTableProps<T>) {
  const [sort, setSort] = useState<{ key: string; desc: boolean } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return rows;
    const value = column.sortValue;
    return [...rows].sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      const order = va < vb ? -1 : 1;
      return sort.desc ? -order : order;
    });
  }, [rows, columns, sort]);

  const table = (
    <Table stickyHeader={Boolean(maxHeight)} striped={false} highlightOnHover={Boolean(onRowClick)} aria-label={caption}>
      <Table.Thead>
        <Table.Tr>
          {columns.map((c) => {
            const active = sort?.key === c.key;
            const Icon = !active ? IconArrowsSort : sort.desc ? IconArrowDown : IconArrowUp;
            return (
              <Table.Th key={c.key} style={{ textAlign: c.align, width: c.width, whiteSpace: "nowrap" }}>
                {c.sortValue ? (
                  <UnstyledButton
                    onClick={() => setSort(active ? { key: c.key, desc: !sort.desc } : { key: c.key, desc: false })}
                    style={{ display: "inline-flex", gap: 4, alignItems: "center", fontWeight: 600, fontSize: "inherit", color: "inherit" }}
                    aria-sort={active ? (sort.desc ? "descending" : "ascending") : undefined}
                  >
                    {c.header}
                    <Icon size={13} style={{ opacity: active ? 1 : 0.4 }} />
                  </UnstyledButton>
                ) : (
                  c.header
                )}
              </Table.Th>
            );
          })}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {sorted.length === 0 ? (
          <Table.Tr>
            <Table.Td colSpan={columns.length}>
              <Text c="dimmed" size="sm" ta="center" py="md">
                {empty ?? "–"}
              </Text>
            </Table.Td>
          </Table.Tr>
        ) : (
          sorted.map((row) => {
            const key = rowKey(row);
            return (
              <Table.Tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
                style={{ cursor: onRowClick ? "pointer" : undefined }}
                bg={selected === key ? "var(--mantine-primary-color-light)" : undefined}
                aria-selected={selected === key || undefined}
              >
                {columns.map((c) => (
                  <Table.Td key={c.key} style={{ textAlign: c.align }} className={c.align === "right" ? "ows-num" : undefined}>
                    {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "–")}
                  </Table.Td>
                ))}
              </Table.Tr>
            );
          })
        )}
      </Table.Tbody>
    </Table>
  );

  return maxHeight ? <ScrollArea.Autosize mah={maxHeight}>{table}</ScrollArea.Autosize> : <Table.ScrollContainer minWidth={480}>{table}</Table.ScrollContainer>;
}
