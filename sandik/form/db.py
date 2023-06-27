from datetime import datetime

from pony.orm import select, flush

from sandik.utils.db_models import Form, FormQuestion, FQ_Connection, FormQuestionOption, FormResponse, \
    FormQuestionAnswer, Log


def db_create_form(**kwargs) -> Form:
    form = Form(**kwargs, id_str="s")
    flush()
    return form


def get_form(**kwargs):
    return Form.get(**kwargs)


def db_get_question(**kwargs) -> FormQuestion:
    return FormQuestion.get(**kwargs)


def db_get_option(**kwargs) -> FormQuestionOption:
    return FormQuestionOption.get(**kwargs)


def db_get_fq_connection_question(**kwargs) -> FQ_Connection:
    return FQ_Connection.get(**kwargs)


def db_add_question_to_form(form, questions_dict):
    if not isinstance(form, Form):
        form = get_form(id=form)

    first_question_order = select(fqc.question_order for fqc in form.fq_connections_set).max()
    first_question_order = first_question_order + 1 if first_question_order else 0
    old_question_fqc_list = [i for i in form.fq_connections_set]
    print(old_question_fqc_list)
    for key, question_info in questions_dict.items():
        if "fq_id_" in key:
            fqc_id = int(key[len("fq_id_"):])
            fq_connection = db_get_fq_connection_question(id=fqc_id)
            old_question_fqc_list.remove(fq_connection)
            print(old_question_fqc_list)
            question = fq_connection.form_question_ref
            options_info = question_info.pop("options", [])
            question_order = question_info.pop("order", 99)
            is_required = question_info.pop("is_required", None)
            is_unique = question_info.pop("is_unique", None)
            q_type = question_info.pop("type", None)
            text = question_info.pop("text", None)
            question.set(type=q_type, text=text)
            fq_connection.set(question_order=question_order, is_required=is_required, is_unique=is_unique, text=text)

            first_option_order = select(o.order for o in question.options_set).max()
            first_option_order = first_option_order + 1 if first_option_order else 0
            old_options = [i for i in question.options_set]
            for option_info in options_info:
                if "id" in option_info['order']:
                    option = db_get_option(id=option_info['order'][2:])
                    old_options.remove(option)
                    option.set(text=option_info["text"])
                else:
                    option_order = first_option_order + int(option_info.pop('order', 0))
                    option = create_form_question_option(question_ref=question, order=option_order, **option_info)
            for o in old_options:
                o.delete()
            print(question)
        else:
            options_info = question_info.pop("options", [])
            question_order = int(question_info.pop("order", None))
            is_required = question_info.pop("is_required", None)
            is_unique = question_info.pop("is_unique", None)
            q_type = question_info.pop("type", None)
            text = question_info.pop("text", None)
            question = create_form_question(type=q_type, text=text)
            for option_info in options_info:
                option = create_form_question_option(question_ref=question, **option_info)
            fqc = FQ_Connection(question_order=first_question_order + question_order, form_ref=form,
                                form_question_ref=question, is_unique=is_unique, is_required=is_required, text=text)

    for fqc in old_question_fqc_list:
        if not fqc.form_question_ref.is_public:
            fqc.form_question_ref.delete()
        fqc.delete()
    return form


def db_get_forms():
    return Form.select().order_by(lambda f: f.id)


def get_active_forms():
    return Form.select(
        lambda f: f.is_active and not (f.is_timed and f.end_time and f.end_time < datetime.now()) and not (
                f.is_timed and f.start_time and f.start_time > datetime.now()))


def db_add_form_response(form, response_dict) -> FormResponse:
    logs = [Log(type=Log.TYPE.CREATE)]
    form_response = FormResponse(form_ref=form, logs_set=logs)
    for fqc_key, answer_value in response_dict.items():
        if fqc_key[-6:] == "-other":
            continue
        fqc_id = int(fqc_key[len("fqc_"):])
        fq_connection = FQ_Connection.get(id=fqc_id)
        answer = FormQuestionAnswer(fq_connection_ref=fq_connection, form_response_ref=form_response)
        if fq_connection.form_question_ref.type in FormQuestion.TYPE.STRING_TYPES:
            answer.set(text=answer_value)
        elif fq_connection.form_question_ref.type in FormQuestion.TYPE.OPTION_TYPES:
            if answer_value == "0":
                answer.text = response_dict.get(fqc_key + "-other", "")
            elif isinstance(answer_value, list):
                for option_id in answer_value:
                    answer.selected_options_set.add(db_get_option(id=int(option_id)))
            else:
                answer.selected_options_set.add(db_get_option(id=int(answer_value)))
    return form_response


def get_form_question_answer(**kwargs) -> FormQuestionAnswer:
    return FormQuestionAnswer.get(**kwargs)


def do_not_unique_answer(response, type_str):
    response.logs_set.add(Log(type=Log.TYPE.FORM_RESPONSE.NOT_UNIQUE_ANSWER, type_str=type_str))


def do_multi_click_response(response):
    response.logs_set.add(Log(type=Log.TYPE.FORM_RESPONSE.MULTI_CLICK_RESPONSE))


def get_form_response(**kwargs) -> FormResponse:
    return FormResponse.get(**kwargs)


def create_fq_connection(**kwargs) -> FQ_Connection:
    return FQ_Connection(**kwargs)


def create_form_question(**kwargs) -> FormQuestion:
    return FormQuestion(**kwargs)


def create_form_question_option(**kwargs) -> FormQuestionOption:
    return FormQuestionOption(**kwargs)


def copy_form_question(old_question):
    question_values = old_question.to_dict(exclude=["id"])
    new_question = create_form_question(**question_values)
    if old_question.options_set.count() > 0:
        for fqo in old_question.options_set:
            fqo_values = fqo.to_dict(exclude=["id", "question_ref"])
            create_form_question_option(question_ref=new_question, **fqo_values)
    return new_question


def copy_form(form: Form) -> Form:
    form_values = form.to_dict(exclude=["id", "id_str"])
    log = Log(type=Log.TYPE.CREATE, details=f"Copy from Form #{form.id}")
    new_form = db_create_form(logs_set=[log], **form_values)

    # Copy questions
    for fqc in form.fq_connections_set:
        fqc_values = fqc.to_dict(exclude=["id", "form_question_ref", "form_ref"])
        if fqc.form_question_ref.is_public:
            create_fq_connection(**fqc_values, form_question_ref=fqc.form_question_ref, form_ref=new_form)
        else:
            new_question = copy_form_question(old_question=fqc.form_question_ref)
            create_fq_connection(**fqc_values, form_question_ref=new_question, form_ref=new_form)

    return new_form


def update_form(form: Form, **kwargs) -> Form:
    form.set(**kwargs)
    form.logs_set.add(Log(type=Log.TYPE.UPDATE, details=str(kwargs)))
    return form


def forms_form_choices():
    choices = [(f.id, f.name) for f in Form.select()]
    return choices


def delete_form_response(deleted_by, form_response) -> FormResponse:
    form_response.logs_set.add(Log(web_user_ref=deleted_by, type=Log.TYPE.DELETE))
    return form_response
