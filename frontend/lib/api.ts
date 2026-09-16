let managerCsrf = "";
let candidateCsrf = "";
export function setCsrf(value: string, candidate = false) {
  if (candidate) candidateCsrf = value;
  else managerCsrf = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
  candidate = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("x-csrf-token", candidate ? candidateCsrf : managerCsrf);
  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("content-type")
  )
    headers.set("content-type", "application/json");
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ApiError(
      response.status,
      typeof data.detail === "string"
        ? data.detail
        : "Please check your input and try again.",
    );
  return data;
}
export const post = <T = any>(
  path: string,
  body?: unknown,
  candidate = false,
) =>
  api<T>(
    path,
    {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    },
    candidate,
  );
export async function checksum(blob: Blob) {
  return Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
    ),
  )
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
export async function uploadFile(
  upload: { url: string; method: string; headers: Record<string, string> },
  blob: Blob,
  signal?: AbortSignal,
) {
  const result = await fetch(upload.url, {
    method: upload.method,
    headers: upload.headers,
    body: blob,
    signal,
  });
  if (!result.ok)
    throw new Error(
      `Upload failed (HTTP ${result.status}). Check the connection and retry.`,
    );
}
export const readable = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
