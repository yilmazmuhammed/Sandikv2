from datetime import datetime

from wtforms import SelectField, StringField, DateField, DecimalField, SubmitField, TextAreaField
from wtforms.validators import Optional, NumberRange

from sandik.auth import db as auth_db
from sandik.utils.db_models import WebsiteTransaction
from sandik.utils.forms import CustomFlaskForm, input_required_validator, max_length_validator


class WebsiteTransactionForm(CustomFlaskForm):
    web_user = SelectField(
        label="Site kullanıcısı:",
        validators=[
            Optional(),
        ],
        choices=[("", "Kullanıcı seçiniz...")],
        coerce=str,
    )

    payer = StringField(
        label="Bağışçı ismi:",
        validators=[
            Optional(),
            max_length_validator("Bağışçı ismi", 100),
        ],
        render_kw={"placeholder": "Bağışçı ismi"}
    )

    date = DateField(
        label="İşlem tarihi:",
        validators=[
            input_required_validator("İşlem tarihi"),
        ],
        default=datetime.today()
    )

    amount = DecimalField(
        label="İşlem miktarı:",
        validators=[
            input_required_validator("İşlem miktarı"),
            NumberRange(message="İşlem miktarı 0'dan büyük bir sayı olmalıdır", min=0.001),
        ],
        render_kw={"placeholder": "0.01"},
    )

    type = SelectField(
        label="İşlem türü:",
        validators=[
            input_required_validator("İşlem türü")
        ],
        choices=[("", "İşlem türünü seçiniz...")],
        coerce=str,
    )

    category_list = SelectField(
        label="İşlem kategorisi:",
        choices=[("", "İşlem kategorisini seçiniz..."), ("", "<divider>")],
        coerce=str,
        validators=[
            input_required_validator("İşlem kategorisi"),
        ],
    )

    category = StringField(
        label="Yeni işlem kategorisi:",
        validators=[
            input_required_validator("Yeni işlem kategorisi"),
            max_length_validator("Yeni işlem kategorisi", 40),
        ],
        render_kw={"placeholder": "Yeni işlem kategorisi"}
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

    def __init__(self, categories, form_title='Websitesi işlemi formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.type.choices += [(key, value) for key, value in WebsiteTransaction.TYPE.strings.items()]
        self.web_user.choices += auth_db.web_users_form_choices(only_active_user=True)
        self.category_list.choices += [(t, t) for t in categories]
        self.category_list.choices += [("", "<divider>"), ("new", "Yeni işlem kategorisi ekle")]
