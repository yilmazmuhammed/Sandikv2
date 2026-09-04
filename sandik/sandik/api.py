from flask import Blueprint, jsonify, request, abort, g

from sandik.sandik import db
from sandik.sandik.requirement import sandik_authorization_required
from sandik.transaction import utils

sandik_api_bp = Blueprint('sandik_api_bp', __name__)


@sandik_api_bp.route('<int:sandik_id>/uye-finansal-durumu')
@sandik_authorization_required("read")
def member_financial_status_api(sandik_id):
    if not request.args.get("member"):
        return jsonify(result=False, msg="'member' parametresi ile member_id'nin gonderilmesi gerekmektedir.")

    member = db.get_member(id=request.args.get("member"), sandik_ref=g.sandik)
    if not member:
        return jsonify(result=False, msg="Üye bulunamadı")

    return jsonify(result=True, member_id=member.id,
                   sum_of_unpaid_and_due_payments=utils.sum_of_unpaid_and_due_payments(whose=member),
                   sum_of_future_and_unpaid_payments=utils.sum_of_future_and_unpaid_payments(whose=member),
                   undistributed_amount=member.total_of_undistributed_amount(),
                   max_amount_can_borrow=member.max_amount_can_borrow(),
                   # Para girişi formu, artan para sorusunu soracak mı buna bakarak karar verir.
                   remaining_money_action=member.get_remaining_money_action())


@sandik_api_bp.route('<int:sandik_id>/uye-hisseleri')
@sandik_authorization_required("read")
def get_shares_of_member_api(sandik_id):
    if not request.args.get("member"):
        return jsonify(result=False, msg="'member' parametresi ile member_id'nin gonderilmesi gerekmektedir.")

    member = db.get_member(id=request.args.get("member"), sandik_ref=g.sandik)
    if not member:
        return jsonify(result=False, msg="Üye bulunamadı")

    shares = [share.to_dict() for share in member.get_active_shares().order_by(lambda s: s.share_order_of_member)]
    return jsonify(result=True, member_id=member.id, shares=shares)
