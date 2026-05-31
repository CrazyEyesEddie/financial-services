from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    password_hash = db.Column(db.String(128), nullable=False)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    pipeline = db.Column(db.String(20), nullable=False, default="ADB")
    billing_type = db.Column(db.String(10), nullable=False, default="hourly")
    flat_amount = db.Column(db.Float, nullable=True)
    active = db.Column(db.Boolean, default=True)

    entries = db.relationship("TimeEntry", backref="project", lazy=True)

    def __repr__(self):
        return f"{self.name} ({self.pipeline})"


class TimeEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    description = db.Column(db.Text, default="")
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    date = db.Column(db.Date, nullable=False)

    @property
    def duration_hours(self):
        if not self.end_time:
            return 0.0
        delta = self.end_time - self.start_time
        return round(delta.total_seconds() / 3600, 2)

    @property
    def is_running(self):
        return self.end_time is None


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), default="")


class InvoiceCounter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    next_number = db.Column(db.Integer, nullable=False, default=1)


class AmebEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    timetable = db.Column(db.String(50), nullable=False)
    hours_worked = db.Column(db.Float, nullable=False)
    hours_rounded = db.Column(db.Float, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship("Project", backref="ameb_entries", lazy=True)


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), unique=True, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    client_name = db.Column(db.String(200), default="")
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(10), default="DUE")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship("Project", backref="invoices", lazy=True)
    ameb_entries = db.relationship("AmebEntry", backref="invoice", lazy=True)
