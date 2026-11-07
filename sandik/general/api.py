import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from sandik.auth import utils as auth_utils
from sandik.auth.requirement import admin_required
from sandik.general import utils

general_api_bp = Blueprint('general_api_bp', __name__)


@general_api_bp.route('/calisma-zamani')
@admin_required
def get_run_time_api():
    run_time = datetime.strptime(os.getenv("RUN_TIME"), os.getenv("DATETIME_STR_FORMAT"))
    elapsed_time = datetime.now() - run_time
    return jsonify(result=True, run_time=run_time,
                   elapsed_time={
                       "days": elapsed_time.days,
                       "hours": int(elapsed_time.seconds / (60 * 60)),
                       "minutes": int((elapsed_time.seconds % (60 * 60)) / 60),
                       "seconds": (elapsed_time.seconds % 60),
                       "total_seconds": elapsed_time.total_seconds()
                   })


@general_api_bp.route('/borc-gecmisi')
def debt_events_api():
    """Borç geçmişinin ham olayları; **oturumla değil kişisel API anahtarıyla** okunur (Cüzdan bağlantısı).

    Anahtar `Authorization: Bearer <anahtar>` başlığında gelir (`/cuzdan-baglantisi` sayfasında üretilir).
    Yalnızca okur; yanıt `no-store`dur.
    """
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    web_user = auth_utils.get_web_user_from_api_token(token)
    if not web_user:
        response = jsonify(result=False, msg="API anahtarı geçersiz ya da silinmiş.")
        response.status_code = 401
    else:
        response = jsonify(result=True, version=1, name=web_user.name_surname, **utils.get_debt_events(web_user))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response
