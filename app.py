"""Dalma & David Financial Services — Flask Application."""

import csv
import io
import json
from datetime import date, datetime, timedelta

import bcrypt
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)

from config import Config
from models import db, User, Project, TimeEntry, Setting, AmebEntry, Invoice, InvoiceCounter

# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------

HOURS_025 = 2.0
HOURS_05 = 4.0


def round_quarter_day(total_hours: float) -> float:
    """Round generously to 0.25, 0.5 or 1.0 day."""
    if total_hours <= 0:
        return 0.0
    if total_hours <= HOURS_025:
        return 0.25
    if total_hours <= HOURS_05:
        return 0.5
    return 1.0


def parse_hours_input(raw: str) -> float:
    """Parse hours:minutes or decimal input into decimal hours."""
    raw = raw.strip()
    if ":" in raw:
        parts = raw.split(":")
        h = float(parts[0])
        m = float(parts[1]) if len(parts) > 1 else 0
        return h + m / 60
    if "h" in raw.lower():
        import re
        m = re.match(r"([\d.]+)\s*h\s*(?:(\d+)\s*m)?", raw, re.IGNORECASE)
        if m:
            h = float(m.group(1))
            mins = float(m.group(2)) if m.group(2) else 0
            return h + mins / 60
    return float(raw)


