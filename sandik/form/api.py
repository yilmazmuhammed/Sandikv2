from flask import Blueprint, request
import flask_excel as excel

from sandik.form import db
from sandik.form.utils import responses_table_from_form

form_api_bp = Blueprint('form_api_bp', __name__)


@form_api_bp.route("/<int:form_id>/yanitlar/xls")
def download_form_responses_api(form_id):
    form = db.get_form(id=form_id)
    only_valid = bool(int(request.args.get("only_valid", 0)))
    file_format = request.args.get("file_format", "xlsx")
    footable = responses_table_from_form(form, only_valid=only_valid)
    try:
        return excel.make_response_from_array(footable, file_format, file_name=f"{form.name} Form Yanıtları")
    except Exception:
        return excel.make_response_from_array(footable, file_format, file_name=f"form_yanitlari_{form.id}")

