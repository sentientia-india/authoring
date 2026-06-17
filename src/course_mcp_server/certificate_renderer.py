from __future__ import annotations

from html import escape


def render_certificate_html(certificate: dict) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Certificate {escape(str(certificate.get("certificate_id", "")))}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f5f7fb; color: #172033; }}
    main {{ max-width: 900px; margin: 48px auto; padding: 56px; background: white; border: 10px solid #2563eb; }}
    h1 {{ font-size: 42px; margin: 0 0 24px; }}
    .name {{ font-size: 34px; font-weight: 700; margin: 20px 0; }}
    .meta {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 36px; }}
    .meta div {{ border-top: 1px solid #d8deea; padding-top: 12px; }}
  </style>
</head>
<body>
  <main>
    <p>Certificate of Completion</p>
    <h1>{escape(str(certificate.get("course_title", "")))}</h1>
    <p>Awarded to</p>
    <p class="name">{escape(str(certificate.get("learner_name", "")))}</p>
    <p>Score: {escape(str(certificate.get("score", "")))}%</p>
    <section class="meta">
      <div>ID: {escape(str(certificate.get("certificate_id", "")))}</div>
      <div>Issued: {escape(str(certificate.get("issued_date", "")))}</div>
      <div>Learner: {escape(str(certificate.get("learner_id", "")))}</div>
      <div>Recertification due: {escape(str(certificate.get("recertification_due_date", "")))}</div>
    </section>
  </main>
</body>
</html>
"""
