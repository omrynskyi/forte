"use client";

// Task D-06 owns this file. D-05 (paystub detail) and D-07 (former employee view) render it.
// Behavior (D16): only when paystub.pdf_available; GET /api/me/paystubs/{item_id}/pdf returns a
// 60-second presigned URL -> window.location.assign(url). On code "pdf_not_ready" say the PDF is
// still being prepared. If the presigned host is unreachable, fall back to the streaming route
// /api/me/paystubs/{item_id}/pdf/file (same auth, served by the API).
import type { Schemas } from "@/lib/api/client";

export function PaystubPdfButton({ paystub }: { paystub: Schemas["PaystubSummary"] }) {
  void paystub;
  return null;
}
