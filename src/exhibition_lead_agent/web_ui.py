import io
import csv
import json
from typing import Optional
from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session

from exhibition_lead_agent.db.database import get_db, init_db
from exhibition_lead_agent.db.models import BrandDB, ContactDB, FieldValueDB, PortfolioDB, DraftDB

init_db()
app = FastAPI(title="Exhibition Lead Agent - Review UI")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Exhibition Lead Agent - Review Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 20px; background: #f8f9fa; }
        h1 { color: #1a73e8; }
        .container { display: flex; gap: 20px; }
        .main-table { flex: 2; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .side-panel { flex: 1; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #e0e0e0; font-size: 14px; }
        th { background: #f1f3f4; }
        .badge { padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
        .badge-qualified { background: #e6f4ea; color: #137333; }
        .badge-rejected { background: #fce8e6; color: #c5221f; }
        .badge-email { background: #e8f0fe; color: #1a73e8; }
        .btn { padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; }
        .btn-approve { background: #34a853; color: white; }
        .btn-reject { background: #ea4335; color: white; }
        .btn-export { background: #1a73e8; color: white; padding: 10px 16px; text-decoration: none; display: inline-block; margin-bottom: 15px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>Exhibition Lead Agent — Review Dashboard</h1>
    <a href="/export/csv" class="btn-export">Export Approved Drafts (CSV)</a>

    <div class="container">
        <div class="main-table">
            <h2>Brand Leads & Drafts</h2>
            <table>
                <thead>
                    <tr>
                        <th>Brand Name</th>
                        <th>Status</th>
                        <th>Contact Bucket</th>
                        <th>Website</th>
                        <th>Draft Subject</th>
                        <th>Draft Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in items %}
                    <tr>
                        <td><strong>{{ item.brand.name }}</strong></td>
                        <td><span class="badge badge-{{ item.brand.qualification_status }}">{{ item.brand.qualification_status }}</span></td>
                        <td><span class="badge badge-email">{{ item.brand.contact_bucket or 'pending' }}</span></td>
                        <td>
                            {% if item.brand.website %}
                            <a href="{{ item.brand.website }}" target="_blank">Link</a>
                            {% else %}
                            Unresolved
                            {% endif %}
                        </td>
                        <td>{{ item.draft.subject if item.draft else 'No draft' }}</td>
                        <td>{{ item.draft.status if item.draft else 'N/A' }}</td>
                        <td>
                            {% if item.draft %}
                            <form action="/drafts/{{ item.draft.id }}/approve" method="post" style="display:inline;">
                                <button class="btn btn-approve" type="submit">Approve</button>
                            </form>
                            <form action="/drafts/{{ item.draft.id }}/reject" method="post" style="display:inline;">
                                <button class="btn btn-reject" type="submit">Reject</button>
                            </form>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="side-panel">
            <h2>Provenance Inspection Panel</h2>
            <p>Select a brand to view field provenance (source URL, fetch timestamp, method, confidence).</p>
            <ul>
                {% for fv in field_values %}
                <li>
                    <strong>{{ fv.field }}</strong>: {{ fv.value }}<br/>
                    <small>Source URL: <a href="{{ fv.source_url }}" target="_blank">{{ fv.source_url }}</a> | Method: {{ fv.method }}</small>
                </li>
                {% endfor %}
            </ul>
        </div>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index(db: Session = Depends(get_db)):
    from jinja2 import Template
    brands = db.query(BrandDB).all()
    items = []
    for b in brands:
        draft = db.query(DraftDB).filter_by(brand_id=b.id).first()
        items.append({"brand": b, "draft": draft})

    field_values = db.query(FieldValueDB).limit(20).all()
    template = Template(HTML_TEMPLATE)
    return template.render(items=items, field_values=field_values)

@app.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(DraftDB).get(draft_id)
    if draft:
        draft.status = "approved"
        db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(DraftDB).get(draft_id)
    if draft:
        draft.status = "rejected"
        db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/export/csv")
def export_csv(db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Brand Name", "Contact Email", "Subject", "Body", "Status", "Source URL"])

    approved_drafts = db.query(DraftDB).filter_by(status="approved").all()
    for d in approved_drafts:
        brand = db.query(BrandDB).get(d.brand_id)
        contact = db.query(ContactDB).get(d.contact_id) if d.contact_id else None
        writer.writerow([
            brand.name if brand else "",
            contact.value if contact else "",
            d.subject,
            d.body,
            d.status,
            contact.source_url if contact else ""
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=approved_leads.csv"}
    )
