from wtforms import PasswordField, SubmitField, BooleanField, StringField, EmailField
from wtforms.validators import Email

from sandik.utils.forms import CustomFlaskForm, input_required_validator, max_length_validator


class RegisterForm(CustomFlaskForm):
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

    email_address = EmailField(
        "E-posta adresi:",
        validators=[
            input_required_validator("E-posta adresi"),
            max_length_validator("E-posta adresi", 40),
            Email("Geçerli bir e-posta adresi giriniz")
        ],
        render_kw={"placeholder": "Email address"}
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(form_title='Kayıt formu', f_class="form-validation", *args, **kwargs)


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
