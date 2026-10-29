import { Button, Group, Stack, Text } from "@mantine/core";
import { IconArrowBackUp, IconInfoCircle } from "@tabler/icons-react";
import { useMemo } from "react";

import type { Case, Issue } from "../../../api/types";
import { useFormat, useT } from "../../../i18n";
import { NumberField } from "../../../ui/Inputs";
import { Fold } from "../../../ui/Fold";
import { domainName, timeSteps } from "./grid";
import { domainMessages } from "./messages";

/** Server checks about the time step (written in English); this block shows them, in grey */
export const isTimeStepIssue = (issue: Issue) => /time.?step|adaptation_domain|target_h?cfl/i.test(issue.message);
// The server's 6 s per km warning, which the block already gives in the user's language
const sameRule = (issue: Issue) => issue.message.startsWith("Effective time steps exceed");

/**
 * WRF's time step: free to change, with its rules in one line and a grey note when the value
 * does not suit the current domains (never red before a launch).
 */
export function TimeStep({ c, update, issues }: { c: Case; update: (change: (c: Case) => void) => void; issues: Issue[] }) {
  const t = useT(domainMessages);
  const f = useFormat();
  const steps = useMemo(() => timeSteps(c.grid, c.namelist_input), [c.grid, c.namelist_input]);
  // 50, 16,7 or 0,56: no needless decimals
  const plain = (x: number) => {
    const r = Math.round(x * 100) / 100;
    return f.number(r, Number.isInteger(r) ? 0 : r < 1 ? 2 : 1);
  };
  const seconds = (s: number) => `${plain(s)} s`;
  const set = (value: number | null) =>
    update((next) => {
      const options = { ...next.namelist_input.domains };
      if (value === null) delete options.time_step;
      else options.time_step = value;
      if (Object.keys(options).length) next.namelist_input.domains = options;
      else delete next.namelist_input.domains;
    });
  const nests = steps.domains.slice(1).flatMap((dt, i) => (dt === null ? [] : [`${domainName(i + 1)} ${seconds(dt)}`]));
  const notes = [
    steps.adaptive && t("timeStepAdaptive"),
    steps.tooLarge.length > 0 && t("timeStepLarge", { names: steps.tooLarge.map(domainName).join(", "), n: steps.automatic }),
    steps.tooSmall && t("timeStepSmall", { factor: plain(steps.automatic / steps.value), n: steps.automatic }),
    ...issues.filter((issue) => isTimeStepIssue(issue) && !sameRule(issue)).map((issue) => issue.message),
  ].filter((note): note is string => Boolean(note));

  return (
    <Fold title={t("timeStep")} aside={`${Math.trunc(steps.value)} s`}>
      <Stack gap="sm">
        <Group align="flex-end" gap="md" wrap="wrap">
          <NumberField
            w={200}
            label={t("timeStepField")}
            info={t("timeStepInfo")}
            unit="s"
            min={1}
            allowDecimal={false}
            value={Math.trunc(steps.value)}
            onValue={set}
          />
          {steps.chosen ? (
            <Button variant="subtle" size="sm" leftSection={<IconArrowBackUp size={16} />} onClick={() => set(null)}>
              {t("timeStepReset", { n: steps.automatic })}
            </Button>
          ) : (
            <Text size="sm" c="dimmed" pb={8}>
              {t("timeStepAuto")}
            </Text>
          )}
        </Group>
        {!steps.adaptive && nests.length > 0 && (
          <Text size="sm" c="dimmed" className="ows-num">
            {t("timeStepNests", { list: nests.join(" · ") })}
          </Text>
        )}
        {notes.map((note, i) => (
          <Group key={i} gap={6} wrap="nowrap" align="flex-start">
            <IconInfoCircle size={16} style={{ color: "var(--ows-muted)", flex: "none", marginTop: 2 }} aria-hidden />
            <Text size="sm" c="dimmed">
              {note}
            </Text>
          </Group>
        ))}
      </Stack>
    </Fold>
  );
}
