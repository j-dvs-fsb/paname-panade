from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from .extensions import db
from .models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/inscription", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        prenom = (request.form.get("prenom") or "").strip()
        date_naissance = request.form.get("date_naissance") or ""

        errors = []
        if not email or "@" not in email:
            errors.append("Email invalide.")
        if len(password) < 6:
            errors.append("Le mot de passe doit faire au moins 6 caractères.")
        if not prenom:
            errors.append("Le prénom est requis.")
        if not date_naissance:
            errors.append("La date de naissance est requise.")
        if User.query.filter_by(email=email).first():
            errors.append("Cet email est déjà utilisé.")

        try:
            dn = datetime.strptime(date_naissance, "%Y-%m-%d").date()
        except ValueError:
            dn = None
            errors.append("Date de naissance invalide.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("auth/register.html", form=request.form)

        user = User(email=email, prenom=prenom, date_naissance=dn)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"Bienvenue {prenom} ! Ton compte est créé.", "success")
        return redirect(url_for("main.profile"))

    return render_template("auth/register.html", form={})


@auth_bp.route("/connexion", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.profile"))
        flash("Email ou mot de passe incorrect.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/deconnexion")
@login_required
def logout():
    logout_user()
    flash("À bientôt !", "info")
    return redirect(url_for("main.index"))
