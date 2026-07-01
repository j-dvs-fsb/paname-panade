"""Calculs de statistiques et de progression pour le profil utilisateur."""
from datetime import date

from .extensions import db
from .models import Exposition, Visit


def total_expos():
    return Exposition.query.count()


def user_done_count(user):
    return Visit.query.filter_by(user_id=user.id).count()


def progress(user):
    total = total_expos()
    done = user_done_count(user)
    pct = round(done / total * 100) if total else 0
    return {"total": total, "done": done, "remaining": max(total - done, 0), "pct": pct}


def fun_stats(user):
    """Statistiques 'fun' à afficher sur le profil."""
    today = date.today()
    days_left = user.days_until_26
    p = progress(user)
    remaining = p["remaining"]

    stats = {
        "days_until_26": days_left,
        "is_over_26": days_left < 0,
        "weeks_until_26": max(days_left // 7, 0),
        "expos_per_week": None,
        "expos_per_month": None,
    }

    weeks = days_left / 7 if days_left > 0 else 0
    if weeks > 0 and remaining > 0:
        stats["expos_per_week"] = round(remaining / weeks, 1)
        stats["expos_per_month"] = round(remaining / (days_left / 30), 1)

    return stats
