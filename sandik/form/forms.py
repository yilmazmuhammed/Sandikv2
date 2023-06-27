from wtforms import SubmitField, StringField, SelectField, BooleanField, TextAreaField, RadioField, PasswordField, \
    DateField, TimeField, EmailField, TelField, IntegerField
from wtforms.validators import InputRequired, Length, Optional, Email

from sandik.auth import db as auth_db
from sandik.form import db
from sandik.utils.db_models import Form as DbForm, FormQuestion, Form
from sandik.utils.forms import CustomFlaskForm, PhoneNumberValidator, ContentField, ImageField, \
    input_required_validator, MultiCheckboxField, max_length_validator, min_number_validator


class FormForm(CustomFlaskForm):
    name = StringField(
        "Form ismi",
        validators=[
            InputRequired("Lütfen form ismini giriniz"),
            Length(max=100, message="Form ismi 100 karakterden fazla olamaz.")
        ],
        id='name', render_kw={"placeholder": "Form ismi"}
    )

    type = SelectField(
        "Form tipi",
        validators=[
            InputRequired("Lütfen form tipini seçiniz")
        ],
        coerce=int,
        choices=[
            (DbForm.TYPE.OTHER, "Diğer",),
            (DbForm.TYPE.MEMBERSHIP_APPLICATION, "Kayıt formu",)
        ]
    )

    is_active = BooleanField(
        label="Cevap alımına açık mı",
        id='is_active',
        default=True
    )

    # is_timed = BooleanField(
    #     label="Zamana bağlı mı",
    #     id='is_timed',
    #     default=False
    # )

    start_date = DateField(
        "Başlangıç tarihi",
        validators=[
            Optional()
        ],
        id="start_date"
    )

    start_time = TimeField(
        "Başlangıç saati",
        validators=[
            Optional()
        ],
        id="start_time"
    )

    end_date = DateField(
        "Bitiş tarihi",
        validators=[
            Optional()
        ],
        id="end_date"
    )

    end_time = TimeField(
        "Bitiş saati",
        validators=[
            Optional()
        ],
        id="end_time"
    )

    completed_message = StringField(
        "Tamamlandı mesajı",
        validators=[
            Optional(),
            max_length_validator(field="Tamamlandı mesajı", max=1000),
        ],
        render_kw={"placeholder": "Tamamlandı mesajı"}
    )

    image_url = StringField(
        "Resim url'si",
        validators=[
            Optional(),
        ],
        render_kw={"placeholder": "www.images.com/image.jpg"}
    )

    submit = SubmitField(label="Kaydet")

    def fill_from_form(self, form: DbForm):
        self.name.data = form.name
        self.type.data = form.type
        self.is_active.data = form.is_active
        # self.is_timed.data = form.is_timed
        if form.start_time:
            self.start_date.data = form.start_time.date()
            self.start_time.data = form.start_time.time()
        if form.end_time:
            self.end_date.data = form.end_time.date()
            self.end_time.data = form.end_time.time()
        self.completed_message.data = form.completed_message
        self.image_url.data = form.image_url


class FormCapacityForm(CustomFlaskForm):
    responses_capacity = IntegerField(
        label="Yanıt sınırı:",
        validators=[
            input_required_validator("Yanıt sınırı"),
            min_number_validator("Yanıt sınırı", 0),
        ],
        render_kw={"placeholder": "Sınırı kaldırmak için '0' giriniz."},
    )

    overcapacity_message = StringField(
        "Yanıt sınırı aşım mesajı",
        validators=[
            Optional(),
            max_length_validator(field="Yanıt sınırı aşım mesajı", max=1000),
        ],
        render_kw={"placeholder": "Yanıt sınırı aşım mesajı"}
    )

    submit = SubmitField(label="Kaydet")

    def fill_from_form(self, form: DbForm):
        self.overcapacity_message.data = form.overcapacity_message
        self.responses_capacity.data = form.responses_capacity


class FormQuestionsForm(CustomFlaskForm):
    submit = SubmitField(label="Kaydet")


