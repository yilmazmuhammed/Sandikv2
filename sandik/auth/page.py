from flask import Blueprint, flash, request, redirect, render_template, url_for, g
from flask_login import login_user, login_required, logout_user, current_user

from sandik.auth import db, forms, utils
from sandik.auth.exceptions import RegisterException, EmailAlreadyExist
from sandik.auth.requirement import admin_required, web_user_required
from sandik.auth.utils import Notification
from sandik.utils import LayoutPI, get_next_url
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
                registered_web_user = db.add_web_user(is_active_=True, **form_data)
                Notification.WebUserAuth.send_register_web_user_notification(registered_web_user=registered_web_user)
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


@web_user_required
def update_web_user_page_base(web_user_id):
    form = forms.UpdateWebUserForm()

    if not form.is_submitted():
        form.fill_from_web_user(web_user=g.web_user)
    elif form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, exclude=["email_address"], with_empty_fields=True)
        try:
            db.update_web_user(web_user=g.web_user, updated_by=current_user, **form_data)
            flash("Kullanıcı bilgileri güncellendi", "success")
        except EmailAlreadyExist as ex:
            flash(u"%s" % ex, 'danger')
    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Site kullanıcısını güncelle", form=form,
                                            active_dropdown="web-users"))


@auth_page_bp.route("/kullanici/<int:web_user_id>/guncelle", methods=["GET", "POST"])
@admin_required
def update_web_user_page(web_user_id):
    return update_web_user_page_base(web_user_id=web_user_id)


@auth_page_bp.route("/bilgilerimi-guncelle", methods=["GET", "POST"])
@login_required
def update_profile_page():
    return update_web_user_page_base(web_user_id=current_user.id)


@auth_page_bp.route("/parola-guncelle", methods=["GET", "POST"])
@login_required
def update_password_page():
    form = forms.UpdatePasswordForm()

    if form.validate_on_submit():
        if form.new_password.data != form.new_password_verification.data:
            flash(u"Parolalar eşleşmiyor!", 'danger')
        elif not db.get_web_user(web_user=current_user, password=form.old_password.data):
            flash(u"Eski parola doğrulanamadı!", 'danger')

        db.update_web_user(web_user=current_user, updated_by=current_user, password=form.new_password.data)
        flash("Kullanıcı parolası güncellendi", "success")
        next_url = get_next_url(request.args, default_url=url_for("general_page_bp.index_page"))
        return redirect(next_url)

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Kullanıcı parolasını güncelle", form=form,
                                            active_dropdown="web-users"))
