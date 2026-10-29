/** HTTP calls to the application server, with readable errors. */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
  }

  /** Separate messages when the server sent a list ({errors: [...]}) */
  get messages(): string[] {
    const d = this.detail as { errors?: unknown } | null;
    if (d && typeof d === "object" && Array.isArray(d.errors)) return d.errors.map(String);
    return [this.message];
  }
}

// FastAPI error bodies: a string, a validation list, or {errors: [...]}
export function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const where = (d.loc ?? []).filter((p) => p !== "body").join(" › ");
        return where ? `${where}: ${d.msg}` : String(d.msg);
      })
      .join("\n");
  }
  if (detail && typeof detail === "object" && "errors" in detail) {
    return (detail as { errors: unknown[] }).errors.map(String).join("\n");
  }
  return detail === undefined ? "" : JSON.stringify(detail);
}

export type Query = Record<string, string | number | boolean | null | undefined | readonly string[]>;

// The language of the window, sent with every request so that the server answers in it
let language = "fr";
export function setRequestLanguage(lang: string) {
  language = lang;
}
const languageHeader = () => ({ "X-OWS-Lang": language });

/** An address opened directly (a download): it carries the language too. */
export function withLanguage(path: string): string {
  return withQuery(path, { lang: language });
}

export function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    // A list is sent as the key repeated (FastAPI reads list[str] so)
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item));
    else if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}${path.includes("?") ? "&" : "?"}${text}` : path;
}

async function failure(response: Response): Promise<ApiError> {
  const text = await response.text().catch(() => "");
  let detail: unknown = text || response.statusText;
  try {
    detail = (JSON.parse(text) as { detail?: unknown }).detail ?? detail;
  } catch {
    // not JSON: keep the text
  }
  return new ApiError(describe(detail) || `HTTP ${response.status}`, response.status, detail);
}

export async function request<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  options: { query?: Query; signal?: AbortSignal } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(withQuery(path, options.query), {
      method,
      headers: body === undefined ? languageHeader() : { ...languageHeader(), "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: options.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("The application server is not responding.", 0, null);
  }
  if (!response.ok) throw await failure(response);
  if (response.status === 204) return undefined as T;
  const type = response.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? response.json() : response.text()) as Promise<T>;
}

/** Sends a file selected by the user (multipart form). */
export const get = <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, undefined, { query, signal });
export const post = <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, body ?? {}, { query });
export const put = <T>(path: string, body: unknown) => request<T>("PUT", path, body);
export const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
export const del = <T = void>(path: string, query?: Query) => request<T>("DELETE", path, undefined, { query });