class DynamicForm(CustomFlaskForm):

    @staticmethod
    def prepare(form):
        for name in dir(DynamicForm):
            if not name.startswith('_'):
                unbound_field = getattr(DynamicForm, name)
                if hasattr(unbound_field, '_formfield'):
                    delattr(DynamicForm, name)
        for fqc in form.fq_connections_set.order_by(lambda fqc_: fqc_.question_order):
            q: FormQuestion = fqc.form_question_ref
            QuestionField = None
            validators = []
            optional_kwargs = {}
            if q.type == FormQuestion.TYPE.SHORT_ANSWER:
                QuestionField = StringField
            elif q.type == FormQuestion.TYPE.LONG_ANSWER:
                QuestionField = TextAreaField
            elif q.type == FormQuestion.TYPE.MULTIPLE_CHOICES:
                QuestionField = RadioField
            elif q.type == FormQuestion.TYPE.CHECKBOX:
                QuestionField = MultiCheckboxField
            elif q.type == FormQuestion.TYPE.SCORING:
                QuestionField = RadioField
            elif q.type == FormQuestion.TYPE.DATE:
                QuestionField = DateField
            elif q.type == FormQuestion.TYPE.TIME:
                QuestionField = TimeField
            elif q.type == FormQuestion.TYPE.DATETIME:
                continue
            elif q.type == FormQuestion.TYPE.CONTENT:
                QuestionField = ContentField
                optional_kwargs["text"] = fqc.primary_text(text_type="html")
            elif q.type == FormQuestion.TYPE.EMAIL:
                QuestionField = EmailField
                validators.append(Email(message="Geçersiz mail adresi"))
            elif q.type == FormQuestion.TYPE.PHONE_NUMBER:
                QuestionField = TelField
                validators.append(PhoneNumberValidator(
                    message="Telefon numaranızı ülke kodunu seçerek, sayılar arasında boşluk olmadan giriniz."))
            elif q.type == FormQuestion.TYPE.DROPDOWN:
                QuestionField = SelectField
            elif q.type == FormQuestion.TYPE.IMAGE:
                QuestionField = ImageField
                optional_kwargs["url"] = fqc.primary_text()
            else:
                raise Exception("")

            if q.type in FormQuestion.TYPE.OPTION_TYPES:
                optional_kwargs["choices"] = [(o.id, o.text) for o in q.get_options().order_by(lambda o: o.order)]
                if q.has_other_option():
                    optional_kwargs["choices"] += [(0, "Diğer")]
                optional_kwargs["coerce"] = int

            if fqc.is_required:
                validators.append(InputRequired(message='Lütfen "%s" sorusunu cevaplayınız.' % (q.text,)))
            else:
                validators.append(Optional())

            q_id = 'fqc_' + str(fqc.id)
            question_field = QuestionField(
                label=fqc.primary_text(),
                validators=validators,
                id=q_id,
                render_kw={"placeholder": "Yanıtınız..."},
                **optional_kwargs,
            )
            setattr(DynamicForm, q_id, question_field)

        setattr(DynamicForm, "submit", SubmitField(label="Gönder"))


class ResponseEmailForm(CustomFlaskForm):
    subject = StringField(
        label="Mail konusu:",
        validators=[
            InputRequired("Mail konusu giriniz."),
        ],
        id='mail_subject', render_kw={"placeholder": "Mail konusu"}
    )

    content = TextAreaField(
        label="Mail içeriği (html):",
        validators=[
            InputRequired("Mail içeriği giriniz."),
        ],
        id='mail_content', render_kw={"placeholder": "Mail içeriği (html)"}
    )

    sender_display_name = StringField(
        label="Gönderenin görünecek ismi:",
        id='sender_display_name', render_kw={"placeholder": "Varsayılan için boş bırakınız."}
    )

    sender_email_address = EmailField(
        label="Gönderen eposta adresi:",
        validators=[
            Optional(),
            Email(message="Gönderen eposta adresi hatalı.")
        ],
        id='sender_email_address', render_kw={"placeholder": "Varsayılan için boş bırakınız."}
    )

    sender_password = PasswordField(
        label="Gönderen epostanın parolası:",
        validators=[
            Optional(),
        ],
        render_kw={"placeholder": "Varsayılan için boş bırakınız."}
    )

    sender_smtp_server = StringField(
        label="SMTP Server:",
        validators=[
            Optional(),
        ],
        id='sender_smtp_server', render_kw={"placeholder": "Varsayılan için boş bırakınız."}
    )

    fqc_ref = SelectField(
        "Eposta adresi hangi sorudan alınsın",
        validators=[
            InputRequired("Soruyu")
        ],
        coerce=int,
    )

    submit = SubmitField(label="Gönder")


class AddAuthoritativeForm(CustomFlaskForm):
    form = SelectField(
        label="Form:",
        choices=[(0, "Form seçiniz...")],
        coerce=int,
    )

    web_user = SelectField(
        label="Kullanıcı:",
        choices=[("", "Kullanıcı seçiniz...")],
        coerce=str,
    )

    management_department = SelectField(
        label="Birim:",
        choices=[("", "Birim seçiniz...")],
        coerce=str,
    )

    submit = SubmitField(label="Kaydet")

    def __init__(self, *args, **kwargs):
        super().__init__(form_title=kwargs.pop("form_title", "Yetkili ekleme formu"), *args, **kwargs)
        self.form.choices += db.forms_form_choices()
        self.web_user.choices += auth_db.web_users_form_choices()
        self.management_department.choices += management_department_db.management_departments_form_choices()
