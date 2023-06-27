import json
from datetime import datetime

from flask import Blueprint, request, redirect, render_template, g, url_for, flash
from flask_login import current_user
from pony.orm import flush

from sandik.auth.requirement import admin_required
from sandik.form.requirement import form_required, form_response_required
from sandik.utils.db_models import Log
from sandik.form import db, forms
from sandik.form.db import db_create_form, db_add_question_to_form, db_get_forms, \
    db_add_form_response
from sandik.form.forms import FormForm, FormQuestionsForm, DynamicForm, FormCapacityForm
from sandik.form.utils import prepare_questions_dict, not_unique_answer, is_multi_click, footable_from_form, \
    connect_args
from sandik.utils import LayoutPI, db_models
from sandik.utils.forms import combine_date_and_time_from_form_data, FormPI, flask_form_to_dict

form_page_bp = Blueprint(
    'form_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@form_page_bp.route("/olustur", methods=["GET", "POST"])
@admin_required
def create_form_page():
    flask_form = FormForm()

    if flask_form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, boolean_fields=["is_active"])
        form_data = combine_date_and_time_from_form_data(form_data=form_data, field_names=["start", "end"])
        form_obj = db_create_form(**form_data)
        connect_args(form_obj, request.args)
        return redirect(url_for("form_page_bp.form_questions_page", form_id=form_obj.id))

    return render_template(
        "utils/form_layout.html", page_info=FormPI(title="Form oluştur", form=flask_form, active_dropdown='form')
    )


@form_page_bp.route("/<int:form_id>/guncelle", methods=["GET", "POST"])
@form_required
@admin_required
def update_form_page(form_id):
    db_form = db.get_form(id=form_id)
    flask_form = FormForm()

    if flask_form.validate_on_submit():
        default = {
            "name": "", "type": None, "is_active": None, "start_time": None, "end_time": None,
            "completed_message": ""
        }
        form_data = flask_form_to_dict(request_form=request.form,
                                       boolean_fields=["is_active"], default_values=default)
        form_data = combine_date_and_time_from_form_data(form_data=form_data, field_names=["start", "end"])
        form_obj = db.update_form(form=db_form, **form_data)
        return redirect(url_for("form_page_bp.form_detail_page", form_id=form_obj.id))

    if request.method == 'GET':
        flask_form.fill_from_form(db_form)

    return render_template(
        "utils/form_layout.html", page_info=FormPI(title="Formu güncelle", form=flask_form, active_dropdown='form')
    )


@form_page_bp.route("/<int:form_id>/yanit-kapasitesini-duzenle", methods=["GET", "POST"])
@form_required
@admin_required
def update_form_capacity_page(form_id):
    db_form = db.get_form(id=form_id)
    flask_form = FormCapacityForm()

    if flask_form.validate_on_submit():
        default_values = {"overcapacity_message": "Kontenjanımız dolmuştur. İlginiz için teşekkür ederiz."}
        form_data = flask_form_to_dict(request_form=request.form, default_values=default_values)
        form_obj = db.update_form(form=db_form, **form_data)
        return redirect(url_for("form_page_bp.form_detail_page", form_id=form_obj.id))

    if request.method == 'GET':
        flask_form.fill_from_form(db_form)

    return render_template(
        "utils/form_layout.html", page_info=FormPI(title="Formu güncelle", form=flask_form, active_dropdown='form')
    )


@form_page_bp.route("/<int:form_id>/sorular", methods=["GET", "POST"])
@form_required
@admin_required
def form_questions_page(form_id):
    import locale
    print(locale.getpreferredencoding())
    flask_form = FormQuestionsForm()
    print(ascii(request.form))
    print(request.form)
    if flask_form.validate_on_submit():
        form_dict = flask_form_to_dict(request_form=request.form)
        # print(form_dict)
        questions = prepare_questions_dict(form_dict)
        db_add_question_to_form(form=form_id, questions_dict=questions)
        return redirect(url_for("form_page_bp.form_detail_page", form_id=form_id))
    g.form = db.get_form(id=form_id)
    return render_template(
        "form/add_form_question_page.html", page_info=FormPI(title="Soru ekle", form=flask_form, active_dropdown='form')
    )


