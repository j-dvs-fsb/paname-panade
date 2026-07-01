from datetime import datetime, date

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
)
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.sql.expression import func

from .extensions import db
from .models import Museum, Exposition, Favorite, Visit
from . import stats as stats_mod

main_bp = Blueprint("main", __name__)


def _user_expo_state(expo):
    """Renvoie (is_favorite, visit) pour l'utilisateur courant."""
    if not current_user.is_authenticated:
        return False, None
    fav = Favorite.query.filter_by(user_id=current_user.id, exposition_id=expo.id).first()
    visit = Visit.query.filter_by(user_id=current_user.id, exposition_id=expo.id).first()
    return fav is not None, visit


def _published():
    return Exposition.query.filter_by(status="published")


def _current():
    """Expositions publiées et non passées (date de fin absente ou ≥ aujourd'hui)."""
    today = date.today()
    return _published().filter(
        or_(Exposition.date_end.is_(None), Exposition.date_end >= today)
    )


@main_bp.route("/")
def index():
    total_expos = _current().count()
    total_museums = Museum.query.count()
    latest = _current().order_by(Exposition.id.desc()).limit(6).all()
    return render_template(
        "index.html",
        total_expos=total_expos,
        total_museums=total_museums,
        latest=latest,
    )


@main_bp.route("/musees")
def museums():
    items = Museum.query.order_by(Museum.name).all()
    return render_template("museums.html", museums=items)


@main_bp.route("/musee/<slug>")
def museum_detail(slug):
    museum = Museum.query.filter_by(slug=slug).first_or_404()
    return render_template("museum_detail.html", museum=museum)


def _geo_museums():
    """Musées géolocalisés, avec leur nombre d'expos courantes (en mémoire)."""
    museums = (
        Museum.query.filter(Museum.lat.isnot(None), Museum.lon.isnot(None))
        .order_by(Museum.name)
        .all()
    )
    # Compte des expos courantes par musée en une passe (≈50 musées, trivial).
    counts = {}
    for expo in _current().all():
        if expo.museum_id is not None:
            counts[expo.museum_id] = counts.get(expo.museum_id, 0) + 1
    return museums, counts


@main_bp.route("/radar")
def radar():
    museums, _ = _geo_museums()
    # Liste triée des arrondissements + centroïde (moyenne des coords) de chacun.
    groups = {}
    for m in museums:
        if m.arrondissement:
            groups.setdefault(m.arrondissement, []).append(m)
    centroids = {
        arr: {
            "lat": sum(x.lat for x in ms) / len(ms),
            "lon": sum(x.lon for x in ms) / len(ms),
        }
        for arr, ms in groups.items()
    }
    arrondissements = sorted(groups, key=_arr_sort_key)
    return render_template(
        "radar.html", arrondissements=arrondissements, centroids=centroids
    )


def _arr_sort_key(arr):
    """Trie « Paris 1er », « Paris 3e », … numériquement (le reste après)."""
    import re
    m = re.search(r"(\d+)", arr or "")
    return (0, int(m.group(1))) if m else (1, arr or "")


@main_bp.route("/api/museums.json")
def api_museums():
    museums, counts = _geo_museums()
    return jsonify([
        {
            "id": m.id,
            "name": m.name,
            "slug": m.slug,
            "arrondissement": m.arrondissement,
            "lat": m.lat,
            "lon": m.lon,
            "expo_count": counts.get(m.id, 0),
            "url": url_for("main.museum_detail", slug=m.slug),
        }
        for m in museums
    ])


# Tuiles de filtres. Prix -> filtre sur price_category. Flags (nocturne, dimanche,
# climatisé) -> pas encore de données : tuiles toggleables, application à brancher.
PRICE_TILES = [
    ("gratuit_tous", "Gratuit pour tous"),
    ("gratuit_26", "Gratuit -26 ans"),
    ("reduit_26", "Tarif réduit -26 ans"),
]
FLAG_TILES = [
    ("nocturne", "Nocturne"),
    ("dimanche", "Ouvert le dimanche"),
    ("climatise", "Climatisé"),
]


def _toggle_args(key, value):
    """Renvoie les args courants avec `value` ajouté/retiré de `key` (toggle)."""
    d = request.args.to_dict(flat=False)
    cur = [v for v in d.get(key, []) if v]
    if value in cur:
        cur.remove(value)
    else:
        cur.append(value)
    if cur:
        d[key] = cur
    else:
        d.pop(key, None)
    return d


