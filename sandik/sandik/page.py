from flask import Blueprint, request, url_for, render_template, flash, g, abort
from flask_login import current_user
from werkzeug.utils import redirect

from sandik.auth import db as auth_db
from sandik.auth.exceptions import WebUserNotFound
from sandik.auth.requirement import login_required, web_user_required
from sandik.sandik import forms, db, utils
from sandik.sandik.exceptions import TrustRelationshipAlreadyExist, TrustRelationshipCreationException, \
    MembershipApplicationAlreadyExist, WebUserIsAlreadyMember, SandikAuthorityException, AddMemberException, \
    MembershipException, MaxShareCountExceed, NotActiveMemberException, ThereIsUnpaidDebtOfMemberException, \
    ThereIsUnpaidAmountOfLoanedException, NotActiveShareException, ThereIsUnpaidDebtOfShareException, NoValidRuleFound
from sandik.sandik.requirement import sandik_required, sandik_authorization_required, to_be_member_of_sandik_required, \
    trust_relationship_required, to_be_member_or_manager_of_sandik_required, sandik_type_required, sandik_rule_required
from sandik.utils import LayoutPI, get_next_url, sandik_preferences
from sandik.utils.db_models import Sandik

from sandik.utils.forms import flask_form_to_dict, FormPI

sandik_page_bp = Blueprint(
    'sandik_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)

"""
########################################################################################################################
###############################################  Temel sandık sayfaları  ###############################################
########################################################################################################################
"""


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


@sandik_page_bp.route("/<int:sandik_id>/detay")
@to_be_member_or_manager_of_sandik_required
def sandik_detail_page(sandik_id):
    return render_template("sandik/sandik_detail_page.html",
                           page_info=LayoutPI(title="Sandık detayı", active_dropdown="sandik"))


@sandik_page_bp.route("/<int:sandik_id>/ozet", methods=["GET", "POST"])
@to_be_member_of_sandik_required
def sandik_summary_for_member_page(sandik_id):
    g.summary_data = utils.get_member_summary_page(member=g.member)
    g.type = "member"
    return render_template("sandik/sandik_summary_for_member_page.html",
                           page_info=LayoutPI(title="Üye özeti", active_dropdown="sandik"))


@sandik_page_bp.route("/<int:sandik_id>/index", methods=["GET", "POST"])
@login_required
@sandik_required
def sandik_index_page(sandik_id):
    member = db.get_member(sandik_ref=g.sandik, web_user_ref=current_user)
    if member:
        return redirect(url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik_id))
    else:
        # TODO yönetici icin sandik ozeti sayfasi veya sandik detayi sayfasi
        return redirect(url_for("sandik_page_bp.sandik_detail_page", sandik_id=sandik_id))


@sandik_page_bp.route("/<int:sandik_id>/sandik-turunu-guncelle", methods=["GET", "POST"])
@sandik_authorization_required(permission="write")
def update_sandik_type_page(sandik_id):
    form = forms.SandikTypeForm()
    if form.validate_on_submit():
        if g.sandik.type != int(form.type.data):
            utils.update_sandik_type(sandik=g.sandik, sandik_type=int(form.type.data), updated_by=current_user)
        else:
            flash("Aynı sandık türü seçildiği için değişiklik yapılmadı.", "warning")

        return redirect(url_for("sandik_page_bp.update_sandik_type_page", sandik_id=sandik_id))

    if not form.is_submitted():
        form.type.data = str(g.sandik.type)

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Sandık türünü değiştir", form=form, active_dropdown='sandik'))


"""
########################################################################################################################
################################################  Güven bağı sayfaları  ################################################
########################################################################################################################
"""


@sandik_page_bp.route("/<int:sandik_id>/guven-halkam", methods=["GET", "POST"])
@sandik_type_required(sandik_type=Sandik.TYPE.WITH_TRUST_RELATIONSHIP)
@to_be_member_of_sandik_required
def trust_links_page(sandik_id):
    g.accepted_trust_links = sorted(g.member.accepted_trust_links(),
                                    key=lambda tr: tr.other_member(whose=current_user).web_user_ref.name_surname)
    return render_template("sandik/trust_links_page.html",
                           page_info=LayoutPI(title="Güven halkam", active_dropdown="sandik"))