def round_ameb_minutes(hours_worked: float) -> float:
    """Round AMEB hours to quarter-hour based on minute thresholds.
    0-9 min → 0, 10-24 → 0.25, 25-39 → 0.50, 40-54 → 0.75, 55-60 → 1.00
    """
    total_minutes = hours_worked * 60
    whole_hours = int(total_minutes // 60)
    remainder_min = total_minutes % 60

    if remainder_min < 10:
        return whole_hours + 0.0
    elif remainder_min < 25:
        return whole_hours + 0.25
    elif remainder_min < 40:
        return whole_hours + 0.50
    elif remainder_min < 55:
        return whole_hours + 0.75
    else:
        return whole_hours + 1.0


def get_setting(key, default=""):
    """Fetch a setting value from the DB."""
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default


def financial_year(d=None):
    """Return the financial year code (e.g. 25 for FY 2025/2026)."""
    from datetime import date as dt_date
    d = d or dt_date.today()
    fy = d.year - 1 if d.month < 7 else d.year
    return fy % 100


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    @app.context_processor
    def inject_settings():
        """Make get_setting available in templates."""
        return dict(get_setting=get_setting)

    return app


# ---------------------------------------------------------------------------
app = create_app()

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def login_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Routes – Auth
# ---------------------------------------------------------------------------


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        user = User.query.first()
        if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            session["logged_in"] = True
            flash("Welcome back!", "success")
            return redirect(url_for("home"))
        flash("Invalid password", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes – Dashboard
# ---------------------------------------------------------------------------


@app.route("/")
@login_required
def home():
    return render_template("home.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for("track"))


@app.route("/dashboard")
@login_required
def dashboard_old():
    return redirect(url_for("track"))


@app.route("/dashboard-old")
@login_required
def dashboard_full():
    today = date.today()
    entries = (
        TimeEntry.query.filter(TimeEntry.date == today)
        .order_by(TimeEntry.start_time.desc())
        .all()
    )

    projects = Project.query.filter_by(active=True).order_by(Project.name).all()

    return render_template(
        "dashboard.html",
        entries=entries,
        today=today,
        projects=projects,
    )


@app.route("/dashboard/add", methods=["POST"])
@login_required
def dashboard_add_entry():
    project_id = request.form.get("project_id")
    description = request.form.get("description", "").strip()
    entry_date = request.form.get("date")
    start_str = request.form.get("start_time")
    end_str = request.form.get("end_time")

    project = Project.query.get(project_id)
    if not project:
        flash("Select a project", "warning")
        return redirect(url_for("dashboard"))

    try:
        date_obj = date.fromisoformat(entry_date) if entry_date else date.today()
        start_time = datetime.fromisoformat(f"{date_obj.isoformat()}T{start_str}") if start_str else datetime.now()
        end_time = datetime.fromisoformat(f"{date_obj.isoformat()}T{end_str}") if end_str else None
    except (ValueError, TypeError):
        flash("Invalid date or time format", "danger")
        return redirect(url_for("dashboard"))

    entry = TimeEntry(
        project_id=project.id,
        description=description,
        start_time=start_time,
        end_time=end_time,
        date=date_obj,
    )
    db.session.add(entry)
    db.session.commit()
    flash("Entry added", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Routes – Time Tracking
# ---------------------------------------------------------------------------


@app.route("/track")
@login_required
def track():
    projects = Project.query.filter_by(active=True).order_by(Project.name).all()
    running = TimeEntry.query.filter_by(end_time=None).first()
    selected_id = request.args.get("project", type=int)
    selected_project = Project.query.get(selected_id) if selected_id else None
    ameb_entries = AmebEntry.query.filter(
        AmebEntry.invoice_id.is_(None)
    ).order_by(AmebEntry.date.desc()).all()
    return render_template("track.html", projects=projects, running=running,
                           selected_project=selected_project, ameb_entries=ameb_entries)


@app.route("/track/start", methods=["POST"])
@login_required
def track_start():
    project_id = request.form.get("project_id")
    description = request.form.get("description", "").strip()

    # Ensure no other entry is running
    running = TimeEntry.query.filter_by(end_time=None).first()
    if running:
        flash("Stop the current entry before starting a new one.", "warning")
        return redirect(url_for("track"))

    project = Project.query.get(project_id)
    if not project:
        flash("Project not found", "danger")
        return redirect(url_for("track"))

    now = datetime.now()
    entry = TimeEntry(
        project_id=project.id,
        description=description,
        start_time=now,
        date=now.date(),
    )
    db.session.add(entry)
    db.session.commit()
    flash(f"Started tracking for {project.name}", "success")
    return redirect(url_for("track"))


@app.route("/track/stop", methods=["POST"])
@login_required
def track_stop():
    running = TimeEntry.query.filter_by(end_time=None).first()
    if not running:
        flash("No running entry to stop.", "warning")
        return redirect(url_for("track"))

    running.end_time = datetime.now()
    db.session.commit()
    hours = running.duration_hours
    flash(
        f"Stopped. Duration: {hours:.2f}h — "
        f"({round_quarter_day(hours)} day{'s' if round_quarter_day(hours) != 1 else ''})",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/track/edit/<int:entry_id>", methods=["GET", "POST"])
@login_required
def edit_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)

    if request.method == "POST":
        entry.project_id = request.form.get("project_id", entry.project_id)
        entry.description = request.form.get("description", "").strip()
        start_str = request.form.get("start_time")
        end_str = request.form.get("end_time")
        if start_str:
            entry.start_time = datetime.fromisoformat(start_str)
        if end_str:
            entry.end_time = datetime.fromisoformat(end_str)
            entry.date = entry.start_time.date()
        db.session.commit()
        flash("Entry updated", "success")
        return redirect(url_for("dashboard"))

    projects = Project.query.filter_by(active=True).order_by(Project.name).all()
    return render_template("edit_entry.html", entry=entry, projects=projects)


@app.route("/track/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash("Entry deleted", "info")
    return redirect(request.referrer or url_for("dashboard"))


# ---------------------------------------------------------------------------
# Routes – Projects
# ---------------------------------------------------------------------------


@app.route("/projects", methods=["GET", "POST"])
@login_required
def projects():
    pipeline_filter = request.args.get("pipeline")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        pipeline = request.form.get("pipeline", "ADB")
        if name:
            existing = Project.query.filter_by(name=name).first()
            if existing:
                flash("Project already exists", "warning")
            else:
                project = Project(name=name, pipeline=pipeline)
                db.session.add(project)
                db.session.commit()
                flash(f"Project '{name}' created ({pipeline})", "success")
        else:
            flash("Project name is required", "danger")
        return redirect(url_for("projects", pipeline=pipeline_filter))

    query = Project.query.order_by(Project.name)
    if pipeline_filter:
        query = query.filter_by(pipeline=pipeline_filter)
    projects_list = query.all()

    return render_template(
        "projects.html",
        projects=projects_list,
        current_pipeline=pipeline_filter or "",
    )


@app.route("/projects/edit/<int:project_id>", methods=["POST"])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    name = request.form.get("name", "").strip()
    if name:
        project.name = name
        db.session.commit()
        flash("Project updated", "success")
    return redirect(request.referrer or url_for("projects"))


@app.route("/projects/pipeline/<int:project_id>", methods=["POST"])
@login_required
def set_pipeline(project_id):
    project = Project.query.get_or_404(project_id)
    pipeline = request.form.get("pipeline", "ADB")
    if pipeline in ("ADB", "QBCC", "AMEB"):
        project.pipeline = pipeline
        db.session.commit()
        flash(f"Project moved to {pipeline}", "info")
    return redirect(request.referrer or url_for("projects"))


@app.route("/projects/toggle/<int:project_id>", methods=["POST"])
@login_required
def toggle_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.active = not project.active
    db.session.commit()
    status = "active" if project.active else "inactive"
    flash(f"Project set to {status}", "info")
    return redirect(request.referrer or url_for("projects"))


@app.route("/projects/billing/<int:project_id>", methods=["POST"])
@login_required
def set_billing(project_id):
    project = Project.query.get_or_404(project_id)
    billing = request.form.get("billing_type", "hourly")
    if billing in ("hourly", "flat"):
        project.billing_type = billing
        db.session.commit()
        flash(f"Billing set to {billing}", "info")
    return redirect(request.referrer or url_for("projects"))


@app.route("/projects/flat-amount/<int:project_id>", methods=["POST"])
@login_required
def set_flat_amount(project_id):
    project = Project.query.get_or_404(project_id)
    try:
        amount = float(request.form.get("flat_amount", 0))
        if amount >= 0:
            project.flat_amount = amount
            db.session.commit()
            flash(f"Flat amount set to ${amount:.2f}", "info")
    except (ValueError, TypeError):
        flash("Invalid amount", "danger")
    return redirect(request.referrer or url_for("projects"))


# ---------------------------------------------------------------------------
# Routes – History
# ---------------------------------------------------------------------------


@app.route("/history")
@login_required
def history():
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    try:
        start = date.fromisoformat(start_str) if start_str else date.today() - timedelta(days=30)
    except (ValueError, TypeError):
        start = date.today() - timedelta(days=30)

    try:
        end = date.fromisoformat(end_str) if end_str else date.today()
    except (ValueError, TypeError):
        end = date.today()

    entries = (
        TimeEntry.query.filter(TimeEntry.date >= start, TimeEntry.date <= end)
        .order_by(TimeEntry.date.desc(), TimeEntry.start_time.desc())
        .all()
    )

    # Group by date for daily summaries
    from collections import defaultdict

    by_date = defaultdict(list)
    for e in entries:
        by_date[e.date].append(e)

    daily_summaries = []
    for d, day_entries in sorted(by_date.items(), reverse=True):
        day_hours = sum(e.duration_hours for e in day_entries if e.end_time)
        daily_summaries.append(
            {
                "date": d,
                "entries": day_entries,
                "total_hours": round(day_hours, 2),
                "rounded_days": round_quarter_day(day_hours),
            }
        )

    return render_template(
        "history.html",
        daily_summaries=daily_summaries,
        start=start,
        end=end,
    )


# ---------------------------------------------------------------------------
# Routes – Export
# ---------------------------------------------------------------------------


@app.route("/export/csv")
@login_required
def export_csv():
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    try:
        start = date.fromisoformat(start_str) if start_str else date.today() - timedelta(days=365)
    except (ValueError, TypeError):
        start = date.today() - timedelta(days=365)

    try:
        end = date.fromisoformat(end_str) if end_str else date.today()
    except (ValueError, TypeError):
        end = date.today()

    entries = (
        TimeEntry.query.filter(TimeEntry.date >= start, TimeEntry.date <= end)
        .order_by(TimeEntry.date, TimeEntry.start_time)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Project", "Description", "Start", "End", "Hours", "Rounded Days"])

    for e in entries:
        if e.end_time:
            rounded = round_quarter_day(e.duration_hours)
            writer.writerow(
                [
                    e.date.isoformat(),
                    e.project.name,
                    e.description,
                    e.start_time.isoformat(),
                    e.end_time.isoformat(),
                    e.duration_hours,
                    rounded,
                ]
            )

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=hours.csv"},
    )


@app.route("/export/json")
@login_required
def export_json():
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    try:
        start = date.fromisoformat(start_str) if start_str else date.today() - timedelta(days=365)
    except (ValueError, TypeError):
        start = date.today() - timedelta(days=365)

    try:
        end = date.fromisoformat(end_str) if end_str else date.today()
    except (ValueError, TypeError):
        end = date.today()

    entries = (
        TimeEntry.query.filter(TimeEntry.date >= start, TimeEntry.date <= end)
        .order_by(TimeEntry.date, TimeEntry.start_time)
        .all()
    )

    data = []
    for e in entries:
        if e.end_time:
            rounded = round_quarter_day(e.duration_hours)
            data.append(
                {
                    "date": e.date.isoformat(),
                    "project": e.project.name,
                    "description": e.description,
                    "start_time": e.start_time.isoformat(),
                    "end_time": e.end_time.isoformat(),
                    "hours": e.duration_hours,
                    "rounded_days": rounded,
                }
            )

    return Response(
        json.dumps(data, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=hours.json"},
    )


# ---------------------------------------------------------------------------
# Routes – Invoice
# ---------------------------------------------------------------------------


@app.route("/invoice")
@login_required
def invoice():
    from collections import defaultdict

    project_id = request.args.get("project_id", type=int)
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    try:
        start = date.fromisoformat(start_str) if start_str else date.today() - timedelta(days=30)
    except (ValueError, TypeError):
        start = date.today() - timedelta(days=30)

    try:
        end = date.fromisoformat(end_str) if end_str else date.today()
    except (ValueError, TypeError):
        end = date.today()

    projects = Project.query.order_by(Project.name).all()
    selected_project = Project.query.get(project_id) if project_id else None

    daily_summaries = []
    grand_total_days = 0.0

    if selected_project:
        entries = (
            TimeEntry.query.filter(
                TimeEntry.project_id == selected_project.id,
                TimeEntry.date >= start,
                TimeEntry.date <= end,
                TimeEntry.end_time.isnot(None),
            )
            .order_by(TimeEntry.date, TimeEntry.start_time)
            .all()
        )

        by_date = defaultdict(list)
        for e in entries:
            by_date[e.date].append(e)

        for d, day_entries in sorted(by_date.items()):
            day_hours = sum(e.duration_hours for e in day_entries)
            day_rounded = round_quarter_day(day_hours)
            grand_total_days += day_rounded
            daily_summaries.append(
                {
                    "date": d,
                    "entries": day_entries,
                    "total_hours": round(day_hours, 2),
                    "rounded_days": day_rounded,
                }
            )

    return render_template(
        "invoice.html",
        projects=projects,
        selected_project=selected_project,
        daily_summaries=daily_summaries,
        grand_total_days=grand_total_days,
        start=start,
        end=end,
    )


# ---------------------------------------------------------------------------
# Routes – Unified Outputs
# ---------------------------------------------------------------------------


@app.route("/outputs", methods=["GET", "POST"])
@login_required
def outputs():
    if request.method == "POST":
        project_id = request.form.get("project_id")
        project = Project.query.get(project_id)
        if not project:
            flash("Select a project", "warning")
            return redirect(url_for("outputs"))
        if project.pipeline == "ADB":
            return redirect(
                url_for("adb_report", project_id=project_id,
                        start=request.form.get("start"),
                        end=request.form.get("end"))
            )
        elif project.pipeline == "AMEB":
            return redirect(
                url_for("ameb_invoice", project_id=project_id)
            )
        else:
            return redirect(
                url_for("qbcc_invoice", project_id=project_id,
                        start=request.form.get("start"),
                        end=request.form.get("end"))
            )

    projects = Project.query.filter_by(active=True).order_by(Project.name).all()
    return render_template("outputs.html", projects=projects)


# ---------------------------------------------------------------------------
# Routes – QBCC Hourly Invoice
# ---------------------------------------------------------------------------


@app.route("/qbcc-invoice")
@login_required
def qbcc_invoice():
    project_id = request.args.get("project_id", type=int)
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    try:
        start = date.fromisoformat(start_str) if start_str else date.today() - timedelta(days=30)
    except (ValueError, TypeError):
        start = date.today() - timedelta(days=30)

    try:
        end = date.fromisoformat(end_str) if end_str else date.today()
    except (ValueError, TypeError):
        end = date.today()

    projects = (
        Project.query.filter_by(pipeline="QBCC", active=True)
        .order_by(Project.name)
        .all()
    )
    selected_project = Project.query.get(project_id) if project_id else None

    entries = []
    total_hours = 0.0

    if selected_project:
        entries = (
            TimeEntry.query.filter(
                TimeEntry.project_id == selected_project.id,
                TimeEntry.date >= start,
                TimeEntry.date <= end,
                TimeEntry.end_time.isnot(None),
            )
            .order_by(TimeEntry.date, TimeEntry.start_time)
            .all()
        )
        total_hours = round(sum(e.duration_hours for e in entries), 6)

    return render_template(
        "qbcc_invoice.html",
        projects=projects,
        selected_project=selected_project,
        entries=entries,
        total_hours=total_hours,
        billing_type=selected_project.billing_type if selected_project else "hourly",
        flat_amount=selected_project.flat_amount if selected_project else None,
        hourly_rate=350,
        start=start,
        end=end,
    )


# ---------------------------------------------------------------------------
# Routes – ADB Rolling Accrual Report
# ---------------------------------------------------------------------------


@app.route("/adb-report")
@login_required
def adb_report():
    project_id = request.args.get("project_id", type=int)
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    try:
        start = date.fromisoformat(start_str) if start_str else date.today() - timedelta(days=90)
    except (ValueError, TypeError):
        start = date.today() - timedelta(days=90)

    try:
        end = date.fromisoformat(end_str) if end_str else date.today()
    except (ValueError, TypeError):
        end = date.today()

    projects = (
        Project.query.filter_by(pipeline="ADB", active=True)
        .order_by(Project.name)
        .all()
    )
    selected_project = Project.query.get(project_id) if project_id else None

    rows = []
    carry_forward = 0.0
    grand_total_days = 0.0

    if selected_project:
        entries = (
            TimeEntry.query.filter(
                TimeEntry.project_id == selected_project.id,
                TimeEntry.date >= start,
                TimeEntry.date <= end,
                TimeEntry.end_time.isnot(None),
            )
            .order_by(TimeEntry.date, TimeEntry.start_time)
            .all()
        )

        running_total = 0.0

        for entry in entries:
            hours = entry.duration_hours
            new_total = running_total + hours
            days_billed = 0.0

            # Check thresholds high-to-low: 8h → 1.0, 4h → 0.5, 2h → 0.25
            while new_total >= 8.0:
                days_billed += 1.0
                new_total -= 8.0
            while new_total >= 4.0:
                days_billed += 0.5
                new_total -= 4.0
            while new_total >= 2.0:
                days_billed += 0.25
                new_total -= 2.0

            rows.append(
                {
                    "entry": entry,
                    "hours": hours,
                    "running_before": round(running_total, 2),
                    "running_after": round(new_total, 2),
                    "days_billed": days_billed,
                    "is_billable": days_billed > 0,
                }
            )

            running_total = new_total
            grand_total_days += days_billed

        carry_forward = round(running_total, 2)

    return render_template(
        "adb_report.html",
        projects=projects,
        selected_project=selected_project,
        rows=rows,
        carry_forward=carry_forward,
        grand_total_days=grand_total_days,
        start=start,
        end=end,
    )


# ---------------------------------------------------------------------------
# Routes – AMEB Invoice (manual entry)
# ---------------------------------------------------------------------------


@app.route("/ameb-invoice", methods=["GET", "POST"])
@login_required
def ameb_invoice():
    project_id = request.args.get("project_id", type=int)
    selected_project = Project.query.get(project_id) if project_id else None
    projects = (
        Project.query.filter_by(pipeline="AMEB", active=True)
        .order_by(Project.name)
        .all()
    )

    if request.method == "POST" and selected_project:
        # Collect un-invoiced entries for this project
        entries = AmebEntry.query.filter(
            AmebEntry.project_id == selected_project.id,
            AmebEntry.invoice_id.is_(None),
        ).order_by(AmebEntry.date).all()

        if not entries:
            flash("No un-invoiced timetable entries. Add new entries on Track/Input first, then generate the invoice.", "warning")
            return redirect(url_for("ameb_invoice", project_id=project_id))

        rate = float(get_setting("ameb_rate", "91"))
        total_rounded = sum(e.hours_rounded for e in entries)
        total_cost = total_rounded * rate

        # Generate invoice number
        fy = financial_year()
        # Reset counter if the FY changed
        counter_str = get_setting(f"invoice_fy_{fy}", "")
        next_num = int(counter_str) if counter_str else 1
        invoice_number = f"{fy}{next_num:02d}"
        # Save counter
        s = Setting.query.filter_by(key=f"invoice_fy_{fy}").first()
        if s:
            s.value = str(next_num + 1)
        else:
            db.session.add(Setting(key=f"invoice_fy_{fy}", value=str(next_num + 1)))

        inv = Invoice(
            invoice_number=invoice_number,
            project_id=selected_project.id,
            issue_date=date.today(),
            client_name=get_setting("ameb_client", ""),
            total=total_cost,
        )
        db.session.add(inv)
        db.session.flush()

        # Link entries to invoice
        for e in entries:
            e.invoice_id = inv.id

        db.session.commit()

        return redirect(url_for("view_invoice", invoice_id=inv.id))

    return render_template("ameb_invoice.html", projects=projects, selected_project=selected_project)


# ---------------------------------------------------------------------------
# Routes – View Invoice
# ---------------------------------------------------------------------------


@app.route("/invoice/<int:invoice_id>")
@login_required
def view_invoice(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    proj = inv.project
    rate_key = f"{proj.pipeline.lower()}_rate"

    rate = float(get_setting(rate_key, "0"))
    abn = get_setting(f"{proj.pipeline.lower()}_abn", "")
    phone = get_setting(f"{proj.pipeline.lower()}_phone", "")
    address = get_setting(f"{proj.pipeline.lower()}_address", "")
    payment_bsb = get_setting("payment_bsb", "063 097")
    payment_account = get_setting("payment_account", "")
    payment_name = get_setting("payment_name", "")
    terms = get_setting("payment_terms", "Payment due within 30 days.")
    gst_note = get_setting("gst_note", "")

    if proj.pipeline == "AMEB":
        entries = AmebEntry.query.filter_by(invoice_id=inv.id).order_by(AmebEntry.date).all()
        return render_template("invoice_ameb.html",
            invoice=inv, project=proj, entries=entries,
            rate=rate, abn=abn, phone=phone, address=address,
            payment_bsb=payment_bsb, payment_account=payment_account,
            payment_name=payment_name, terms=terms, gst_note=gst_note,
        )

    # QBCC/ADB — show time entries
    from collections import defaultdict
    time_entries = TimeEntry.query.filter(
        TimeEntry.project_id == proj.id,
        TimeEntry.end_time.isnot(None),
    ).order_by(TimeEntry.date).all()
    return render_template("invoice_generic.html",
        invoice=inv, project=proj, entries=time_entries,
        rate=rate, abn=abn, phone=phone, address=address,
        payment_bsb=payment_bsb, payment_account=payment_account,
        payment_name=payment_name, terms=terms, gst_note=gst_note,
    )


# ---------------------------------------------------------------------------
# Routes – AMEB entry management (in Settings)
# ---------------------------------------------------------------------------


@app.route("/ameb-entry/add", methods=["POST"])
@login_required
def ameb_add_entry():
    entry_date = request.form.get("entry_date")
    timetable = request.form.get("entry_timetable", "").strip()
    hours_str = request.form.get("entry_hours", "0")
    project_id = request.form.get("project_id") or request.args.get("project_id")

    if not project_id:
        proj = Project.query.filter_by(pipeline="AMEB", active=True).first()
        if proj:
            project_id = proj.id
        else:
            flash("Create an AMEB project first", "warning")
            return redirect(url_for("track"))

    try:
        hours_val = parse_hours_input(hours_str)
        rounded = round_ameb_minutes(hours_val)
        entry = AmebEntry(
            date=date.fromisoformat(entry_date) if entry_date else date.today(),
            timetable=timetable,
            hours_worked=hours_val,
            hours_rounded=rounded,
            project_id=int(project_id),
        )
        db.session.add(entry)
        db.session.commit()
        flash(f"Added {timetable}: {hours_val}h → {rounded:.2f}h rounded", "success")
    except (ValueError, TypeError):
        flash("Invalid hours value", "danger")

    return redirect(url_for("track", project=project_id))


@app.route("/ameb-entry/delete/<int:entry_id>", methods=["POST"])
@login_required
def ameb_delete_entry(entry_id):
    entry = AmebEntry.query.get_or_404(entry_id)
    if entry.invoice_id:
        flash("Cannot delete — already invoiced", "danger")
    else:
        db.session.delete(entry)
        db.session.commit()
        flash("Entry deleted", "info")
    return redirect(url_for("track"))


# ---------------------------------------------------------------------------
# Routes – Settings
# ---------------------------------------------------------------------------


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        # Save rate/payment settings
        rate_keys = [
            "adb_rate", "qbcc_rate", "ameb_rate",
            "adb_abn", "qbcc_abn", "ameb_abn",
            "adb_phone", "qbcc_phone", "ameb_phone",
            "adb_address", "qbcc_address", "ameb_address",
            "payment_bsb", "payment_account", "payment_name",
            "payment_terms", "gst_note", "ameb_client", "ameb_send_to",
        ]
        for key in rate_keys:
            val = request.form.get(key, "")
            s = Setting.query.filter_by(key=key).first()
            if s:
                s.value = val
            else:
                db.session.add(Setting(key=key, value=val))
        db.session.commit()
        flash("Settings saved", "success")

        # Password change
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        user = User.query.first()
        if not bcrypt.checkpw(current.encode(), user.password_hash.encode()):
            flash("Current password is incorrect", "danger")
        elif len(new_password) < 4:
            flash("New password must be at least 4 characters", "danger")
        elif new_password != confirm:
            flash("Passwords do not match", "danger")
        else:
            user.password_hash = bcrypt.hashpw(
                new_password.encode(), bcrypt.gensalt()
            ).decode()
            db.session.commit()
            flash("Password changed successfully", "success")
            return redirect(url_for("dashboard"))

    # Load all settings for the template
    all_settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("settings.html", settings=all_settings)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config.get("PORT", 7246))
