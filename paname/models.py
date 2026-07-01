from datetime import datetime, date

from flask_login import UserMixin

FR_MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def format_fr_date(d):
    """date(2026, 4, 15) -> '15 avril 2026'. None -> ''."""
    if not d:
        return ""
    return f"{d.day} {FR_MONTHS[d.month - 1]} {d.year}"
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    prenom = db.Column(db.String(80), nullable=False)
    date_naissance = db.Column(db.Date, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    favorites = db.relationship("Favorite", backref="user", cascade="all, delete-orphan")
    visits = db.relationship("Visit", backref="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def birthday_26(self):
        """Date des 26 ans."""
        return self.date_naissance.replace(year=self.date_naissance.year + 26)

    @property
    def days_until_26(self):
        return (self.birthday_26 - date.today()).days


# Conditions de gratuité d'un musée (clé stockée -> libellé). Multi-sélection.
FREE_ACCESS_LABELS = {
    "gratuit_26": "Gratuit pour les -26 ans (UE)",
    "permanent": "Collections permanentes gratuites",
    "premier_dimanche": "Gratuit le 1er dimanche du mois",
    "gratuit_tous": "Gratuit pour tous",
}


class Museum(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    museofile_id = db.Column(db.String(20), unique=True, index=True)  # ID officiel (dataset Île-de-France)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    address = db.Column(db.String(300))
    arrondissement = db.Column(db.String(20))
    website = db.Column(db.String(500))
    expos_url = db.Column(db.String(500))  # page "expositions en cours" (cible scraping)
    free_access = db.Column(db.String(120))  # clés CSV, cf. FREE_ACCESS_LABELS
    image_url = db.Column(db.String(500))
    logo_url = db.Column(db.String(500))     # logo du musée (collections permanentes)
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

    expositions = db.relationship("Exposition", backref="museum", cascade="all, delete-orphan")

    @property
    def free_access_list(self):
        return [k for k in (self.free_access or "").split(",") if k]

    @property
    def free_labels(self):
        return [FREE_ACCESS_LABELS[k] for k in self.free_access_list if k in FREE_ACCESS_LABELS]

    @property
    def is_permanent_free(self):
        """Compat : collections accessibles gratuitement à tous."""
        keys = self.free_access_list
        return "permanent" in keys or "gratuit_tous" in keys


# Catégories de prix (clé stockée -> libellé affiché)
PRICE_LABELS = {
    "gratuit_tous": "Gratuit pour tous",
    "gratuit_26": "Gratuit pour les -26 ans",
    "reduit_26": "Tarif réduit pour les -26 ans",
}

# Type de réservation (clé stockée -> libellé affiché)
RESERVATION_LABELS = {
    "obligatoire": "Réservation obligatoire",
    "conseillee": "Réservation conseillée",
    "non_necessaire": "Sans réservation",
}


class Exposition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    museum_id = db.Column(db.Integer, db.ForeignKey("museum.id"))
    date_start = db.Column(db.Date)
    date_end = db.Column(db.Date)
    schedule = db.Column(db.String(500))   # horaires en texte libre
    url = db.Column(db.String(500))        # site / billetterie
    image_url = db.Column(db.String(500))  # image distante (source)
    image_local = db.Column(db.String(300))  # chemin relatif dans static/ si téléchargée

    # Lieu
    venue_name = db.Column(db.String(200))   # nom du lieu (peut différer du musée)
    address = db.Column(db.String(300))      # adresse / rue
    postal_code = db.Column(db.String(10))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

    # Tarif & réservation
    price_type = db.Column(db.String(50), default="gratuit")  # legacy (gratuit/payant)
    price_category = db.Column(db.String(30), default="gratuit_tous")  # cf. PRICE_LABELS
    reservation = db.Column(db.String(20), default="non_necessaire")   # cf. RESERVATION_LABELS
    reservation_url = db.Column(db.String(500))

    source = db.Column(db.String(80))      # "seed", "que-faire-a-paris", "scraping", "manuel"
    external_id = db.Column(db.String(120), index=True)
    status = db.Column(db.String(20), default="published", nullable=False)  # draft / published

    favorites = db.relationship("Favorite", backref="exposition", cascade="all, delete-orphan")
    visits = db.relationship("Visit", backref="exposition", cascade="all, delete-orphan")

    @property
    def price_label(self):
        return PRICE_LABELS.get(self.price_category, "Gratuit pour tous")

    @property
    def reservation_label(self):
        return RESERVATION_LABELS.get(self.reservation, "Sans réservation")

    @property
    def image(self):
        """URL à afficher : la copie locale si présente, sinon l'image distante."""
        if self.image_local:
            from flask import url_for
            return url_for("static", filename=self.image_local)
        return self.image_url

    @property
    def map_lat(self):
        """Coordonnée de la carte : celle de l'expo, sinon celle du musée."""
        if self.lat is not None:
            return self.lat
        return self.museum.lat if self.museum else None

    @property
    def map_lon(self):
        if self.lon is not None:
            return self.lon
        return self.museum.lon if self.museum else None

    @property
    def is_permanent(self):
        return self.source == "permanent"

    @property
    def date_label(self):
        """Période en clair : « Du … au … », « Jusqu'au … », « À partir du … »."""
        if self.is_permanent and not (self.date_start or self.date_end):
            return "En permanence"
        if self.date_start and self.date_end:
            return f"Du {format_fr_date(self.date_start)} au {format_fr_date(self.date_end)}"
        if self.date_end:
            return f"Jusqu'au {format_fr_date(self.date_end)}"
        if self.date_start:
            return f"À partir du {format_fr_date(self.date_start)}"
        return "Dates non communiquées"

    @property
    def is_current(self):
        today = date.today()
        if self.date_end and self.date_end < today:
            return False
        return True

    @property
    def avg_rating(self):
        rated = [v.rating for v in self.visits if v.rating]
        return round(sum(rated) / len(rated), 1) if rated else None

    @property
    def rating_count(self):
        return len([v for v in self.visits if v.rating])


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exposition_id = db.Column(db.Integer, db.ForeignKey("exposition.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "exposition_id", name="uq_fav"),)


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exposition_id = db.Column(db.Integer, db.ForeignKey("exposition.id"), nullable=False)
    rating = db.Column(db.Integer)         # 1..5
    comment = db.Column(db.Text)
    visited_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "exposition_id", name="uq_visit"),)