@sandik_page_bp.route("/<int:sandik_id>/u-<int:member_id>/gb-gonder")
@sandik_type_required(sandik_type=Sandik.TYPE.WITH_TRUST_RELATIONSHIP)
@to_be_member_of_sandik_required
def send_request_trust_link_page(sandik_id, member_id):
    receiver_member = db.get_member(id=member_id, sandik_ref=g.sandik)
    if not receiver_member:
        abort(404, "Üye bulunamadı")

    try:
        trust_relationship = db.create_trust_relationship(requester_member=g.member, receiver_member=receiver_member,
                                                          created_by=current_user)
        utils.send_notification_for_trust_relationship(trust_relationship=trust_relationship)
    except TrustRelationshipAlreadyExist:
        flash("Bu üyeyle zaten aranızda bekleyen veya onaylanmış bir güven bağı var.", "warning")
    except TrustRelationshipCreationException as e:
        flash(str(e), "warning")

    return redirect(request.referrer or url_for("sandik_page_bp.trust_links_page", sandik_id=sandik_id))


@sandik_page_bp.route("/<int:sandik_id>/gb-<int:trust_relationship_id>/onayla")
@sandik_type_required(sandik_type=Sandik.TYPE.WITH_TRUST_RELATIONSHIP)
@to_be_member_of_sandik_required
@trust_relationship_required
def accept_trust_relationship_request_page(sandik_id, trust_relationship_id):
    if g.trust_relationship.receiver_member_ref.web_user_ref != current_user:
        abort(403)

    db.accept_trust_relationship_request(trust_relationship=g.trust_relationship, confirmed_by=current_user)
    return redirect(request.referrer)


@sandik_page_bp.route("/<int:sandik_id>/gb-<int:trust_relationship_id>/kaldir")
@sandik_type_required(sandik_type=Sandik.TYPE.WITH_TRUST_RELATIONSHIP)
@to_be_member_of_sandik_required
@trust_relationship_required
def remove_trust_relationship_request_page(sandik_id, trust_relationship_id):
    if current_user not in [g.trust_relationship.receiver_member_ref.web_user_ref,
                            g.trust_relationship.requester_member_ref.web_user_ref]:
        abort(403, "Başkasının güven bağını kaldıramazsınız")

    db.remove_trust_relationship_request(trust_relationship=g.trust_relationship, rejected_by=current_user)
    return redirect(request.referrer)


"""
########################################################################################################################
##############################################  Sandık üyeliği sayfaları  ##############################################
########################################################################################################################
"""


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


@sandik_page_bp.route("/<int:sandik_id>/uye-ekle", methods=["GET", "POST"])
@sandik_authorization_required(permission="write")
def add_member_to_sandik_page(sandik_id):
    form = forms.AddMemberForm(sandik=g.sandik)

    if form.validate_on_submit():
        try:
            if form.email_address.data and form.web_user.data:
                raise AddMemberException("Lütfen e-posta adresi ve site kullanıcısından birini doldurunuz.")
            elif not form.email_address.data and not form.web_user.data:
                raise AddMemberException("Lütfen e-posta adresi ve site kullanıcısından birini doldurunuz.")

            web_user = None
            if form.email_address.data:
                web_user = auth_db.get_web_user(email_address=form.email_address.data)
            elif form.web_user.data:
                web_user = auth_db.get_web_user(id=form.web_user.data)
            if not web_user:
                raise AddMemberException("Site kullanıcısı bulunamadı.")

            utils.add_member_to_sandik(sandik=g.sandik, web_user=web_user, added_by=current_user,
                                       date_of_membership=form.date_of_membership.data,
                                       contribution_amount=form.contribution_amount.data,
                                       detail=form.detail.data,
                                       number_of_share=form.number_of_share.data)
            utils.Notification.MembershipApplication.send_confirming_notification(sandik=g.sandik, web_user=web_user)

            return redirect(url_for("sandik_page_bp.members_of_sandik_page", sandik_id=sandik_id))
        except (AddMemberException, WebUserIsAlreadyMember, NoValidRuleFound) as e:
            flash(str(e), "danger")

    if request.method == "GET":
        form.contribution_amount.data = g.sandik.contribution_amount

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Sandığa üye ekle", form=form, active_dropdown='members'))


