from flask import Blueprint, flash, request, redirect, render_template, url_for, g
from flask_login import login_user, login_required, logout_user, current_user

from sandik.auth import db, forms, utils
from sandik.auth.exceptions import RegisterException, EmailAlreadyExist, AuthException
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
                web_user = db.add_web_user(is_active_=True, **form_data)
                Notification.WebUserAuth.send_register_web_user_notification(registered_web_user=web_user)

                flash("Hesap oluşturuldu.", 'success')
                return redirect(url_for("auth_page_bp.login_page"))
            except RegisterException as ex:
                flash(f"{ex}", 'danger')
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
                next_page = get_next_url(request.args, default_url=url_for("general_page_bp.index_page"))
                return redirect(next_page)
            else:
                flash("Kullanıcınız henüz onaylanmamış.", 'danger')
        else:  # If password or username is incorrect
            flash("E-posta adresi veya parola doğru değil", 'danger')
    return render_template("auth/login_page.html", page_info=FormPI(form=form, title="Giriş yap"))


@auth_page_bp.route("/cikis")
@login_required
def logout_page():
    logout_user()
    flash("Güvenli çıkış yapıldı", 'success')
    return redirect(url_for("general_page_bp.index_page"))


@auth_page_bp.route("/parola-sifirla", methods=['GET', 'POST'])
def forgotten_password_page():
    form = forms.ForgottenPasswordForm()

    if form.validate_on_submit():
        web_user = db.get_web_user(email_address=form.email_address.data)
        if web_user:
            utils.send_renew_password_email(web_user=web_user)
            flash("Parola sıfırlama bağlantısı e-posta adresinize gönderildi.", "success")
            form = None
        else:
            flash("Kullanıcı bulunamadı.", "success")

    return render_template("auth/register_page.html",
                           page_info=FormPI(title="Parola sıfırlama isteği", form=form))


@auth_page_bp.route("/parola-sifirla/<string:token>", methods=['GET', 'POST'])
def password_reset_page(token):
    form = forms.PasswordResetForm()

    try:
        web_user = utils.get_web_user_from_password_reset_token(token=token)
        if form.validate_on_submit():
            db.password_reset(web_user=web_user, new_password=form.new_password.data)
            return redirect(url_for("auth_page_bp.login_page"))
    except AuthException as e:
        flash(f"{e}", "danger")
        form = None

    return render_template("auth/auth_forms.html", page_info=FormPI(title="Parola sıfırlama", form=form))


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
            flash(f"{ex}", 'danger')
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


def _reminder_preference_page_base(web_user, title, template):
    """Hatırlatma tercihi formunun ortak gövdesi.

    İki giriş noktası paylaşır: giriş yapmış kullanıcı (`/tercihlerim`) ve e-postadaki
    jetonlu bağlantı (`/tercih/<token>`). Fark yalnızca kullanıcıya nasıl ulaşıldığı ve
    hangi kabuğun kullanıldığıdır; form ve kaydetme mantığı aynıdır.
    """
    form = forms.ReminderPreferenceForm()

    if form.validate_on_submit():
        month_start_day, next_month_day = form.to_days()
        db.update_reminder_preference(web_user=web_user, updated_by=web_user,
                                      month_start_day=month_start_day, next_month_day=next_month_day)
        flash("E-posta hatırlatma tercihleriniz kaydedildi", "success")
        form.fill_from_days(month_start_day=month_start_day, next_month_day=next_month_day)
    elif not form.is_submitted():
        month_start_day, next_month_day = web_user.get_reminder_days()
        form.fill_from_days(month_start_day=month_start_day, next_month_day=next_month_day)

    return render_template(template, page_info=FormPI(title=title, form=form))


# İSİMLENDİRME NOTU — sayfada bugün yalnızca ödeme hatırlatma e-postalarının günü var, bu yüzden
# kullanıcıya görünen etiketler ve fonksiyon adları ("E-posta ... tercihlerim",
# `reminder_preference_*`) e-postaya özeldir. **E-postayla ilgisi olmayan ilk tercih eklendiğinde**
# bunlar "Kullanıcı tercihlerim" / `preference_*` olarak yeniden adlandırılmalıdır; ikisi de
# ucuzdur (etiket metni ve `url_for` çağrıları).
#
# **Adresler bilerek şimdiden genel tutuldu** (`/tercihlerim`, `/tercih/<token>`): bunlar sonradan
# değiştirilemez. `/tercih/<token>` gönderilmiş e-postaların içinde, kullanıcıların posta
# kutusunda süresiz durur; adres değişirse eski e-postalardaki bağlantılar kırılır. Zorunlu
# kalınırsa eski adres kalıcı olarak yenisine yönlendirilmelidir (ikinci bir route + redirect).
@auth_page_bp.route("/tercihlerim", methods=["GET", "POST"])
@login_required
def reminder_preference_page():
    return _reminder_preference_page_base(web_user=current_user, title="E-posta hatırlatma tercihlerim",
                                          template="auth/reminder_preference_page.html")


@auth_page_bp.route("/tercih/<string:token>", methods=["GET", "POST"])
def reminder_preference_by_token_page(token):
    """E-postadaki bağlantı. Giriş yapmayı gerektirmez; jeton tek başına yeterlidir."""
    template = "auth/reminder_preference_by_token_page.html"
    try:
        web_user = utils.get_web_user_from_reminder_preference_token(token=token)
    except AuthException as e:
        flash(f"{e}", "danger")
        return render_template(template, page_info=FormPI(title="E-posta hatırlatma tercihi", form=None))

    return _reminder_preference_page_base(web_user=web_user, title="E-posta hatırlatma tercihi",
                                          template=template)


@auth_page_bp.route("/parola-guncelle", methods=["GET", "POST"])
@login_required
def update_password_page():
    form = forms.UpdatePasswordForm()

    if form.validate_on_submit():
        if form.new_password.data != form.new_password_verification.data:
            flash(u"Parolalar eşleşmiyor!", 'danger')
        elif not db.get_web_user(web_user=current_user, password=form.old_password.data):
            flash(u"Eski parola doğrulanamadı!", 'danger')
        else:
            db.update_web_user(web_user=current_user, updated_by=current_user, password=form.new_password.data)
            flash("Kullanıcı parolası güncellendi", "success")
            next_url = get_next_url(request.args, default_url=url_for("general_page_bp.index_page"))
            return redirect(next_url)

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Kullanıcı parolasını güncelle", form=form,
                                            active_dropdown="web-users"))
