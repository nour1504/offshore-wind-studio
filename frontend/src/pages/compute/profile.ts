/**
 * Compute profiles on the client: blank profiles per kind, identifiers, the shape sent to the
 * server, and the same completeness rules as the server (owstudio.core.engine.profiles).
 */
import type { ComputeProfile, ProfileKind } from "../../api/types";

/** Order in which the kinds are presented: the usual case first. */
export const KIND_ORDER: ProfileKind[] = ["wsl", "local"];
export const MANAGED_DISTRO = "OffshoreWindStudio-WRF";
export const MANAGED_USER = "owstudio";

/** The profiles shown: the managed WSL distribution, or this Linux computer. */
export function localProfile(profile: Pick<ComputeProfile, "kind" | "wsl_distro">): boolean {
  return profile.kind === "local" || (profile.kind === "wsl" && profile.wsl_distro === MANAGED_DISTRO);
}

/** The installer's dedicated absolute Linux root, also checked on the backend before use. */
export function validInstallRoot(value: string): boolean {
  const root = value.trim().replace(/\/+$/, "") || "/";
  return /^\/[A-Za-z0-9_./-]+$/.test(root)
    && !["/", "/usr", "/usr/local", "/opt", "/home", "/tmp", "/var", "/root", "/etc"].includes(root)
    && !root.split("/").includes("..");
}

export const ID_PATTERN = /^[a-z0-9-]{1,40}$/;
export const NAME_MAX = 80;

/** The five installation folders, in the order they are presented. */
export const INSTALL_FIELDS = ["wrf_dir", "wps_dir", "geog_dir", "input_dir"] as const;
export type InstallField = (typeof INSTALL_FIELDS)[number];

// Written into namelist.wps, which Fortran reads without expanding ~ or $HOME
const ABSOLUTE_ONLY: InstallField[] = ["wps_dir", "geog_dir"];

/** Lower-case identifier from a name: "WSL Ubuntu 22.04" -> "wsl-ubuntu-22-04". */
export function slug(text: string): string {
  return (
    text
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9-]+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 40)
      .replace(/-$/, "") || "profile"
  );
}

/** ``base``, or ``base-2``, ``base-3``… when already taken. */
export function uniqueId(base: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  const root = slug(base);
  if (!used.has(root)) return root;
  for (let i = 2; ; i += 1) {
    const suffix = `-${i}`;
    const candidate = `${root.slice(0, 40 - suffix.length).replace(/-$/, "")}${suffix}`;
    if (!used.has(candidate)) return candidate;
  }
}

/** A new profile of this kind with the server's defaults. */
export function blankProfile(kind: ProfileKind, name: string, taken: Iterable<string>): ComputeProfile {
  return withKind(
    {
      id: uniqueId(name, taken),
      name,
      kind,
      install: { wrf_dir: "", wps_dir: "", geog_dir: "", env_setup: "", work_dir: "", input_dir: "" },
      resources: { mpi_command: "mpirun -np {ranks}" },
      wsl_distro: kind === "wsl" ? MANAGED_DISTRO : "",
      wsl_user: kind === "wsl" ? MANAGED_USER : "",
      notes: "",
      engine_manifest: {},
    },
    kind,
  );
}

/** The profile with the settings blocks its kind needs (existing values are kept). */
export function withKind(profile: ComputeProfile, kind: ProfileKind): ComputeProfile {
  return {
    ...profile,
    kind,
    wsl_distro: kind === "wsl" ? MANAGED_DISTRO : profile.wsl_distro,
    wsl_user: kind === "wsl" ? MANAGED_USER : profile.wsl_user,
  };
}