@form_page_bp.route("/listele")
@admin_required
def forms_page():
    g.forms = db_get_forms()
    return render_template("form/forms.html", page_info=LayoutPI(title="Formlar", active_dropdown='form'))


@form_page_bp.route("/<int:form_id>/detay")
@form_required
@admin_required
def form_detail_page(form_id):
    g.form = db.get_form(id=form_id)
    return render_template("form/form_detail.html", page_info=LayoutPI(title="Form detayı", active_dropdown="form"))


@form_page_bp.route("/<string:form_id_str>", methods=["GET", "POST"])
@form_page_bp.route("/<string:form_id_str>/embed", methods=["GET", "POST"])
def form_embed_page(form_id_str):
    form = db.get_form(id_str=form_id_str)
    # if not form.is_active_by_time():
    #     flash("Form cevap alımına kapalıdır. İlginiz için teşekkür ederiz.", "danger")
    #     return render_template("form/form_embed.html", page_info=FormPI(title=form.name, form=None, is_open=False))

    if form.is_capacity_full():
        flash(form.overcapacity_message, "info")
        return render_template("form/form_embed.html", page_info=FormPI(title=form.name, form=None, is_open=False))

    g.additional_fqcs = form.fq_connections_set.filter(
        lambda fqc: fqc.form_question_ref.type in [db_models.FormQuestion.TYPE.CONTENT])
    DynamicForm.prepare(form)
    flask_form = DynamicForm(form_title=form.name)
    errors = []
    if flask_form.validate_on_submit():
        response_dict = flask_form_to_dict(request_form=request.form)
        response = db_add_form_response(form, response_dict)
        if is_multi_click(response):
            return render_template("form/form_embed.html", page_info=LayoutPI(title=form.name))
        nua = not_unique_answer(response)
        g.margin_top = request.args.get("margin-top", 0)
        if nua:
            if (datetime.now() - Log.get_create_log(entity=nua.form_response_ref).time).seconds > 30:
                flash(f"Daha önce \"{nua.fq_connection_ref.text}\" sorusuna bu cevap verilmiş.", "danger")
            else:
                # TODO
                flash(f"Daha önce \"{nua.fq_connection_ref.text}\" sorusuna bu cevap verilmiş.", "danger")
                # flash("Yanıtınız kaydedilmiştir. Teşekkür ederiz.", "success")
            return render_template("form/form_embed.html",
                                   page_info=FormPI(title=form.name, form=flask_form, is_open=False))
        else:
            flash(form.completed_message or "Yanıtınız kaydedilmiştir. Teşekkür ederiz", "success")
            # return redirect(url_for("form_page_bp.form_embed_page", form_id_str=form_id_str))
            return render_template("form/form_embed.html",
                                   page_info=FormPI(title=form.name, form=flask_form, is_open=False))
    return render_template("form/form_embed.html", page_info=FormPI(title=form.name, form=flask_form, errors=errors))


@form_page_bp.route("/<int:form_id>/yanitlar")
@form_required
@admin_required
def form_responses_page(form_id):
    g.form = db.get_form(id=form_id)
    footable = footable_from_form(form=g.form)
    g.valid_status = json.dumps(footable["valid_status"])
    g.columns = json.dumps(footable["columns"])
    g.rows = json.dumps(footable["rows"])
    return render_template("form/form_responses_page.html",
                           page_info=LayoutPI(title=f"{g.form.name} - Form yanıtları", active_dropdown="form"))


@form_page_bp.route("/<int:form_id>/kopyala")
@form_required
@admin_required
def copy_form_page(form_id):
    old_form = db.get_form(id=form_id)
    new_form = db.copy_form(form=old_form)
    flush()
    # TODO redirect edit form info
    return redirect(url_for("form_page_bp.update_form_page", form_id=new_form.id))


@form_page_bp.route("/<int:form_id>/fr-<int:form_response_id>/sil")
@form_response_required
@admin_required
def delete_form_response_page(form_id, form_response_id):
    db.delete_form_response(deleted_by=current_user, form_response=g.form_response)
    return redirect(request.referrer)
