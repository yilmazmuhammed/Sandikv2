from flask import Blueprint, flash, request, redirect, render_template, url_for, g
from flask_login import login_user, login_required, logout_user, current_user

from sandik.auth import db, forms
from sandik.auth.exceptions import RegisterException
from sandik.auth.requirement import admin_required
from sandik.utils import LayoutPI
from sandik.utils.forms import flask_form_to_dict, FormPI

auth_page_bp = Blueprint(
    'auth_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets_auth'
)


@auth_page_bp.route('/kayit', methods=['GET', 'POST'])
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("general_page_bp.index_page"))

    form = forms.RegisterForm()

    if form.validate_on_submit():
        if form.password.data != form.password_verification.data:
            flash(u"Parolalar eşleşmiyor", 'danger')
        else:
            try:
                form_data = flask_form_to_dict(request_form=request.form, exclude=['password_verification'])
                db.add_web_user(is_active_=True, **form_data)
                flash("Account created.", 'success')
                return redirect(url_for("auth_page_bp.login_page"))
            except RegisterException as ex:
                flash(u"%s" % ex, 'danger')
    return render_template("auth/register_page.html", page_info=FormPI(form=form, title="Kayıt ol"))


@auth_page_bp.route('/giris', methods=['GET', 'POST'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("general_page_bp.index_page"))

    form = forms.LoginForm()

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, boolean_fields=['remember_me'])
        remember_me = form_data.pop("remember_me")
        web_user = db.get_web_user(**form_data)
        if web_user:
            if login_user(web_user, remember=remember_me):
                flash("Giriş yapıldı", 'success')
                next_page = request.args.get("next", "/")
                return redirect(next_page)
            else:
                flash("Kullanıcınız henüz onaylanmamış.", 'danger')
        else:
            flash("E-posta adresi veya parola doğru değil", 'danger')
    return render_template("auth/login_page.html", page_info=FormPI(form=form, title="Giriş yap"))


@auth_page_bp.route("/cikis")
@login_required
def logout_page():
    logout_user()
    flash("Güvenli çıkış yapıldı", 'success')
    return redirect(url_for("general_page_bp.index_page"))


@auth_page_bp.route("/kullanicilar")
@admin_required
def web_users_page():
    g.web_users = db.select_web_users().order_by(lambda wu: wu.name_surname.lower())
    return render_template("auth/web_users_page.html",
                           page_info=LayoutPI(title="Kullanıcı listesi", active_dropdown="web-users"))


@auth_page_bp.route("/kullanici/<int:web_user_id>/onayla")
@admin_required
def confirm_web_user_page(web_user_id):
    db.confirm_web_user(web_user_id, updated_by=current_user)
    return redirect(request.referrer)


@auth_page_bp.route("/kullanici/<int:web_user_id>/engelle")
@admin_required
def block_web_user_page(web_user_id):
    db.block_web_user(web_user_id, updated_by=current_user)
    return redirect(request.referrer)
