from flask import Blueprint, request, url_for, render_template, flash, g, abort
from flask_login import current_user
from werkzeug.utils import redirect

from sandik.auth.requirement import login_required, web_user_required
from sandik.sandik import forms, db, utils
from sandik.sandik.exceptions import TrustRelationshipAlreadyExist, TrustRelationshipCreationException, \
    MembershipApplicationAlreadyExist, WebUserIsAlreadyMember
from sandik.sandik.requirement import sandik_required, sandik_authorization_required, member_required, \
    trust_relationship_required
from sandik.transaction import db as transaction_db, utils as transaction_utils
from sandik.utils import LayoutPI, get_next_url, period as period_utils
from sandik.utils.forms import flask_form_to_dict, FormPI

sandik_page_bp = Blueprint(
    'sandik_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@sandik_page_bp.route("/olustur", methods=["GET", "POST"])
@login_required
def create_sandik_page():
    form = forms.SandikForm()

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form)
        sandik = db.create_sandik(created_by=current_user, **form_data)
        db.save()
        return redirect(url_for("sandik_page_bp.sandik_detail_page", sandik_id=sandik.id))

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Sandık oluştur", form=form, active_dropdown='sandik'))


@sandik_page_bp.route("/<int:sandik_id>/detay", methods=["GET", "POST"])
@login_required
@sandik_required
def sandik_detail_page(sandik_id):
    return render_template("sandik/sandik_detail_page.html",
                           page_info=LayoutPI(title="Sandık detayı", active_dropdown="sandik"))


@sandik_page_bp.route("/<int:sandik_id>/ozet", methods=["GET", "POST"])
@member_required
def sandik_summary_page(sandik_id):
    g.sum_of_unpaid_and_due_payments = transaction_utils.sum_of_unpaid_and_due_payments(whose=g.member)
    sum_of_future_and_unpaid_payments = transaction_utils.sum_of_future_and_unpaid_payments(whose=g.member)
    g.sum_of_payments = g.sum_of_unpaid_and_due_payments + sum_of_future_and_unpaid_payments
    g.trusted_links = {
        "total_paid_contributions": transaction_db.total_paid_contributions_of_trusted_links(member=g.member),
        "total_loaned_amount": transaction_db.total_loaned_amount_of_trusted_links(member=g.member),
        "total_balance": transaction_db.total_balance_of_trusted_links(member=g.member),
        "total_paid_installments": transaction_db.total_paid_installments_of_trusted_links(member=g.member)
    }
    g.my_upcoming_payments = transaction_utils.get_payments(
        whose=g.member,
        is_fully_paid=False,
        periods=[period_utils.current_period(),
                 period_utils.get_last_period(start_period=period_utils.current_period(), period_count=2)])
    return render_template("sandik/sandik_summary_page.html",
                           page_info=LayoutPI(title=g.sandik.name, active_dropdown="sandik"))


@sandik_page_bp.route("/<int:sandik_id>/index", methods=["GET", "POST"])
@login_required
@sandik_required
def sandik_index_page(sandik_id):
    member = db.get_member(sandik_ref=g.sandik, web_user_ref=current_user)
    if member:
        return redirect(url_for("sandik_page_bp.sandik_summary_page", sandik_id=sandik_id))
    else:
        return redirect(url_for("sandik_page_bp.sandik_detail_page", sandik_id=sandik_id))


@sandik_page_bp.route("/<int:sandik_id>/güven-halkam", methods=["GET", "POST"])
@member_required
def trust_links_page(sandik_id):
    return render_template("sandik/trust_links_page.html",
                           page_info=LayoutPI(title="Güven halkam", active_dropdown="sandik"))


@sandik_page_bp.route("/<int:sandik_id>/güven-bagi-istegi", methods=["GET", "POST"])
@member_required
def request_trust_link_page(sandik_id):
    form = forms.SelectMemberForm(sandik=g.sandik)

    if form.validate_on_submit():
        selected_member = db.get_member(id=form.member.data)
        try:
            trust_relationship = db.create_trust_relationship(requester_member=g.member,
                                                              receiver_member=selected_member,
                                                              requested_by=current_user)
            utils.send_notification_for_trust_relationship(trust_relationship=trust_relationship)
            next_url = get_next_url(request.args,
                                    default_url=url_for("sandik_page_bp.trust_links_page", sandik_id=sandik_id))
            return redirect(next_url)
        except TrustRelationshipAlreadyExist:
            flash("Bu üyeyle zaten aranızda bekleyen veya onaylanmış bir güven bağı var.", "warning")
        except TrustRelationshipCreationException as e:
            flash(str(e), "warning")

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Güven bağı isteği", form=form, active_dropdown='sandik'))


