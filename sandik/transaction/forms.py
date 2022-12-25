from datetime import datetime

from wtforms import TextAreaField, SelectField, SubmitField, DecimalField, DateField, HiddenField, StringField, \
    IntegerField
from wtforms.validators import NumberRange, Optional

from sandik.sandik import db as sandik_db
from sandik.utils.db_models import MoneyTransaction
from sandik.utils.forms import CustomFlaskForm, input_required_validator, max_length_validator, min_number_validator


class MoneyTransactionForm(CustomFlaskForm):
    member = SelectField(
        label="Üye:",
        validators=[
            input_required_validator("Üye")
        ],
        choices=[("", "Üye seçiniz...")],
        coerce=str,
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

    use_untreated_amount = HiddenField()
    pay_future_payments = HiddenField()

    detail = TextAreaField(
        label="Detay:",
        validators=[
            Optional(),
            max_length_validator("Detay", 1000),
        ],
        render_kw={"placeholder": "Detay"}
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, sandik, form_title='Para işlemi formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.type.choices += [(key, value) for key, value in MoneyTransaction.TYPE.strings.items()]
        self.member.choices += sandik_db.members_form_choices(sandik=sandik)


class DebtPaymentForm(CustomFlaskForm):
    member = SelectField(
        label="Üye:",
        validators=[
            input_required_validator("Üye")
        ],
        choices=[("", "Üye seçiniz...")],
        coerce=str,
    )

    date = DateField(
        label="İşlem tarihi:",
        validators=[
            input_required_validator("İşlem tarihi"),
        ],
        default=datetime.today()
    )

    debt = SelectField(
        label="Borç:",
        validators=[
            input_required_validator("Ödenecek borç")
        ],
        choices=[("", "Önce üyeyi seçiniz...")],
        coerce=str,
        validate_choice=False,
    )

    amount = DecimalField(
        label="İşlem miktarı:",
        validators=[
            input_required_validator("İşlem miktarı"),
            NumberRange(message="İşlem miktarı 0'dan büyük bir sayı olmalıdır", min=0.001),
        ],
        render_kw={"placeholder": "0.01"},
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

    def __init__(self, sandik, form_title='Borç ödeme', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.member.choices += sandik_db.members_form_choices(sandik=sandik)


class ContributionForm(CustomFlaskForm):
    member = SelectField(
        label="Üye:",
        validators=[
            input_required_validator("Üye")
        ],
        choices=[("", "Üye seçiniz...")],
        coerce=str,
    )

    share = SelectField(
        label="Hisse:",
        validators=[
            input_required_validator("Hisse")
        ],
        choices=[("", "Hisse seçiniz...")],
        coerce=str,
        validate_choice=False
    )

    amount = DecimalField(
        label="İşlem miktarı:",
        validators=[
            input_required_validator("İşlem miktarı"),
            NumberRange(message="İşlem miktarı 0'dan büyük bir sayı olmalıdır", min=0.001),
        ],
        render_kw={"placeholder": "0.01"},
    )

    period = StringField(
        label="Aidat dönemi:",
        validators=[
            input_required_validator("Aidat dönemi"),
            max_length_validator("Aidat dönemi", 7),
        ],
        render_kw={"placeholder": "YYYY-AA"}
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, sandik, form_title='Aidat formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.member.choices += sandik_db.members_form_choices(sandik=sandik)


class DebtForm(CustomFlaskForm):
    member = SelectField(
        label="Üye:",
        validators=[
            input_required_validator("Üye")
        ],
        choices=[("", "Üye seçiniz...")],
        coerce=str,
    )

    share = SelectField(
        label="Hisse:",
        validators=[
            input_required_validator("Hisse")
        ],
        choices=[("", "Hisse seçiniz...")],
        coerce=str,
        validate_choice=False
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

    number_of_installment = IntegerField(
        label="Taksit sayısı:",
        validators=[
            Optional(),
            min_number_validator(field="Taksit sayısı",min=1),
        ],
        render_kw={"placeholder": "5"},
    )

    start_period = StringField(
        label="Ödeme başlangıç dönemi:",
        validators=[
            Optional(),
            max_length_validator("Ödeme başlangıç dönemi", 7),
        ],
        render_kw={"placeholder": "YYYY-AA"}
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

    def __init__(self, sandik, form_title='Para işlemi formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.member.choices += sandik_db.members_form_choices(sandik=sandik)