@sandik_page_bp.route("/<int:sandik_id>/uye-<int:member_id>/guncelle", methods=["GET", "POST"])
@sandik_authorization_required(permission="write")
def update_member_of_sandik_page(sandik_id, member_id):
    member = db.get_member(id=member_id, sandik_ref=g.sandik)
    if not member:
        abort(404, "Üye bulunamadı")

    form = forms.EditMemberForm()

    if form.validate_on_submit():
        try:
            updated_values = {
                "detail": form.detail.data,
                "date_of_membership": form.date_of_membership.data,
                "contribution_amount": form.contribution_amount.data
            }
            if form.email_address.data != member.web_user_ref.email_address:
                web_user = auth_db.get_web_user(email_address=form.email_address.data)
                if not web_user:
                    raise WebUserNotFound("Site kullanıcısı bulunamadı.")
                updated_values["web_user_ref"] = web_user

            utils.update_member_of_sandik(member=member, updated_by=current_user, **updated_values)

            return redirect(url_for("sandik_page_bp.member_summary_for_management_page",
                                    sandik_id=sandik_id, member_id=member_id))
        except (WebUserNotFound, MembershipException) as e:
            flash(str(e), "danger")

    if not form.is_submitted():
        form.fill_values_with_member(member=member)

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Sandığa üye ekle", form=form, active_dropdown='members'))


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
    g.members = g.sandik.members_set.order_by(lambda m: m.web_user_ref.name_surname.lower())
    return render_template("sandik/members_of_sandik_page.html",
                           page_info=LayoutPI(title="Üyeler", active_dropdown="members"))


@sandik_page_bp.route("/<int:sandik_id>/uyelik-basvurulari")
@sandik_authorization_required(permission="read")
def membership_applications_to_sandik_page(sandik_id):
    return render_template("sandik/membership_applications_to_sandik_page.html",
                           page_info=LayoutPI(title="Üyelik başvuruları", active_dropdown="members"))


@sandik_page_bp.route("/<int:sandik_id>/uye-<int:member_id>/ozet")
@sandik_authorization_required(permission="read")
def member_summary_for_management_page(sandik_id, member_id):
    member = db.get_member(id=member_id, sandik_ref=g.sandik)
    if not member:
        abort(404, "Üye bulunamadı")

    g.member = member
    g.summary_data = utils.get_member_summary_page(member=g.member)
    g.type = "management"

    g.accepted_trust_links = sorted(g.member.accepted_trust_links(),
                                    key=lambda tr: tr.other_member(whose=member).web_user_ref.name_surname)

    page_title = f"Üye özeti: {g.member.web_user_ref.name_surname}"
    return render_template("sandik/sandik_summary_for_member_page.html",
                           page_info=LayoutPI(title=page_title, active_dropdown="members"))


@sandik_page_bp.route("/<int:sandik_id>/uye-<int:member_id>/hisse-ekle", methods=["GET", "POST"])
@sandik_authorization_required(permission="write")
def add_share_to_member_page(sandik_id, member_id):
    member = db.get_member(id=member_id, sandik_ref=g.sandik)
    if not member:
        abort(404, "Üye bulunamadı")

    # Üyenin hisse sayısı açılabilecek hisse sayısından küçük mü diye kontrol ediliyor
    danger_msg = None
    try:
        max_share_count = sandik_preferences.get_max_number_of_share(sandik=member.sandik_ref)
        if member.shares_set.select(lambda s: s.is_active).count() >= max_share_count:
            danger_msg = f"Bir üyenin en fazla {max_share_count} adet hissesi olabilir."
    except NoValidRuleFound as e:
        danger_msg = str(e)
    finally:
        if danger_msg:
            flash(danger_msg, "danger")
            return redirect(request.referrer or url_for("sandik_page_bp.member_summary_for_management_page",
                                                        sandik_id=sandik_id, member_id=member_id))

    form = forms.AddShareForm()
    form.share_order_of_member.data = db.get_last_share_order(member) + 1

    if form.validate_on_submit():
        try:
            utils.add_share_to_member(member=member, date_of_opening=form.date_of_opening.data,
                                      added_by=current_user)
            utils.Notification.MembershipApplication.send_adding_share_notification(sandik=g.sandik,
                                                                                    web_user=member.web_user_ref)

            return redirect(
                url_for("sandik_page_bp.member_summary_for_management_page", sandik_id=sandik_id, member_id=member_id)
            )
        except (MaxShareCountExceed, NoValidRuleFound) as e:
            flash(str(e), "danger")

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Hisse ekle", form=form, active_dropdown='members'))


