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