@sandik_page_bp.route("/guven-bagi-istegini-onayla/<int:trust_relationship_id>")
@login_required
@trust_relationship_required
def accept_trust_relationship_request_page(trust_relationship_id):
    print(current_user)
    print([g.trust_relationship.receiver_member_ref.web_user_ref,
                            g.trust_relationship.requester_member_ref.web_user_ref])
    if g.trust_relationship.receiver_member_ref.web_user_ref != current_user:
        abort(403)

    db.accept_trust_relationship_request(trust_relationship=g.trust_relationship, confirmed_by=current_user)
    return redirect(request.referrer)


@sandik_page_bp.route("/guven-bagi-istegini-reddet/<int:trust_relationship_id>")
@trust_relationship_required
def reject_trust_relationship_request_page(trust_relationship_id):
    if current_user not in [g.trust_relationship.receiver_member_ref.web_user_ref,
                            g.trust_relationship.requester_member_ref.web_user_ref]:
        abort(403)

    db.reject_trust_relationship_request(trust_relationship=g.trust_relationship, rejected_by=current_user)
    return redirect(request.referrer)


@sandik_page_bp.route("/uyelik-basvurusu", methods=["GET", "POST"])
@login_required
def apply_for_membership_page():
    if not current_user.get_primary_bank_account():
        flash("Üyelik başvurusu yapmadan önce birincil banka hesabı oluşturmalısınız'", "danger")
        return redirect(url_for("general_page_bp.create_bank_account_page", next=request.url))

    form = forms.SelectSandikForm(form_title="Sandık başvurusu")
    if form.validate_on_submit():
        sandik = db.get_sandik(id=form.sandik.data)
        try:
            db.apply_for_membership(sandik=sandik, applied_by=current_user)
            utils.Notification.MembershipApplication.send_apply_notification(sandik=sandik, applied_by=current_user)
            next_url = get_next_url(request.args, default_url=url_for("general_page_bp.index_page"))
            return redirect(next_url)
        except MembershipApplicationAlreadyExist:
            flash("Bu sandıkta zaten onaylanmamış üyelik başvurunuz bulunmakta.", "danger")
        except WebUserIsAlreadyMember:
            flash("Bu sandığa zaten üyesiniz.", "danger")

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Üyelik başvurusu yap", form=form, active_dropdown='sandik'))


@sandik_page_bp.route("/<int:sandik_id>/basvuru-onayla/<int:web_user_id>")
@sandik_authorization_required(permission="write")
@web_user_required
def confirm_membership_application_page(sandik_id, web_user_id):
    try:
        utils.confirm_membership_application(sandik=g.sandik, web_user=g.web_user, confirmed_by=current_user)
        utils.Notification.MembershipApplication.send_confirming_notification(sandik=g.sandik, web_user=g.web_user)
    except WebUserIsAlreadyMember:
        flash("Kullanıcı zaten bu sandığın üyesi.", "danger")

    return redirect(request.referrer)


@sandik_page_bp.route("/<int:sandik_id>/basvuru-reddet/<int:web_user_id>")
@sandik_authorization_required(permission="write")
@web_user_required
def reject_membership_application_page(sandik_id, web_user_id):
    db.reject_membership_application(sandik=g.sandik, web_user=g.web_user, rejected_by=current_user)
    return redirect(request.referrer)


@sandik_page_bp.route("/<int:sandik_id>/uyeler")
@sandik_authorization_required(permission="read")
def members_of_sandik_page(sandik_id):
    return render_template("sandik/members_of_sandik_page.html",
                           page_info=LayoutPI(title="Üyeler", active_dropdown="members"))


@sandik_page_bp.route("/<int:sandik_id>/uyelik-basvurulari")
@sandik_authorization_required(permission="read")
def membership_applications_to_sandik_page(sandik_id):
    return render_template("sandik/membership_applications_to_sandik_page.html",
                           page_info=LayoutPI(title="Üyelik başvuruları", active_dropdown="members"))
