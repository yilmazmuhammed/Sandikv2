from wtforms import StringField, BooleanField, SubmitField

from sandik.utils.forms import CustomFlaskForm, max_length_validator, input_required_validator, IbanValidator


class BankAccountForm(CustomFlaskForm):
    title = StringField(
        "Başlık",
        validators=[
            input_required_validator("Başlık"),
            max_length_validator("Başlık", 100),
        ],
        render_kw={"placeholder": "Başlık"}
    )

    holder = StringField(
        "Hesap sahibi",
        validators=[
            input_required_validator("Hesap sahibi"),
            max_length_validator("Hesap sahibi", 100),
        ],
        render_kw={"placeholder": "Hesap sahibi"}
    )

    iban = StringField(
        "IBAN",
        validators=[
            input_required_validator("IBAN"),
            IbanValidator(),
        ],
        render_kw={"placeholder": "IBAN"}
    )

    is_primary = BooleanField(
        label="Varsayılan hesap mı?",
        default=True
    )

    submit = SubmitField(label="Giriş yap")

    def __init__(self, form_title="Banka hesabı formu", *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)

    def fill_with_bank_account(self, bank_account):
        self.title.data = bank_account.title
        self.holder.data = bank_account.holder
        self.iban.data = bank_account.iban
        self.is_primary.data = bank_account.is_primary