@sandik_page_bp.route("/<int:sandik_id>/uye-<int:member_id>/sil")
@sandik_authorization_required(permission="write")
def remove_member_from_sandik_page(sandik_id, member_id):
    member = db.get_member(id=member_id, sandik_ref=g.sandik)
    if not member:
        abort(404, "Üye bulunamadı")

    try:
        utils.remove_member_from_sandik(member=member, removed_by=current_user)
    except (NotActiveMemberException, ThereIsUnpaidDebtOfMemberException, ThereIsUnpaidAmountOfLoanedException,
            NotActiveShareException, ThereIsUnpaidDebtOfShareException) as e:
        flash(str(e), "danger")

    return redirect(request.referrer or url_for("sandik_page_bp.members_of_sandik_page", sandik_id=sandik_id))


@sandik_page_bp.route("/<int:sandik_id>/uye-<int:member_id>/hisse-<int:share_id>/sil")
@sandik_authorization_required(permission="write")
def remove_share_from_member_page(sandik_id, member_id, share_id):
    member = db.get_member(id=member_id, sandik_ref=g.sandik)
    if not member:
        abort(404, "Üye bulunamadı")

    share = db.get_share(id=share_id, member_ref=member)
    if not share:
        abort(404, "Hisse bulunamadı")

    try:
        utils.remove_share_from_member(share=share, removed_by=current_user)
    except (NotActiveShareException, ThereIsUnpaidDebtOfShareException) as e:
        flash(str(e), "danger")
        print(type(e), e)

    return redirect(request.referrer or url_for("sandik_page_bp.member_summary_for_management_page",
                                                sandik_id=sandik_id, member_id=member_id))


"""
########################################################################################################################
#############################################  Sandık yetkileri sayfaları  #############################################
########################################################################################################################
"""


@sandik_page_bp.route("/<int:sandik_id>/sandik-yetkileri")
@sandik_authorization_required(permission="read")
def sandik_authorities_page(sandik_id):
    g.authorities = g.sandik.sandik_authority_types_set.order_by(lambda sat: sat.name)
    return render_template("sandik/sandik_authorities_page.html",
                           page_info=LayoutPI(title="Sandık yetkileri", active_dropdown="sandik-authorities"))


@sandik_page_bp.route("/<int:sandik_id>/sandik-yetkisi-ekle", methods=["GET", "POST"])
@sandik_authorization_required(permission="admin")
def create_sandik_authority_page(sandik_id):
    form = forms.SandikAuthorityForm()

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form, boolean_fields=["is_admin", "can_read", "can_write"])
        db.create_sandik_authority(created_by=current_user, sandik_ref=g.sandik, **form_data)
        return redirect(url_for("sandik_page_bp.sandik_authorities_page", sandik_id=sandik_id))

    return render_template(
        "utils/form_layout.html",
        page_info=FormPI(title="Sandık yetkisi oluştur", form=form, active_dropdown='sandik-authorities')
    )


@sandik_page_bp.route("/<int:sandik_id>/sandik-yetkileri/<int:sandik_authority_id>/sil")
@sandik_authorization_required(permission="admin")
def delete_sandik_authority_page(sandik_id, sandik_authority_id):
    authority = db.get_sandik_authority(id=sandik_authority_id, sandik_ref=g.sandik)
    if not authority:
        abort(404)

    db.delete_sandik_authority(sandik_authority=authority, deleted_by=current_user)
    return redirect(request.referrer)


@sandik_page_bp.route("/<int:sandik_id>/yetkili-kullanicilar")
@sandik_authorization_required(permission="read")
def authorized_web_users_of_sandik_page(sandik_id):
    g.authorized_web_users = db.select_authorized_web_users_of_sandik(sandik=g.sandik)
    return render_template("sandik/authorized_web_users_of_sandik_page.html",
                           page_info=LayoutPI(title="Sandık yetkileri", active_dropdown="sandik-authorities"))


@sandik_page_bp.route("/<int:sandik_id>/yetkili-ekle", methods=["GET", "POST"])
@sandik_authorization_required(permission="admin")
def add_authorized_to_sandik_page(sandik_id):
    form = forms.AddAuthorizedForm(sandik=g.sandik)

    if form.validate_on_submit():
        try:
            if form.email_address.data and form.member.data:
                raise SandikAuthorityException("Lütfen e-posta adresi ve sandık üyesinden birini doldurunuz.")
            elif form.email_address.data:
                web_user = auth_db.get_web_user(email_address=form.email_address.data)
                if not web_user:
                    raise SandikAuthorityException("Bu e-posta adresine tanımlı kullanıcı bulunamadı.")
            elif form.member.data:
                member = db.get_member(id=form.member.data)
                if not member:
                    raise SandikAuthorityException("Üye yanlış seçildi.", create_log=True)
                web_user = member.web_user_ref
            else:
                raise SandikAuthorityException("Lütfen e-posta adresi ve sandık üyesinden birini doldurunuz.")

            authority = db.get_sandik_authority(id=form.authority.data)

            db.add_authorized_to_sandik(connected_by=current_user, web_user=web_user, sandik_authority=authority)

            return redirect(url_for("sandik_page_bp.authorized_web_users_of_sandik_page", sandik_id=sandik_id))
        except SandikAuthorityException as e:
            flash(str(e), "danger")

    return render_template(
        "utils/form_layout.html",
        page_info=FormPI(title="Sandığa yetkili ekle", form=form, active_dropdown='sandik-authorities')
    )


