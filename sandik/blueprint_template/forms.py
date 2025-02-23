from wtforms import SubmitField

from dirilis_yonetim.utils.forms import CustomFlaskForm


class ExampleForm(CustomFlaskForm):
    submit = SubmitField(label="Kaydet")

    def __init__(self, form_title='Example form', *args, **kwargs):
        super().__init__(
            form_title=form_title,
            f_class="form-horizontal",
            *args, **kwargs
        )
