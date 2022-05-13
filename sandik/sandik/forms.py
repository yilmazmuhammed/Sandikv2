from datetime import datetime

from wtforms import StringField, IntegerField, TextAreaField, SubmitField, SelectField, BooleanField, EmailField, \
    DateField, DecimalField
from wtforms.validators import NumberRange, Optional, Email

from sandik.auth import db as auth_db
from sandik.sandik import db
from sandik.utils import sandik_preferences
from sandik.utils.db_models import Sandik, SmsPackage
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

    type = SelectField(
        label="Sandık türü:",
        validators=[
            input_required_validator("Sandık türü:"),
        ],
        choices=[("", "Sandık türünü seçiniz...")],
        coerce=str,
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
        self.type.choices += list(Sandik.TYPE.strings.items())


class SandikTypeForm(CustomFlaskForm):

    type = SelectField(
        label="Sandık türü:",
        validators=[
            input_required_validator("Sandık türü:"),
        ],
        choices=[("", "Sandık türünü seçiniz...")],
        coerce=str,
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='Sandık türü formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.type.choices += [(str(value), text )for value, text in Sandik.TYPE.strings.items()]


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


class SandikAuthorityForm(CustomFlaskForm):
    name = StringField(
        "Yetki başlığı",
        validators=[
            input_required_validator("Yetki başlığı"),
            max_length_validator("Yetki başlığı", 100),
        ],
        render_kw={"placeholder": "Yetki başlığı"}
    )

    is_primary = BooleanField(
        label="Yönetici mi?",
        default=False
    )

    can_read = BooleanField(
        label="Okuma izni",
        default=False
    )

    can_write = BooleanField(
        label="Yazma izni",
        default=False
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, form_title='Sandık yetkisi formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)


class AddAuthorizedForm(CustomFlaskForm):
    member = SelectField(
        label="Üye:",
        validators=[
            Optional(),
        ],
        choices=[("", "Üye seçiniz...")],
        coerce=str,
    )

    email_address = EmailField(
        "E-posta adresi:",
        validators=[
            Optional(),
            max_length_validator("E-posta adresi", 40),
            Email("Geçerli bir e-posta adresi giriniz")
        ],
        render_kw={"placeholder": "Email address"}
    )

    authority = SelectField(
        label="Sandık yetkisi:",
        validators=[
            input_required_validator("Sandık yetkisi")
        ],
        choices=[("", "Sandık yetkisi seçiniz...")],
        coerce=str,
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, sandik, form_title='Sandık yetkisi formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.member.choices += db.members_form_choices(sandik=sandik)
        self.authority.choices += db.sandik_authorities_form_choices(sandik=sandik)


class AddMemberForm(CustomFlaskForm):
    web_user = SelectField(
        label="Site kullanıcısı:",
        validators=[
            Optional(),
        ],
        choices=[("", "Kullanıcı seçiniz...")],
        coerce=str,
    )

    email_address = EmailField(
        "E-posta adresi:",
        validators=[
            Optional(),
            max_length_validator("E-posta adresi", 80),
            Email("Geçerli bir e-posta adresi giriniz")
        ],
        render_kw={"placeholder": "Email address"}
    )

    date_of_membership = DateField(
        label="Üyelik tarihi:",
        validators=[
            input_required_validator("Üyelik tarihi"),
        ],
        default=datetime.today()
    )

    contribution_amount = DecimalField(
        label="Aidat miktarı:",
        validators=[
            input_required_validator("Aidat miktarı"),
            NumberRange(message="Aidat miktarı 0'dan büyük bir sayı olmalıdır", min=0.001),
        ],
        render_kw={"placeholder": "100"},
    )

    number_of_share = IntegerField(
        label="Hisse sayısı:",
        validators=[
            input_required_validator("Hisse sayısı"),
            NumberRange(message="Hisse sayısı en az 1 olmalıdır.", min=1),
        ],
        default=1,
        render_kw={"placeholder": "5"},
    )

    detail = TextAreaField(
        label="Detay:",
        validators=[
            Optional(),
            max_length_validator("Detay", 1000),
        ],
        render_kw={"placeholder": "Detay"}
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, sandik, form_title='Üye ekleme formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.web_user.choices += auth_db.web_users_form_choices(exclusions=sandik.members_set.web_user_ref)
        max_share = sandik_preferences.get_max_number_of_share(sandik=sandik)
        self.number_of_share.validators.append(
            NumberRange(message=f"Hisse sayısı {max_share}'dan fazla olamaz", max=max_share)
        )


class EditMemberForm(CustomFlaskForm):
    email_address = EmailField(
        "E-posta adresi:",
        validators=[
            input_required_validator("E-posta adresi"),
            max_length_validator("E-posta adresi", 80),
            Email("Geçerli bir e-posta adresi giriniz")
        ],
        render_kw={"placeholder": "Email address"}
    )

    date_of_membership = DateField(
        label="Üyelik tarihi:",
        validators=[
            input_required_validator("Üyelik tarihi"),
        ],
    )

    contribution_amount = DecimalField(
        label="Aidat miktarı:",
        validators=[
            input_required_validator("Aidat miktarı"),
            NumberRange(message="Aidat miktarı 0'dan büyük bir sayı olmalıdır", min=0.001),
        ],
        render_kw={"placeholder": "100"},
    )

    detail = TextAreaField(
        label="Detay:",
        validators=[
            Optional(),
            max_length_validator("Detay", 1000),
        ],
        render_kw={"placeholder": "Detay"}
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, form_title='Üye düzenleme formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)

    def fill_values_with_member(self, member):
        self.email_address.data = member.web_user_ref.email_address
        self.contribution_amount.data = member.contribution_amount
        self.date_of_membership.data = member.date_of_membership
        self.detail.data = member.detail


class AddShareForm(CustomFlaskForm):
    share_order_of_member = IntegerField(
        label="Hisse no:",
        render_kw={"disabled": ""},
    )

    date_of_opening = DateField(
        label="Hisse açılış tarihi:",
        validators=[
            input_required_validator("Hisse açılış tarihi"),
        ],
        default=datetime.today()
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='Hisse ekleme formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)


class SendSmsForm(CustomFlaskForm):
    sms_type = SelectField(
        label="Sms türü:",
        validators=[
            input_required_validator("Sms türü:"),
        ],
        choices=[("", "Sms türünü seçiniz...")],
        coerce=str,
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, form_title='Hisse ekleme formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.sms_type.choices += list(SmsPackage.TYPE.strings.items())