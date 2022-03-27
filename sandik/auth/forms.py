from wtforms import PasswordField, SubmitField, BooleanField, StringField, EmailField, TelField
from wtforms.validators import Email, Optional

from sandik.utils.forms import CustomFlaskForm, input_required_validator, max_length_validator, PhoneNumberValidator


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
            max_length_validator("E-posta adresi", 40),
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
        label="Beni hatırla"
    )

    submit = SubmitField(label="Giriş yap")

    def __init__(self, *args, **kwargs):
        super().__init__(form_title='Giriş yap', f_class="form-validation", *args, **kwargs)
