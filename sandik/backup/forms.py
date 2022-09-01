from flask_wtf.file import FileField, FileAllowed
from wtforms import SubmitField
from wtforms.validators import InputRequired

from sandik.utils.forms import CustomFlaskForm


class RestoreBackupForm(CustomFlaskForm):

    backup_file = FileField(
        "Yedek dosyası (json):",
        validators=[
            InputRequired("Lütfen \"json\" formatındaki yedek dosyasını yükleyiniz"),
            FileAllowed(['json'], 'Sadece json formatı kabul edilmektedir')
        ],
        render_kw={"class": "form-control"}
    )

    submit = SubmitField(label="Yedeği yükle")

    def __init__(self, form_title='Yedekten geri yükleme', *args, **kwargs):
        super().__init__(form_title=form_title, is_file_form=True, *args, **kwargs)