def _build_tiles(definitions, key, active):
    return [
        {"label": label, "active": val in active,
         "href": url_for("main.expos", **_toggle_args(key, val))}
        for val, label in definitions
    ]


@main_bp.route("/expositions")
def expos():
    q = request.args.get("q", "").strip()
    active_prix = request.args.getlist("prix")
    active_flags = request.args.getlist("f")

    query = _current()
    if q:
        query = query.filter(Exposition.title.ilike(f"%{q}%"))
    valid_prix = [p for p in active_prix if p in dict(PRICE_TILES)]
    if valid_prix:
        query = query.filter(Exposition.price_category.in_(valid_prix))
    # nocturne / dimanche / climatisé : filtrage non encore appliqué (pas de données).
    items = query.order_by(Exposition.title).all()

    return render_template(
        "expos.html", expos=items, q=q,
        price_tiles=_build_tiles(PRICE_TILES, "prix", active_prix),
        flag_tiles=_build_tiles(FLAG_TILES, "f", active_flags),
        active_prix=active_prix, active_flags=active_flags,
    )


@main_bp.route("/exposition/<slug>")
def expo_detail(slug):
    expo = Exposition.query.filter_by(slug=slug).first_or_404()
    if expo.status != "published" and not (current_user.is_authenticated and current_user.is_admin):
        abort(404)
    is_fav, visit = _user_expo_state(expo)
    reviews = [v for v in expo.visits if v.rating or v.comment]
    reviews.sort(key=lambda v: v.visited_at or datetime.min, reverse=True)
    return render_template(
        "expo_detail.html", expo=expo, is_fav=is_fav, visit=visit, reviews=reviews
    )


@main_bp.route("/exposition/<int:expo_id>/favori", methods=["POST"])
@login_required
def toggle_favorite(expo_id):
    expo = db.session.get(Exposition, expo_id) or abort(404)
    fav = Favorite.query.filter_by(user_id=current_user.id, exposition_id=expo.id).first()
    if fav:
        db.session.delete(fav)
        flash("Retiré des favoris.", "info")
    else:
        db.session.add(Favorite(user_id=current_user.id, exposition_id=expo.id))
        flash("Ajouté aux favoris ⭐", "success")
    db.session.commit()
    return redirect(request.referrer or url_for("main.expo_detail", slug=expo.slug))


@main_bp.route("/exposition/<int:expo_id>/fait", methods=["POST"])
@login_required
def mark_done(expo_id):
    expo = db.session.get(Exposition, expo_id) or abort(404)
    rating = request.form.get("rating", type=int)
    comment = (request.form.get("comment") or "").strip()

    visit = Visit.query.filter_by(user_id=current_user.id, exposition_id=expo.id).first()
    if not visit:
        visit = Visit(user_id=current_user.id, exposition_id=expo.id)
        db.session.add(visit)
    if rating and 1 <= rating <= 5:
        visit.rating = rating
    visit.comment = comment or visit.comment
    db.session.commit()
    flash("Expo marquée comme faite ! 🎉", "success")
    return redirect(request.referrer or url_for("main.expo_detail", slug=expo.slug))


@main_bp.route("/exposition/<int:expo_id>/annuler-fait", methods=["POST"])
@login_required
def unmark_done(expo_id):
    visit = Visit.query.filter_by(user_id=current_user.id, exposition_id=expo_id).first()
    if visit:
        db.session.delete(visit)
        db.session.commit()
        flash("Visite annulée.", "info")
    return redirect(request.referrer or url_for("main.profile"))


@main_bp.route("/au-hasard")
def random_expo():
    expo = _current().order_by(func.random()).first()
    if not expo:
        flash("Aucune exposition en base pour le moment.", "info")
        return redirect(url_for("main.index"))
    return redirect(url_for("main.expo_detail", slug=expo.slug))


@main_bp.route("/profil")
@login_required
def profile():
    prog = stats_mod.progress(current_user)
    fun = stats_mod.fun_stats(current_user)

    visits = (
        Visit.query.filter_by(user_id=current_user.id)
        .order_by(Visit.visited_at.desc())
        .all()
    )
    favorites = (
        Favorite.query.filter_by(user_id=current_user.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    return render_template(
        "profile.html", prog=prog, fun=fun, visits=visits, favorites=favorites
    )
