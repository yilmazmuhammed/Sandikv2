from json.decoder import JSONDecodeError

from flask import json
from flask_wtf import FlaskForm
from werkzeug.datastructures import MultiDict
from wtforms import SelectMultipleField, widgets, ValidationError
from wtforms.validators import InputRequired, Length, NumberRange

try:
    import phonenumbers
except ImportError:
    phonenumbers = None

from sandik.utils import LayoutPI


class FormPI(LayoutPI):
    def __init__(self, form, explanation=None, errors: list = None, is_open=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not isinstance(errors, list):
            errors = []
        self.form = form
        self.explanation = explanation
        self.errors = errors
        self.is_open = is_open
        if form:
            for field in form:
                self.errors += field.errors


def form_open(form_name, f_id=None, enctype=None, f_action="", f_class="form-horizontal"):
    f_open = """<form action="%s" method="post" name="%s" """ % (f_action, form_name,)

    if f_id:
        f_open += """ id="%s" """ % (f_id,)
    if enctype:
        f_open += """ enctype="%s" """ % (enctype,)

    f_open += """class="%s">""" % (f_class,)

    return f_open


def form_close():
    return """</form>"""


class CustomFlaskForm(FlaskForm):
    def __init__(self, form_title='Form', form_name='form', form_id='form', f_class="form-horizontal", f_action="",
                 form_explanation=None, enctype=None, is_file_form=False, *args, **kwargs):
        self.form_title = form_title
        self.form_explanation = form_explanation
        if not enctype and is_file_form:
            enctype = "multipart/form-data"
        self.open = form_open(form_name=form_name, f_id=form_id, f_class=f_class, enctype=enctype, f_action=f_action)
        self.close = form_close()
        super().__init__(*args, **kwargs)

    def get_all_errors(self):
        errors = []
        for field in self:
            errors += field.errors
        return errors


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def custom_json_loads(string):
    lines = string.split("\r\n")
    ret = {}
    for line in lines:
        key, value = line.split(":")
        if len(value.split(",")) > 1:
            ret[key] = [v.strip() for v in value.split(",")]
        else:
            ret[key] = value.strip()
    return ret


def flask_form_to_dict(request_form: MultiDict, exclude=None, boolean_fields=None, default_values=None,
                       json_fields=None, json_loads=custom_json_loads):
    if default_values is None:
        default_values = {}
    if json_fields is None:
        json_fields = []
    if boolean_fields is None:
        boolean_fields = []
    if exclude is None:
        exclude = []
    exclude += ["submit", "csrf_token"]

    result = {
        key: request_form.getlist(key)[0] if len(request_form.getlist(key)) == 1 else request_form.getlist(key)
        for key in request_form
        if key not in exclude and not (len(request_form.getlist(key)) == 1 and request_form.getlist(key)[0] == "")
    }

    default_values.update(result)
    result = default_values

    for i in boolean_fields:
        if result.get(i):
            result[i] = True
        else:
            result[i] = False

    for i in json_fields:
        if result.get(i):
            try:
                result[i] = json.loads(result[i])
            except JSONDecodeError as e:
                print(type(e), "::", str(e))
                result[i] = json_loads(result[i])

    return result


class PhoneNumberValidator(object):
    """
    Validates an phone number. Requires phonenumbers package to be
    installed. For ex: pip install phonenumbers.

    :param message:
        Error message to raise in case of a validation error.
    :param default_codes:
        Uluslararası formatta doğrulanamazsa sırasıyla default_codes
        içindeki ülke kodları girdinin başına eklenerek kontrol edilir.
        (Default None)
    :param granular_message:
        Use validation failed message from email_validator library
        (Default False).
    """

    def __init__(self, message=None, default_codes=None, granular_message=False, ):
        if phonenumbers is None:
            raise Exception("Install 'phonenumbers' for phone number validation support.")
        if default_codes is None:
            default_codes = []
        self.default_codes = default_codes
        if not message:
            message = u'Telefon numaranızı başında "+" olarak uluslar arası telefon numarası formatında giriniz.'
        self.message = message

    def __call__(self, form, field):
        # if len(field.data) > 16:
        #     raise ValidationError(self.message+"\nTelefon numarası 16 karakterden uzun olamaz.")

        trials = [field.data, "+" + field.data] + [code + field.data for code in self.default_codes]
        print(trials)
        for trial in trials:
            try:
                phone_number = phonenumbers.parse(trial)
                if phonenumbers.is_valid_number(phone_number):
                    # TODO field.data = "+" + phone_number.country_code + phone_number.national_number
                    print("Geçerli:", phone_number)
                    print(phone_number.country_code, phone_number.national_number)
                    break
                else:
                    raise ValidationError(self.message, "\nTelefon numarası geçerli değil")
            except phonenumbers.phonenumberutil.NumberParseException as e:
                print("Doğrulanamıyor:", trial)
                print(e)
                pass
        else:
            raise ValidationError(self.message, "\nTelefon numarası doğrulanamıyor.")


class IbanValidator(object):
    def __init__(self, message=None):
        self.message = message or "IBAN'ınızı başına 'TR' koymadan 24 haneli olarak şekilde giriniz."

    def __call__(self, form, field):
        data = field.data.replace(' ', '')
        if len(data) != 24:
            raise ValidationError(self.message)

        try:
            int(data)
        except ValueError:
            raise ValidationError(self.message)


def input_required_validator(field):
    return InputRequired("Lütfen %s giriniz" % (field.lower(),))


def max_length_validator(field, max: int):
    return Length(max=max, message="%s %s karakterden fazla olamaz." % (field.capitalize(), max))


def min_length_validator(field, min: int):
    return Length(min=min, message="%s %s karakterden az olamaz." % (field.capitalize(), min))


def min_number_validator(field, min: int):
    return NumberRange(min=min, message="%s cannot be smaller than %s" % (field.capitalize(), min))
