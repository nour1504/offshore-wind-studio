import { Accordion, Alert, Badge, Button, Group, List, Modal, Select, SimpleGrid, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { useState } from "react";
import { useVerifyProfile, useSaveProfile } from "../../api/compute";
import type { ComputeProfile, ProfileKind } from "../../api/types";
import { useT } from "../../i18n";
import { Confirm, FieldLabel } from "../../ui/Inputs";
import { PathInput } from "../../ui/PathInput";
import { ErrorState } from "../../ui/States";
import { computeMessages } from "./messages";
import { forRequest, INSTALL_FIELDS, invalid, KIND_ORDER, missing, normalize, sameProfile, withKind } from "./profile";

const ROLES = { wrf_dir: "wrf", wps_dir: "wps", geog_dir: "geog", input_dir: undefined } as const;


/** Edits and saves a profile without connecting to the engine; verification only on request. */
export function ProfileEditor({ initial, isNew, taken, onClose }: { initial: ComputeProfile; isNew: boolean; taken: string[]; onClose: () => void }) {
  const t = useT(computeMessages);
  const [profile, setProfile] = useState(() => structuredClone(initial));
  const save = useSaveProfile();
  const verify = useVerifyProfile();
  const [verifyVersion, setVerifyVersion] = useState("");
  const effective: ComputeProfile = profile;
  const invalids = invalid(effective, taken, isNew);
  const missingFields = missing(effective);
  const valid = invalids.length === 0;
  const dirty = !sameProfile(effective, initial);
  const version = JSON.stringify(forRequest(effective));
  const update = (change: (draft: ComputeProfile) => void) => { const next = structuredClone(profile); change(next); setProfile(next); save.reset(); };
  const textStyle = { input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } };
  const saveProfile = () => save.mutate(normalize(effective), { onSuccess: onClose });
  return <Modal opened onClose={dirty ? () => undefined : onClose} withCloseButton={!dirty} closeOnClickOutside={!dirty} closeOnEscape={!dirty} title={<Group><Text fw={600}>{t("editor")}</Text>{dirty && <Badge color="gray">{t("unsaved")}</Badge>}</Group>} size="xl">
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <TextInput label={t("name")} value={profile.name} maxLength={80} required onChange={e => update(p => { p.name = e.currentTarget.value; })} />
        <TextInput label={<FieldLabel label={t("id")} info={t("idHelp")} />} value={profile.id} disabled={!isNew} maxLength={40} required onChange={e => update(p => { p.id = e.currentTarget.value; })} />
      </SimpleGrid>
      <Select label={t("kind")} data={KIND_ORDER.map(kind => ({ value: kind, label: t(`kinds.${kind}`) }))} value={profile.kind} allowDeselect={false} onChange={value => { if (value) { const next = withKind(profile, value as ProfileKind); setProfile(next); save.reset(); } }} />
      {profile.kind === "wsl" && <Stack gap="md">
        <Text fw={600} size="sm">{t("connection")}</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}><TextInput label={t("distro")} value={profile.wsl_distro} readOnly /><TextInput label={t("wslUser")} value={profile.wsl_user ?? ""} readOnly /></SimpleGrid>
      </Stack>}
      <Stack gap="sm">
        <Text fw={600} size="sm"><FieldLabel label={t("install")} info={t("pathHelp")} /></Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>{INSTALL_FIELDS.map(field => <PathInput key={field} label={t(`paths.${field}`)} value={profile.install[field]} placeholder="/…" machine="engine" profile={isNew ? undefined : initial.id} expect={ROLES[field]} marks={INSTALL_FIELDS.filter(other => other !== field).map(other => profile.install[other]).filter(Boolean)} onChange={value => update(p => { p.install[field] = value; })} />)}</SimpleGrid>
      </Stack>
      <Accordion variant="default" multiple>
        <Accordion.Item value="advanced"><Accordion.Control>{t("env")}</Accordion.Control><Accordion.Panel><Stack>
          <Textarea label={t("env")} description={t("envHelp")} minRows={3} autosize styles={textStyle} value={profile.install.env_setup} onChange={e => update(p => { p.install.env_setup = e.currentTarget.value; })} />
          <TextInput label={t("mpi")} description={t("localMpiHelp")} styles={textStyle} value={profile.resources.mpi_command} onChange={e => update(p => { p.resources.mpi_command = e.currentTarget.value; })} />
          <Textarea label={t("notes")} value={profile.notes} autosize minRows={2} onChange={e => update(p => { p.notes = e.currentTarget.value; })} />
        </Stack></Accordion.Panel></Accordion.Item>
      </Accordion>
      {!valid && <Alert color="red" title={t("invalid")}>{t("localInvalidHelp")}</Alert>}
      {missingFields.length > 0 && <Alert color="gray" title={t("missing")}><List size="sm">{missingFields.map((field, index) => <List.Item key={index}>{"field" in field ? t(`paths.${field.field}`) : field.code === "distro" ? t("distro") : t("mpiHelp")}</List.Item>)}</List></Alert>}
      {save.error && <ErrorState error={save.error} />}
      <Group justify="space-between" wrap="wrap">
        <Button variant="default" loading={verify.isPending} disabled={!valid || missingFields.length > 0} title={t("verifyHelp")} onClick={() => { setVerifyVersion(version); verify.mutate(forRequest(effective)); }}>{t("verify")}</Button>
        <Group>{dirty ? <Confirm title={t("discardTitle")} text={t("discardText")} onConfirm={onClose} confirmLabel={t("discard")}>{open => <Button variant="default" onClick={open}>{t("cancel")}</Button>}</Confirm> : <Button variant="default" onClick={onClose}>{t("cancel")}</Button>}<Button disabled={!valid} loading={save.isPending} onClick={saveProfile}>{t("save")}</Button></Group>
      </Group>
      {verify.error && <ErrorState error={verify.error} />}
      {verify.data && <Stack gap="sm"><Text fw={600}>{t("verifyTitle")}</Text>{verifyVersion !== version ? <Alert color="gray">{t("verificationStale")}</Alert> : <><Badge color={verify.data.reachable ? "teal" : "red"}>{t(verify.data.reachable ? "reachable" : "unreachable")}</Badge>{verify.data.checks.map((check, index) => <Alert key={index} color={check.status === "ok" ? "teal" : check.status === "warn" ? "yellow" : "red"} title={`${t(`check.${check.status}`)} · ${check.label}`}><Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{check.detail}</Text></Alert>)}</>}</Stack>}
    </Stack>
  </Modal>;
}
