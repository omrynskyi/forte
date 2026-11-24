"use client";

import { $api, type Schemas } from "./api/client";

export type Me = Schemas["MeOut"];

/** The signed-in user, or undefined while loading. 401 -> error (redirect to /login). */
export function useMe() {
  return $api.useQuery("get", "/api/auth/me", {}, { retry: false, staleTime: 30_000 });
}

/** Where a signed-in user belongs (D-01 uses this right after login; shells use it as a guard). */
export function homePathFor(me: Me): string {
  if (!me.membership || !me.company) return "/setup";
  if (me.membership.status === "former") return "/me/former";
  if (me.membership.role === "admin") return "/admin";
  if (me.membership.role === "payroll_manager") return "/payroll";
  if (me.onboarding && !me.onboarding.complete) return "/me/onboarding/address";
  return "/me";
}
