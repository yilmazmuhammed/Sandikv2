import os

from flask import Blueprint, jsonify, request

from sandik.auth.requirement import admin_required
from sandik.paw import utils

paw_api_bp = Blueprint('paw_api_bp', __name__)


@paw_api_bp.route('/kaynak-kodu-guncelle')
@admin_required
def update_source_code_api():
    ret = utils.git_pull()
    return jsonify(result=True, msg=ret)


@paw_api_bp.route('/web-uygulamasini-bastan-baslat')
@admin_required
def reload_webapp_api():
    domain = request.host
    api_token = os.getenv("API_TOKEN")  # pythonanywhere sunucusunun varsayılan ortam değişkenlerinden gelmektedir
    username = os.getenv("USER")  # pythonanywhere sunucusunun varsayılan ortam değişkenlerinden gelmektedir

    if username is None:
        return jsonify(result=False, msg="PythonAnyWhere kullanıcısı için 'USER' çevresel değişkeni bulunamadı")
    if api_token is None:
        return jsonify(result=False, msg="PythonAnyWhere uygulaması için 'API_TOKEN' çevresel değişkeni bulunamadı")

    paw_api = utils.PythonAnywhereApi(token=api_token, username=username, domain=domain)
    response = paw_api.webapp_reload()

    print(response.content)
    if response.status_code == 200:
        return jsonify(result=True, msg=response.content)
    else:
        return jsonify(result=False, msg=f"status_code: {response.status_code}", response_content=response.content)
