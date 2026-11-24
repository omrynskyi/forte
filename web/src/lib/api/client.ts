/**
 * Typed API client. Types come from api/openapi.json (`make gen`), so a backend schema change is a
 * TypeScript error here, not a runtime surprise.
 *
 *   // in a client component
 *   const { data, isPending, error } = $api.useQuery("get", "/api/runs/{run_id}", {
 *     params: { path: { run_id } },
 *   });
 *   const approve = $api.useMutation("post", "/api/runs/{run_id}/approve");
 *   approve.mutate({ params: { path: { run_id } }, body: {} });
 *
 * Errors: every API error body is {"detail": {"code", "message"}}. Show `message` to the user
 * with apiErrorMessage(error); branch on apiErrorCode(error) (e.g. "past_cutoff").
 */
import createFetchClient from "openapi-fetch";
import createClient from "openapi-react-query";

import type { paths } from "./schema";

export const fetchClient = createFetchClient<paths>({
  baseUrl: "", // same origin; next.config.ts proxies /api/* to FastAPI
  credentials: "include",
});

export const $api = createClient(fetchClient);

export type ApiErrorBody = { detail?: { code?: string; message?: string } | unknown };

export function apiErrorCode(error: unknown): string | undefined {
  const detail = (error as ApiErrorBody | undefined)?.detail;
  return typeof detail === "object" && detail && "code" in detail
    ? String((detail as { code: unknown }).code)
    : undefined;
}

export function apiErrorMessage(error: unknown, fallback = "Something went wrong. Try again."): string {
  const detail = (error as ApiErrorBody | undefined)?.detail;
  if (typeof detail === "object" && detail && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (Array.isArray(detail)) return "Some fields need another look."; // FastAPI 422 validation
  return fallback;
}

export type Schemas = import("./schema").components["schemas"];