/** The profile as the server stores it: text trimmed, WSL fields only for WSL. */
export function normalize(profile: ComputeProfile): ComputeProfile {
  const kind = profile.kind;
  const install = profile.install;
  return {
    // The profile list also carries `missing` and `default`. They are response metadata,
    // not ComputeProfile fields: the server's strict request model rejects either one.
    id: profile.id,
    kind,
    name: profile.name.trim(),
    install: {
      wrf_dir: install.wrf_dir.trim(),
      wps_dir: install.wps_dir.trim(),
      geog_dir: install.geog_dir.trim(),
      work_dir: "",
      input_dir: install.input_dir.trim(),
      env_setup: install.env_setup.replace(/\s+$/, ""),
    },
    resources: { mpi_command: profile.resources.mpi_command.trim() },
    wsl_distro: kind === "wsl" ? profile.wsl_distro.trim() : "",
    wsl_user: kind === "wsl" ? (profile.wsl_user ?? "").trim() : "",
    notes: profile.notes.trim(),
    // The provenance stays only while the profile still points at the engine it describes
    engine_manifest: installedEngine(profile) ? (profile.engine_manifest ?? {}) : {},
  };
}

/** The profile uses the engine the application installed (its folders are unchanged). */
export function installedEngine(profile: ComputeProfile): boolean {
  const root = profile.engine_manifest?.root;
  if (!root) return false;
  const install = profile.install;
  return install.wrf_dir.trim() === `${root}/WRF` && install.wps_dir.trim() === `${root}/WPS` && install.geog_dir.trim() === (profile.engine_manifest.geography?.path ?? "");
}

/** An engine installed before 0.6.2 keeps its data inside it (<engine>/input): where they go now. */
export function oldDataFolder(profile: ComputeProfile): string | null {
  const root = profile.engine_manifest?.root;
  if (!root?.startsWith("/")) return null;
  const folder = profile.install.input_dir.trim().replace(/\/+$/, "");
  if (folder && folder !== `${root}/input` && folder !== `${root}/work`) return null;
  return `${root.slice(0, root.lastIndexOf("/"))}/donnees`;
}

/**
 * A copy the server accepts for a check even before the name and identifier are chosen (they
 * do not change the check).
 */
export function forRequest(profile: ComputeProfile): ComputeProfile {
  const clean = normalize(profile);
  return {
    ...clean,
    id: ID_PATTERN.test(clean.id) ? clean.id : "new-profile",
    name: clean.name ? clean.name.slice(0, NAME_MAX) : "New profile",
  };
}

// ------------------------------------------------------------------------ rules

/** Problems that make the server refuse the profile: saving is not possible until fixed. */
export type Invalid =
  | { code: "name" }
  | { code: "nameLong" }
  | { code: "id" }
  | { code: "idTaken" };

/** What must still be filled in before the engine can be used (saving is possible). */
export type Missing =
  | { code: "unset"; field: InstallField }
  | { code: "relative"; field: InstallField; value: string }
  | { code: "distro" }
  | { code: "ranksPlaceholder" };

export function invalid(profile: ComputeProfile, takenIds: string[], isNew: boolean): Invalid[] {
  const p = profile;
  const out: Invalid[] = [];
  const name = p.name.trim();
  if (!name) out.push({ code: "name" });
  else if (name.length > NAME_MAX) out.push({ code: "nameLong" });
  if (!ID_PATTERN.test(p.id)) out.push({ code: "id" });
  else if (isNew && takenIds.includes(p.id)) out.push({ code: "idTaken" });
  return out;
}

/** Same rules as ComputeProfile.missing() on the server. */
export function missing(profile: ComputeProfile): Missing[] {
  const p = normalize(profile);
  const out: Missing[] = [];
  for (const field of INSTALL_FIELDS) {
    const value = p.install[field];
    const starts = ABSOLUTE_ONLY.includes(field) ? ["/"] : ["/", "~", "$"];
    if (!value) out.push({ code: "unset", field });
    else if (!starts.some((s) => value.startsWith(s))) out.push({ code: "relative", field, value });
  }
  if (p.kind === "wsl" && !p.wsl_distro) out.push({ code: "distro" });
  if (!p.resources.mpi_command.includes("{ranks}")) out.push({ code: "ranksPlaceholder" });
  return out;
}

/** Where the engine is, in one line: the WSL distribution, or this computer. */
export function target(profile: ComputeProfile): string | null {
  return profile.kind === "wsl" ? profile.wsl_distro || null : null;
}

export const sameProfile = (a: ComputeProfile, b: ComputeProfile) => JSON.stringify(normalize(a)) === JSON.stringify(normalize(b));
