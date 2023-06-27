from flask import url_for

from sandik.form import db
from sandik.sandik import db as sandik_db


def connect_args(form, args):
    if args.get("sandik"):
        form.sandiks_set.add(sandik_db.get_sandik(id=args.get("sandik")))


def prepare_questions_dict(form_dict):
    questions = {}
    for key in form_dict:
        key_parts = key.split("-")
        question_number = key_parts[1]
        data_type = key_parts[2]
        if not questions.get(question_number):
            questions[question_number] = {"is_required": False, "is_unique": False, "options": []}
        # print(key, form_dict[key])
        # print(data_type)
        if data_type == "is_required":
            questions[question_number][data_type] = True
        if data_type == "is_unique":
            questions[question_number][data_type] = True
        if data_type == "option":
            option_order = key_parts[3]
            questions[question_number]["options"].append({"text": form_dict[key], "order": option_order})
        else:
            questions[question_number][data_type] = form_dict[key]

    return questions


def not_unique_answer(response):
    for fqc in response.form_ref.fq_connections_set.filter(lambda fqc: fqc.is_unique):
        answer = db.get_form_question_answer(fq_connection_ref=fqc, form_response_ref=response)
        if answer:
            if fqc.form_question_ref.type in fqc.form_question_ref.TYPE.STRING_TYPES:
                if fqc.answers_set.filter(
                        lambda a: a.text == answer.text and a.form_response_ref.is_valid()).count() > 1:
                    db.do_not_unique_answer(response, answer.text)
                    return answer
            # elif fqc.form_question_ref.type == FormQuestion.TYPE.OPTION_TYPES:
            #     fqc.answers_set.filter(lambda a: a.)
    return None


# TODO Control multi click
def is_multi_click(response):
    if False:
        db.do_multi_click_response(response)
        return True
    return False


def responses_table_from_form(form, only_valid=True):
    footable = footable_from_form(form, only_valid=only_valid)
    cols = [col for col in footable["columns"] if col.get("visible", True)]
    table_rows = []
    # create header row
    table_rows.append([col["title"] for col in cols])
    # create rows
    for row in footable["rows"]:
        table_rows.append([row.get(col["name"]) for col in cols])
    return table_rows


def footable_from_form(form, only_valid=False):
    columns = [
        {"name": "index", "title": "#"},
        {"name": "time", "title": "Zaman"},
        {"name": "is_valid", "title": "Geçerlilik durumu", "visible": False},
        {"name": "fr_id", "title": "Response ID", "visible": False},
    ]
    for fqc in form.fq_connections_set.order_by("lambda fqc: fqc.question_order"):
        if fqc.form_question_ref.type not in fqc.form_question_ref.TYPE.CONTENT_TYPES:
            columns.append({"name": f"fqc_{fqc.id}", "title": fqc.text or fqc.form_question_ref.text})
    columns.append({"name": "actions", "title": "İşlemler", "breakpoints": "xs sm md lg xl", })

    valid_status = {
        "multi_click": "Ard arda gönderim",
        "is_not_unique": "Benzersiz sütunlar uymuyor",
        "not_created": "Oluşturulmamış",
        "valid": "Geçerli",
        "deleted": "Silinmiş",
    }

    rows = []
    valid_index = 0
    not_valid_index = 0
    deleted_index = 0
    if only_valid:
        responses = form.valid_responses()
    else:
        responses = form.form_responses_set

    for fr in responses.order_by("lambda fr: fr.id"):
        row = {"time": fr.get_creation_log().time.strftime("%d/%m/%Y, %H:%M:%S"), "fr_id": fr.id,
               "actions": f"""<tr><td><a class='btn btn-xs btn-danger dialog-confirm' confirm-message='Form yanıtı silinecek, emin misiniz?' title='Sil' href='{url_for("form_page_bp.delete_form_response_page", form_id=form.id, form_response_id=fr.id)}'><i class='fa fa-trash' aria-hidden=\"true\"></a></td></tr>"""}
        if fr.is_multi_click():
            not_valid_index += 1
            row["is_valid"] = valid_status["multi_click"]
            row["index"] = f"mc{not_valid_index}"
        elif not fr.is_unique():
            not_valid_index += 1
            row["is_valid"] = valid_status["is_not_unique"]
            row["index"] = f"nu{not_valid_index}"
        elif not fr.is_created():
            not_valid_index += 1
            row["is_valid"] = valid_status["not_created"]
            row["index"] = f"nc{not_valid_index}"
        elif fr.is_deleted():
            deleted_index += 1
            row["is_valid"] = valid_status["deleted"]
            row["index"] = f"d{deleted_index}"
        else:
            valid_index += 1
            row["is_valid"] = valid_status["valid"]
            row["index"] = valid_index
        for fqa in fr.answers_set.order_by("lambda fa: fa.fq_connection_ref.question_order"):
            row[f"fqc_{fqa.fq_connection_ref.id}"] = fqa.answer_str
        rows.append(row)
    return {"columns": columns, "rows": rows, "valid_status": valid_status}
