import os
from datetime import datetime

from flask import Blueprint, jsonify

from sandik.auth.requirement import admin_required

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
