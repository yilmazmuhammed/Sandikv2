from flask import Blueprint, jsonify, request

from sandik.sandik import db as sandik_db
from sandik.sandik.requirement import sandik_authorization_required

transaction_api_bp = Blueprint('transaction_api_bp', __name__)


@transaction_api_bp.route('odenmemis-borclar')
@sandik_authorization_required("read")
def get_unpaid_debts_of_member_api(sandik_id):
    if not request.args.get("member"):
        return jsonify(result=False, msg="'member' parametresi ile member_id'nin gonderilmesi gerekmektedir.")

    member = sandik_db.get_member(id=request.args.get("member"))
    if not member:
        return jsonify(result=False, msg="Üye bulunamadı")

    debts = [debt.to_extended_dict() for debt in member.get_unpaid_debts()]
    print(debts)
    return jsonify(result=True, member_id=member.id, debts=debts)
