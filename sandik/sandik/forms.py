from wtforms import StringField, IntegerField, TextAreaField, SubmitField, SelectField
from wtforms.validators import NumberRange, Optional

from sandik.sandik import db
from sandik.utils.forms import CustomFlaskForm, input_required_validator, max_length_validator


class SandikForm(CustomFlaskForm):
    name = StringField(
        "Sandık ismi",
        validators=[
            input_required_validator("Sandık ismi"),
            max_length_validator("Sandık ismi", 100),
        ],
        id='name', render_kw={"placeholder": "Sandık ismi"}
    )

    # TODO IntegerField html5'ten import edilse nasıl oluyor
    contribution_amount = IntegerField(
        label="Aidat miktarı:",
        validators=[
            input_required_validator("Aidat miktarı"),
            NumberRange(message="Aidat miktarını sayı olarak giriniz"),
        ],
        render_kw={"placeholder": "0"},
    )

    detail = TextAreaField(
        label="Detay:",
        validators=[
            Optional(),
            max_length_validator("Detay", 1000),
        ],
        render_kw={"placeholder": "Detay"}
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='Kayıt formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)


class SelectSandikForm(CustomFlaskForm):
    sandik = SelectField(
        label="Sandık:",
        validators=[
            input_required_validator("Sandık")
        ],
        choices=[("", "Sandık seçiniz...")],
        coerce=str,
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='Sandık seçim formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.sandik.choices += db.sandiks_form_choices()


class SelectMemberForm(CustomFlaskForm):
    member = SelectField(
        label="Üye:",
        validators=[
            input_required_validator("Üye")
        ],
        choices=[("", "Üye seçiniz...")],
        coerce=str,
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, sandik, form_title='Üye seç', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.member.choices += db.members_form_choices(sandik=sandik)
