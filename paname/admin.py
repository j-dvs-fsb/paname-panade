"""Back-office : gestion des expositions et des musées (réservé aux admins)."""
from functools import wraps

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort
)
from flask_login import login_required, current_user
from slugify import slugify

from .extensions import db
from .models import (
    Museum, Exposition, PRICE_LABELS, RESERVATION_LABELS, FREE_ACCESS_LABELS,
)
from .utils import html_to_text, next_local_museum_id

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _unique_slug(model, base, current_id=None):
    base = slugify(base)[:200] or model.__name__.lower()
    slug, n = base, 2
    while True:
        q = model.query.filter(model.slug == slug)
        if current_id is not None:
            q = q.filter(model.id != current_id)
        if not q.first():
            return slug
        slug, n = f"{base}-{n}", n + 1


def _parse_date(value):
    from datetime import datetime
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- Dashboard
@admin_bp.route("/")
@admin_required
def dashboard():
    stats = {
        "expos": Exposition.query.count(),
        "expos_draft": Exposition.query.filter_by(status="draft").count(),
        "museums": Museum.query.count(),
    }
    drafts = (Exposition.query.filter_by(status="draft")
              .order_by(Exposition.id.desc()).limit(10).all())
    return render_template("admin/dashboard.html", stats=stats, drafts=drafts)


# ---------------------------------------------------------------- Expositions
@admin_bp.route("/expositions")
@admin_required
def expos():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    query = Exposition.query
    if q:
        query = query.filter(Exposition.title.ilike(f"%{q}%"))
    if status in ("draft", "published"):
        query = query.filter_by(status=status)
    items = query.order_by(Exposition.id.desc()).all()
    return render_template("admin/expos.html", expos=items, q=q, status=status)


@admin_bp.route("/expositions/nouvelle", methods=["GET", "POST"])
@admin_bp.route("/expositions/<int:expo_id>/edit", methods=["GET", "POST"])
@admin_required
def expo_form(expo_id=None):
    expo = db.session.get(Exposition, expo_id) if expo_id else None
    if expo_id and not expo:
        abort(404)

    if request.method == "POST":
        f = request.form
        title = (f.get("title") or "").strip()
        if not title:
            flash("Le titre est obligatoire.", "danger")
            return render_template("admin/expo_form.html", expo=expo,
                                   museums=Museum.query.order_by(Museum.name).all(),
                                   price_labels=PRICE_LABELS,
                                   reservation_labels=RESERVATION_LABELS)
        if not expo:
            # slug calculé avant l'ajout en session (évite un autoflush prématuré)
            expo = Exposition(source="manuel", slug=_unique_slug(Exposition, title))
            db.session.add(expo)
        expo.title = title
        expo.description = html_to_text(f.get("description"))
        expo.date_start = _parse_date(f.get("date_start"))
        expo.date_end = _parse_date(f.get("date_end"))
        expo.schedule = (f.get("schedule") or "").strip() or None
        expo.url = (f.get("url") or "").strip() or None
        expo.image_url = (f.get("image_url") or "").strip() or None
        expo.venue_name = (f.get("venue_name") or "").strip() or None
        expo.address = (f.get("address") or "").strip() or None
        expo.postal_code = (f.get("postal_code") or "").strip() or None
        expo.lat = _float(f.get("lat"))
        expo.lon = _float(f.get("lon"))
        expo.price_category = f.get("price_category") or "gratuit_tous"
        expo.reservation = f.get("reservation") or "non_necessaire"
        expo.reservation_url = (f.get("reservation_url") or "").strip() or None
        expo.museum_id = int(f["museum_id"]) if f.get("museum_id") else None
        expo.status = "published" if f.get("status") == "published" else "draft"
        db.session.commit()
        flash("Exposition enregistrée.", "success")
        return redirect(url_for("admin.expos"))

    return render_template("admin/expo_form.html", expo=expo,
                           museums=Museum.query.order_by(Museum.name).all(),
                           price_labels=PRICE_LABELS,
                           reservation_labels=RESERVATION_LABELS)


@admin_bp.route("/expositions/<int:expo_id>/statut", methods=["POST"])
@admin_required
def expo_toggle_status(expo_id):
    expo = db.session.get(Exposition, expo_id) or abort(404)
    expo.status = "draft" if expo.status == "published" else "published"
    db.session.commit()
    flash(f"Statut : {expo.status}.", "info")
    return redirect(request.referrer or url_for("admin.expos"))


@admin_bp.route("/expositions/<int:expo_id>/supprimer", methods=["POST"])
@admin_required
def expo_delete(expo_id):
    expo = db.session.get(Exposition, expo_id) or abort(404)
    db.session.delete(expo)
    db.session.commit()
    flash("Exposition supprimée.", "info")
    return redirect(url_for("admin.expos"))


