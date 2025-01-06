from flask import Blueprint, request, render_template, g, redirect, url_for

from sandik.blueprint_template import forms
from sandik.utils import LayoutPI
from sandik.utils.forms import flask_form_to_dict, FormPI

blueprint_template_page_bp = Blueprint(
    'blueprint_template_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@blueprint_template_page_bp.route('/example')
def example_page():
    # # Example for http://127.0.0.1:5000/blueprint_template/example?arg0=55&arg1=asd&arg1=qwe
    print("request.args:\t", request.args, "\n")
    for i in request.args:
        print("arg:\t\t", i)
        print("get:\t\t", request.args.get(i))
        print("getlist:\t", request.args.getlist(i))
        print()
    g.arg0 = request.args.get('arg0')
    g.args = request.args
    return render_template("blueprint_template/example_page.html", page_info=LayoutPI(title="Page title"))


@blueprint_template_page_bp.route('/example_form')
def example_form_page():
    form = forms.ExampleForm(form_title="Example form")

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, exclude=[], boolean_fields=[])
        g.args = form_data
        return redirect(url_for("blueprint_template_page_bp.example_form_page"))
    return render_template("utils/form_layout.html", page_info=FormPI(title="Form page title", form=form))
