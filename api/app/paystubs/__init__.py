"""Paystub presentation and PDFs. Modules (created by their tasks):
- templates.py  (A-06) plain-language headline + per-line explanations (PAY-1). Copy lives here.
- pdf.py        (A-12) render_paystub_pdf(detail: PaystubDetail) -> bytes, with ReportLab.
                Deterministic input -> PDF; no network, no DB access.
- pdf_store.py  (A-13) store_pdfs_for_run(run_id): render once per Paystub with NULL
                pdf_object_key, put to StorageAdapter, then set key/sha256/version_id/rendered_at.
"""