# ---------------------------------------------------------------- Musées
@admin_bp.route("/musees")
@admin_required
def museums():
    items = Museum.query.order_by(Museum.name).all()
    return render_template("admin/museums.html", museums=items)


@admin_bp.route("/musees/nouveau", methods=["GET", "POST"])
@admin_bp.route("/musees/<int:museum_id>/edit", methods=["GET", "POST"])
@admin_required
def museum_form(museum_id=None):
    museum = db.session.get(Museum, museum_id) if museum_id else None
    if museum_id and not museum:
        abort(404)

    if request.method == "POST":
        f = request.form
        name = (f.get("name") or "").strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
            return render_template("admin/museum_form.html", museum=museum,
                                   free_access_labels=FREE_ACCESS_LABELS)
        if not museum:
            # slug + ID local calculés avant l'ajout (évite un autoflush prématuré).
            # ID local : pattern distinct des museofile « M#### ».
            slug = _unique_slug(Museum, name)
            existing = [m.museofile_id for m in Museum.query.all()]
            museum = Museum(slug=slug, name=name,
                            museofile_id=next_local_museum_id(existing))
            db.session.add(museum)
        museum.name = name
        museum.description = (f.get("description") or "").strip() or None
        museum.address = (f.get("address") or "").strip() or None
        museum.arrondissement = (f.get("arrondissement") or "").strip() or None
        museum.website = (f.get("website") or "").strip() or None
        museum.expos_url = (f.get("expos_url") or "").strip() or None
        museum.logo_url = (f.get("logo_url") or "").strip() or None
        valid = set(FREE_ACCESS_LABELS)
        museum.free_access = ",".join(k for k in f.getlist("free_access") if k in valid)
        museum.lat = _float(f.get("lat"))
        museum.lon = _float(f.get("lon"))
        db.session.commit()
        flash("Musée enregistré.", "success")
        return redirect(url_for("admin.museums"))

    return render_template("admin/museum_form.html", museum=museum,
                           free_access_labels=FREE_ACCESS_LABELS)


@admin_bp.route("/musees/<int:museum_id>/supprimer", methods=["POST"])
@admin_required
def museum_delete(museum_id):
    museum = db.session.get(Museum, museum_id) or abort(404)
    db.session.delete(museum)
    db.session.commit()
    flash("Musée supprimé (et ses expositions rattachées).", "info")
    return redirect(url_for("admin.museums"))


# ---------------------------------------------------------------- Sync QFAP
@admin_bp.route("/sync-qfap", methods=["POST"])
@admin_required
def sync_qfap():
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    try:
        from scripts.sync_data import fetch, parse_date, map_reservation, clean_link, match_museum
    except Exception as e:  # pragma: no cover
        flash(f"Sync indisponible : {e}", "danger")
        return redirect(url_for("admin.dashboard"))
    try:
        records = fetch(200)
    except Exception as e:
        flash(f"Erreur réseau : {e}", "danger")
        return redirect(url_for("admin.dashboard"))

    created = updated = 0
    for rec in records:
        ext_id = str(rec.get("id") or rec.get("recordid") or "")
        title = rec.get("title")
        if not title:
            continue
        expo = Exposition.query.filter_by(external_id=ext_id).first() if ext_id else None
        if not expo:
            expo = Exposition(slug=_unique_slug(Exposition, title), external_id=ext_id,
                              source="que-faire-a-paris", status="published")
            db.session.add(expo)
            created += 1
        else:
            updated += 1
        expo.title = title
        expo.description = (html_to_text(rec.get("description"))
                            or html_to_text(rec.get("lead_text")) or "")
        expo.date_start = parse_date(rec.get("date_start"))
        expo.date_end = parse_date(rec.get("date_end"))
        expo.schedule = html_to_text(rec.get("date_description"))
        expo.url = rec.get("url")
        expo.image_url = rec.get("cover_url")
        expo.price_type = "gratuit"
        expo.price_category = "gratuit_tous"
        expo.venue_name = rec.get("address_name")
        expo.address = rec.get("address_street")
        expo.postal_code = rec.get("address_zipcode")
        geo = rec.get("lat_lon") or {}
        expo.lat = geo.get("lat")
        expo.lon = geo.get("lon")
        expo.reservation = map_reservation(rec.get("access_type"))
        expo.reservation_url = clean_link(rec.get("access_link"))
        m = match_museum(rec)
        if m:
            expo.museum_id = m.id
    db.session.commit()
    flash(f"Sync QFAP : {created} créées, {updated} mises à jour.", "success")
    return redirect(url_for("admin.dashboard"))
