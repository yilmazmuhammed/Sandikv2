from datetime import datetime

from wtforms import StringField, IntegerField, TextAreaField, SubmitField, SelectField, BooleanField, EmailField, \
    DateField, DecimalField
from wtforms.validators import NumberRange, Optional, Email, ValidationError

from sandik.auth import db as auth_db
from sandik.sandik import db, utils
from sandik.sandik.exceptions import InvalidRuleVariable, InvalidRuleCharacter, RuleOperatorCountException, \
    NoValidRuleFound
from sandik.utils import sandik_preferences
from sandik.utils.db_models import Sandik, SmsPackage, SandikRule
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
        self.type.choices += [(str(value), text) for value, text in Sandik.TYPE.strings.items()]


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
        default=datetime.today
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
        self.web_user.choices += auth_db.web_users_form_choices(exclusions=sandik.members_set.web_user_ref,
                                                                only_active_user=True)
        try:
            max_share = sandik_preferences.get_max_number_of_share(sandik=sandik)
            self.number_of_share.validators.append(
                NumberRange(message=f"Hisse sayısı {max_share}'dan fazla olamaz", max=max_share)
            )
        except NoValidRuleFound:
            pass


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
        default=datetime.today
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


"""
########################################################################################################################
#############################################  Sandık kuralları formları   #############################################
########################################################################################################################
"""


class SandikRuleFormulaValidator:
    def __init__(self, formula_type, message=None):
        self.message = message or "Sandık formülü geçerli değil!"
        self.formula_type = formula_type
        self.variable_list = SandikRule.FORMULA_VARIABLE.strings.keys()
        self.comparison_operators = list(SandikRule.COMPARISON_OPERATOR.strings.keys())
        self.arithmetic_operators = list(SandikRule.ARITHMETIC_OPERATOR.strings.keys())

    def __call__(self, form, field):
        try:
            utils.rule_formula_validator(formula_string=field.data, variables=self.variable_list,
                                         operators=self.comparison_operators + self.arithmetic_operators,
                                         formula_type=self.formula_type)
        except RuleOperatorCountException as e:
            raise ValidationError(str(e))
        except InvalidRuleVariable as variable_name:
            raise ValidationError(f"{self.message}: {variable_name} geçerli bir değişken değil")
        except InvalidRuleCharacter as character_index:
            raise ValidationError(f"{self.message} "
                                  f"<br>- Formül matematik işaretleri, karşılaştırma işaretleri, karamlar ve "
                                  f"değişkenler dışında başka bir karakter içeremez."
                                  f"<br>Matematiksel işaretler: {self.arithmetic_operators}"
                                  f"<br>Karşılaştırma işaretleri: {self.comparison_operators}"
                                  f"<br>Geçerli değişkenler: {self.variable_list}"
                                  f"<br>Hata {character_index}. karakterde tespit edildi.")


class SandikRuleForm(CustomFlaskForm):
    type = SelectField(
        label="Kural türü:",
        validators=[
            input_required_validator("Kural türü:"),
        ],
        choices=[("", "Kural türünü seçiniz...")],
        coerce=str,
    )

    condition_formula = StringField(
        "Koşul formülü",
        validators=[
            SandikRuleFormulaValidator(formula_type=SandikRule.FORMULA_TYPE.CONDITION),
        ],
        render_kw={"placeholder": "Koşul formülü"}
    )

    value_formula = StringField(
        "Değer formülü",
        validators=[
            input_required_validator("Değer formülü"),
            SandikRuleFormulaValidator(formula_type=SandikRule.FORMULA_TYPE.VALUE),
        ],
        render_kw={"placeholder": "Değer formülü"}
    )

    submit = SubmitField(label="Gönder")

    def __init__(self, form_title='Sandık kuralı ekleme formu', *args, **kwargs):
        super().__init__(form_title=form_title, *args, **kwargs)
        self.type.choices += list(SandikRule.TYPE.strings.items())


"""
########################################################################################################################
########################################################################################################################
########################################################################################################################
"""
