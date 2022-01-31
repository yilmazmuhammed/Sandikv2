from flask import Blueprint, jsonify, request, abort

from sandik.sandik import db
from sandik.sandik.requirement import sandik_authorization_required
from sandik.transaction import utils

sandik_api_bp = Blueprint('sandik_api_bp', __name__)


@sandik_api_bp.route('<int:sandik_id>/uye-finansal-durumu')
@sandik_authorization_required("read")
def member_financial_status_api(sandik_id):
    if not request.args.get("member"):
        return jsonify(result=False, msg="'member' parametresi ile member_id'nin gonderilmesi gerekmektedir.")
    member = db.get_member(id=request.args.get("member"))
    if not member:
        return jsonify(result=False, msg="Üye bulunamadı")
    return jsonify(result=True, member_id=member.id,
                   sum_of_unpaid_and_due_payments=utils.sum_of_unpaid_and_due_payments(whose=member),
                   sum_of_future_and_unpaid_payments=utils.sum_of_future_and_unpaid_payments(whose=member),
                   untreated_amount=utils.untreated_amount(member=member))
