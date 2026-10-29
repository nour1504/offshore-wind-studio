import { Alert, Button, Center, Group, Skeleton, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconAlertTriangle, IconInbox } from "@tabler/icons-react";
import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { common } from "../i18n/common";
import { useT } from "../i18n";

interface EmptyProps {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}

/** Nothing to show yet: says why and what to do next. */
export function EmptyState({ icon, title, children, action }: EmptyProps) {
  return (
    <Center py="xl" px="md">
      <Stack align="center" gap="sm" maw={460} ta="center">
        <ThemeIcon size={52} radius="xl" variant="light" color="gray" className="ows-empty-icon">
          {icon ?? <IconInbox size={26} stroke={1.5} />}
        </ThemeIcon>
        <Title order={3}>{title}</Title>
        {children && (
          <Text c="dimmed" size="sm">
            {children}
          </Text>
        )}
        {action && <Group mt="xs">{action}</Group>}
      </Stack>
    </Center>
  );
}

/** Placeholder with the rough shape of the content being loaded. */
export function LoadingState({ rows = 3, height = 18 }: { rows?: number; height?: number }) {
  const t = useT(common);
  return (
    <Stack gap="sm" aria-busy="true" aria-label={t("loading")}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={height} width={`${100 - i * 12}%`} radius="sm" />
      ))}
    </Stack>
  );
}

/** A failed request: the server's explanation and a way to try again. */
export function ErrorState({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: ReactNode }) {
  const t = useT(common);
  const messages = error instanceof ApiError ? error.messages : [error instanceof Error ? error.message : String(error)];
  return (
    <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} title={title ?? t("error")}>
      <Stack gap={4}>
        {messages.map((m, i) => (
          <Text key={i} size="sm" style={{ whiteSpace: "pre-wrap" }}>
            {m}
          </Text>
        ))}
        {onRetry && (
          <Group mt={4}>
            <Button size="xs" variant="light" color="red" onClick={onRetry}>
              {t("retry")}
            </Button>
          </Group>
        )}
      </Stack>
    </Alert>
  );
}

/** Renders loading, error or the content of a query. */
export function QueryView<T>({
  query,
  children,
  loading,
  empty,
}: {
  query: { data: T | undefined; isLoading: boolean; error: unknown; refetch: () => unknown };
  children: (data: T) => ReactNode;
  loading?: ReactNode;
  /** Shown instead of children when it returns something for the data */
  empty?: (data: T) => ReactNode | null;
}) {
  if (query.isLoading) return <>{loading ?? <LoadingState />}</>;
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data === undefined) return null;
  const nothing = empty?.(query.data);
  return <>{nothing ?? children(query.data)}</>;
}