@sandik_page_bp.route("/<int:sandik_id>/sandik-yetkilileri/<int:web_user_id>/kaldir")
@sandik_authorization_required(permission="admin")
@web_user_required
def remove_authorized_from_sandik_page(sandik_id, web_user_id):
    authority = g.web_user.get_sandik_authority(sandik=g.sandik)
    if not authority:
        abort(404)

    db.delete_authorized_from_sandik(sandik_authority=authority, web_user=g.web_user, removed_by=current_user)
    return redirect(request.referrer)


"""
########################################################################################################################
##############################################  Sms bildirimi sayfaları   ##############################################
########################################################################################################################
"""


@sandik_page_bp.route("/<int:sandik_id>/sms-gonder", methods=["GET", "POST"])
@sandik_authorization_required(permission="write")
def send_sms_page(sandik_id):
    form = forms.SendSmsForm()

    if form.validate_on_submit():
        form_data = flask_form_to_dict(request_form=request.form)
        utils.send_sms_from_sandik(sandik=g.sandik, created_by=current_user, **form_data)
        return redirect(url_for("sandik_page_bp.send_sms_page", sandik_id=sandik_id))

    return render_template("utils/form_layout.html",
                           page_info=FormPI(title="Sandık üyelerine SMS gönder", form=form, active_dropdown='sms'))


"""
########################################################################################################################
#############################################  Sandık kuralları sayfaları   ############################################
########################################################################################################################
"""


@sandik_page_bp.route("/<int:sandik_id>/sandik-kurali-ekle", methods=["GET", "POST"])
@sandik_authorization_required(permission="write")
def add_sandik_rule_page(sandik_id):
    form = forms.SandikRuleForm()

    if form.validate_on_submit():
        utils.add_sandik_rule_to_sandik(condition_formula=form.condition_formula.data,
                                        value_formula=form.value_formula.data,
                                        type=form.type.data, sandik=g.sandik, created_by=current_user)
        return redirect(url_for("sandik_page_bp.add_sandik_rule_page", sandik_id=sandik_id))

    return render_template("sandik/add_sandik_rule_page.html",
                           page_info=FormPI(title="Sandık kuralı ekle", form=form, active_dropdown='sandik-rules'))


@sandik_page_bp.route("/<int:sandik_id>/sandik-kurallari")
@sandik_authorization_required(permission="read")
def sandik_rules_page(sandik_id):
    g.sandik_rules = db.get_sandik_rules_groups_by_category(sandik=g.sandik)
    return render_template("sandik/sandik_rules_page.html",
                           page_info=LayoutPI(title="Sandık kuralları", active_dropdown="sandik-rules"))


@sandik_page_bp.route("/<int:sandik_id>/sk-<int:sandik_rule_id>/yukari-tasi")
@sandik_authorization_required(permission="write")
@sandik_rule_required
def raise_order_of_sandik_rule_page(sandik_id, sandik_rule_id):
    if not db.raise_order_of_sandik_rule(sandik_rule=g.sandik_rule, updated_by=current_user):
        flash("Sandık kuralı zaten en öncelikli durumda", "warning")
    return redirect(request.referrer or url_for("sandik_page_bp.sandik_rules_page", sandik_id=sandik_id))


@sandik_page_bp.route("/<int:sandik_id>/sk-<int:sandik_rule_id>/asagi-tasi")
@sandik_authorization_required(permission="write")
@sandik_rule_required
def lower_order_of_sandik_rule_page(sandik_id, sandik_rule_id):
    if not db.lower_order_of_sandik_rule(sandik_rule=g.sandik_rule, updated_by=current_user):
        flash("Sandık kuralı zaten en az öncelikli durumda", "warning")
    return redirect(request.referrer or url_for("sandik_page_bp.sandik_rules_page", sandik_id=sandik_id))


"""
########################################################################################################################
########################################################################################################################
########################################################################################################################
"""
