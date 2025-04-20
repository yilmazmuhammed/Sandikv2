import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from sandik.auth.requirement import admin_required
from sandik.bot.email_bot import EmailBot

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


@general_api_bp.route('/contact-us', methods=["POST"])
def contact_us():
    data = request.get_json()

    email_bot = EmailBot(email_address=os.getenv("SANDIKv2_EMAIL_BOT_EMAIL_ADDRESS"),
                         password=os.getenv("SANDIKv2_EMAIL_BOT_PASSWORD"),
                         smtp_server=os.getenv("SANDIKv2_EMAIL_BOT_SMTP_SERVER"),
                         display_name=os.getenv("SANDIKv2_EMAIL_BOT_DISPLAY_NAME"))
    try:
        email_bot.connect_server()
        for address in [
            os.getenv("SANDIKv2_ADMIN_EMAIL_ADDRESS"),
            # data["email"]
        ]:
            msg = email_bot.create_email_message(to_addresses=address,
                                                 subject="Contact us",
                                                 message=f"Name: {data['name']}\n"
                                                         f"Email: {data['email']} "
                                                         f"Message: {data['message']}")
            email_bot.send_email(to_addresses=address, msg=msg)
        email_bot.disconnect_server()
        return jsonify({"result": True})
    except Exception as e:
        return jsonify({"result": False, "msg": str(e)})
