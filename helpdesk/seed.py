"""
The fictional sample library. Everything here is invented for the demo.

One PDF (the employee handbook, readable by everyone) plus short Markdown
documents with narrower audiences, so permission filtering has something
real to do.
"""

from __future__ import annotations

from pathlib import Path

from . import ingest

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "samples" / "harbor-lane-handbook.pdf"

DOCS = [
    ("Pay and payroll", ["everyone"], """# Pay and payroll

## Pay days
Everyone is paid every other Friday by direct deposit. If a pay day falls on a public holiday, you're paid the working day before.

## Pay reviews
Pay reviews happen once a year in March. Ask your manager if you have questions about your own pay.
"""),
    ("Speaking up", ["everyone"], """# Speaking up

## Reporting a concern
If you experience or see harassment, discrimination or anything unsafe, tell your manager or email people-team@harborlane.example. You can also use the anonymous hotline listed on the staff noticeboard.

## What happens next
The people team will acknowledge your report. Retaliation against anyone who raises a concern in good faith is never tolerated.
"""),
    ("Manager guide", ["managers"], """# Manager guide

## Salary bands 2026
Barista: $19 to $23 per hour. Shift lead: $23 to $27 per hour. Roastery supervisor: $68,000 to $82,000 a year. Cafe manager: $72,000 to $88,000 a year. The 2027 pay review budget is 4% of payroll.

## Managing underperformance
Start with a documented conversation. If nothing changes within 30 days, open a 60-day performance plan with the people team. Never discuss someone's plan with other staff.
"""),
    ("Q1 2027 restructuring plan (draft)", ["managers", "finance"], """# Q1 2027 restructuring plan (draft)

## Proposal
Close the Dock Street cafe at the end of March 2027 because its lease cost has doubled. Six roles are affected.

## Commitments
Offer every affected person a transfer to Mill Yard or Pier Road before any redundancy. Nothing is shared with staff until the plan is approved.
"""),
    ("Finance procedures", ["finance"], """# Finance procedures

## Q3 2026 results
Revenue was $4.2 million, up 11% on last year. Gross margin fell to 58% because green coffee prices rose. Wholesale grew fastest; Dock Street was the only cafe that lost money.

## Supplier bank detail changes
Never change a supplier's bank details because of an email. Call the supplier on the number already on file, and get a second approver in finance before saving the change.
"""),
    ("Investigations procedure", ["people-team"], """# Investigations procedure

## Opening a case
When a concern is reported, open a case within two business days and acknowledge the person who raised it.

## Running the investigation
Interview the people involved separately and keep notes in the case system only. Outcomes are shared only with those who need to know.
"""),
]


def load_sample_library(client, settings, progress=None) -> list[ingest.IngestResult]:
    results = [ingest.ingest(client, settings, SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), "Employee handbook",
                             ["everyone"], progress)]
    for title, groups, md in DOCS:
        results.append(ingest.ingest(client, settings, f"{title}.md", md.encode(), title, groups, progress))
    return results
