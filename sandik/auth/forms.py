from wtforms import PasswordField, SubmitField, BooleanField, StringField, EmailField, TelField, SelectField
from wtforms.validators import Email, Optional, EqualTo

from sandik.utils.forms import CustomFlaskForm, input_required_validator, max_length_validator, PhoneNumberValidator
from sandik.utils.db_models import ReminderPreference


class WebUserForm(CustomFlaskForm):
    name = StringField(
        label="İsim:",
        validators=[
            input_required_validator("İsim"),
            max_length_validator("İsim", 100),
        ],
        render_kw={"placeholder": "İsim"}
    )

    surname = StringField(
        label="Soyisim:",
        validators=[
            input_required_validator("Soyisim"),
            max_length_validator("Soyisim", 100),
        ],
        render_kw={"placeholder": "Soyisim"}
    )

    phone_number = TelField(
        label="Telefon numarası:",
        validators=[
            Optional(),
            PhoneNumberValidator("Telefon numaranızı ülke kodunu seçerek, sayılar arasında boşluk olmadan giriniz.")
        ],
        render_kw={"placeholder": "Telefon numarası"}
    )

    email_address = EmailField(
        "E-posta adresi:",
        validators=[
            input_required_validator("E-posta adresi"),
            max_length_validator("E-posta adresi", 254),
            Email("Geçerli bir e-posta adresi giriniz")
        ],
        render_kw={"placeholder": "Email address"}
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, form_title='Kullanıcı formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.email_address.render_kw["readonly"] = False


class RegisterForm(WebUserForm):
    password = PasswordField(
        "Parola:",
        validators=[
            input_required_validator("Parola"),
            max_length_validator("Parola", 30),
        ],
        render_kw={"placeholder": "Parola"}
    )

    password_verification = PasswordField(
        "Parola tekrarı:",
        validators=[
            input_required_validator("Parola tekrarı"),
            max_length_validator("Parola tekrarı", 30),
            EqualTo("password", message="Parolalar birbiriyşe eşleşmiyor."),
        ],
        render_kw={"placeholder": "Parola tekrarı"}
    )

    submit = SubmitField(label="Kayıt ol")

    def __init__(self, form_title='Kayıt formu', *args, **kwargs):
        super().__init__(form_title=form_title, f_class="form-validation", *args, **kwargs)


class UpdateWebUserForm(WebUserForm):
    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='Kayıt formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.email_address.render_kw["readonly"] = True

    def fill_from_web_user(self, web_user):
        self.email_address.data = web_user.email_address
        self.phone_number.data = web_user.phone_number
        self.name.data = web_user.name
        self.surname.data = web_user.surname


class LoginForm(CustomFlaskForm):
    email_address = EmailField(
        "E-posta adresi:",
        validators=[
            input_required_validator("E-posta adresi"),
            max_length_validator("E-posta adresi", 254),
            Email("Geçerli bir e-posta adresi giriniz")
        ],
        render_kw={"placeholder": "E-posta adresi"}
    )

    password = PasswordField(
        "Parola:",
        validators=[
            input_required_validator("Parola"),
            max_length_validator("Parola", 30),
        ],
        render_kw={"placeholder": "Parola"}
    )

    remember_me = BooleanField(
        label="Beni hatırla",
        default=True
    )

    submit = SubmitField(label="Giriş yap")

    def __init__(self, *args, **kwargs):
        super().__init__(form_title='Giriş yap', f_class="form-validation", *args, **kwargs)


class UpdatePasswordForm(CustomFlaskForm):
    old_password = PasswordField(
        "Eski parola:",
        validators=[
            input_required_validator("Eski parola"),
            max_length_validator("Eski parola", 30),
        ],
        render_kw={"placeholder": "Eski parola"}
    )

    new_password = PasswordField(
        "Yeni parola:",
        validators=[
            input_required_validator("Yeni parola"),
            max_length_validator("Yeni parola", 30),
        ],
        render_kw={"placeholder": "Yeni parola"}
    )

    new_password_verification = PasswordField(
        "Yeni parola tekrarı:",
        validators=[
            input_required_validator("Yeni parola tekrarı"),
            max_length_validator("Yeni parola tekrarı", 30),
            EqualTo("new_password", message="Parolalar birbiriyşe eşleşmiyor."),
        ],
        render_kw={"placeholder": "Yeni parola tekrarı"}
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='Parola güncelleme formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)


class ForgottenPasswordForm(CustomFlaskForm):
    email_address = EmailField(
        "E-posta adresi:",
        validators=[
            input_required_validator("E-posta adresi"),
            max_length_validator("E-posta adresi", 254),
            Email("Geçerli bir e-posta adresi giriniz")
        ],
        render_kw={"placeholder": "Email address"}
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, form_title='Parola sıfırlama isteği formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)


class PasswordResetForm(UpdatePasswordForm):
    old_password = None

    def __init__(self, form_title='Parola sıfırlama formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)


class ReminderPreferenceForm(CustomFlaskForm):
    """Ödeme hatırlatma e-postalarının açık/kapalı ve gün tercihi.

    Veritabanında tek bir sayı tutulur (`0` = istemiyorum, `1`-`28` = o gün), ama kullanıcıya iki
    ayrı soru olarak gösterilir: "istiyor musunuz?" ve "hangi gün?". Çeviri `to_days()` /
    `fill_from_days()` içindedir; sayfa katmanı iki temsili birbirine karıştırmaz.
    """
    month_start_enabled = BooleanField(
        label="Ay başı hatırlatması: bu ayın ödemeleri",
        default=True
    )
    month_start_day = SelectField(
        label="Ayın kaçında gönderilsin?",
        choices=[(str(d), f"Her ayın {d}. günü") for d in
                 range(ReminderPreference.MIN_DAY, ReminderPreference.MAX_DAY + 1)],
        default=str(ReminderPreference.DEFAULT_MONTH_START_DAY),
        coerce=str,
    )

    next_month_enabled = BooleanField(
        label="Ay sonu hatırlatması: bu ay + gelecek ayın ödemeleri",
        default=True
    )
    next_month_day = SelectField(
        label="Ayın kaçında gönderilsin?",
        choices=[(str(d), f"Her ayın {d}. günü") for d in
                 range(ReminderPreference.MIN_DAY, ReminderPreference.MAX_DAY + 1)],
        default=str(ReminderPreference.DEFAULT_NEXT_MONTH_DAY),
        coerce=str,
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='E-posta hatırlatma tercihlerim', *args, **kwargs):
        # form_name/form_id şablondaki JS seçicisiyle eşleşmeli (parts/reminder_preference_form.html)
        kwargs.setdefault("form_name", "reminder_preference_form")
        kwargs.setdefault("form_id", "reminder_preference_form")
        super().__init__(form_title=form_title, *args, **kwargs)

    def fill_from_days(self, month_start_day, next_month_day):
        """`(0|1-28, 0|1-28)` -> form alanları. Kapalıysa gün kutusu varsayılanda bırakılır."""
        self.month_start_enabled.data = month_start_day != ReminderPreference.OFF
        self.next_month_enabled.data = next_month_day != ReminderPreference.OFF
        if month_start_day != ReminderPreference.OFF:
            self.month_start_day.data = str(month_start_day)
        if next_month_day != ReminderPreference.OFF:
            self.next_month_day.data = str(next_month_day)

    def to_days(self):
        """Form alanları -> `(month_start_day, next_month_day)`; kapalı olan `0` olur."""
        def day_of(enabled_field, day_field, default):
            if not enabled_field.data:
                return ReminderPreference.OFF
            try:
                day = int(day_field.data)
            except (TypeError, ValueError):
                return default
            return day if ReminderPreference.is_valid_day(day) and day != ReminderPreference.OFF else default

        return (day_of(self.month_start_enabled, self.month_start_day,
                       ReminderPreference.DEFAULT_MONTH_START_DAY),
                day_of(self.next_month_enabled, self.next_month_day,
                       ReminderPreference.DEFAULT_NEXT_MONTH_DAY))
