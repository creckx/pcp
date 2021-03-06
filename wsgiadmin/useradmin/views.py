from random import randint
from time import time
from hashlib import md5

from constance import config
from crispy_forms.helper import FormHelper
from django.contrib import messages
from django.db.models.query_utils import Q
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _, ugettext
from django.template.context import RequestContext
from django.core.mail import send_mail, EmailMessage
from django.views.generic import TemplateView
from django.views.generic.edit import FormView
from wsgiadmin.apps.forms import EmailForm
from wsgiadmin.core.tasks import send_email

from wsgiadmin.old.apacheconf.models import UserSite
from wsgiadmin.clients.models import *
from wsgiadmin.emails.models import Message
from wsgiadmin.old.requests.request import SSHHandler
from wsgiadmin.service.forms import PassCheckForm, RostiFormHelper
from wsgiadmin.useradmin.forms import SendPwdForm, RegistrationForm, AdminPasswd
from wsgiadmin.clients.models import Parms
from wsgiadmin.stats.tools import add_credit


class EmailView(TemplateView):
    template_name = "universal.html"
    form_class = EmailForm
    success_url = reverse_lazy("send_email")
    menu_active = "dashboard"

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.user = request.session.get('switched_user', request.user)
        self.superuser = request.user
        if not self.superuser.is_superuser:
            return HttpResponseForbidden(_("Permission error"))
        return super(EmailView, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = self.get_form(request)
        context = self.get_context_data(form, **kwargs)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = self.get_form(request)
        if not form.is_valid():
            context = self.get_context_data(form, **kwargs)
            return self.render_to_response(context)
        else:
            url = self.form_valid(form)
            return HttpResponseRedirect(url)

    def form_valid(self, form):
        send_email.delay(form.cleaned_data["subject"], form.cleaned_data["message"], [int(x) for x in form.cleaned_data["ids"].strip().split(" ")])
        return self.success_url

    def get_form(self, request):
        if request.method == "POST":
            return self.form_class(request.POST)
        return self.form_class()

    def get_context_data(self, form, **kwargs):
        context = super(EmailView, self).get_context_data(**kwargs)
        context["form"] = form
        context['menu_active'] = self.menu_active
        context['u'] = self.user
        context['superuser'] = self.superuser
        return context


@login_required
def app_copy(request):
    u = request.session.get('switched_user', request.user)
    superuser = request.user
    if not superuser.is_superuser:
        return HttpResponseForbidden(_("Permission error"))

    app = UserSite.objects.get(id=int(request.POST.get("app")))
    new_location = request.POST.get("new_location")

    sh = SSHHandler(request.user, app.owner.parms.web_machine)
    cmd = "cp -a %s %s" % (app.document_root, new_location)
    sh.run(cmd=cmd, instant=True)

    messages.add_message(request, messages.SUCCESS, _('Site has been copied'))

    return HttpResponseRedirect(reverse("master"))


@login_required
def master(request):
    u = request.session.get('switched_user', request.user)
    superuser = request.user
    if not superuser.is_superuser:
        return HttpResponseForbidden(_("Permission error"))

    apps = []
    balance_day = 0.0
    balance_month = 0.0

    if settings.OLD:
        balance_day = 0
        sites = UserSite.objects.all()
        for site in sites:
            balance_day += site.pay
        balance_month = balance_day * 30

        apps = UserSite.objects.filter(Q(type="static")|Q(type="php"))
        apps = sorted(apps, key=lambda x: x.main_domain.name)

    return render_to_response('master.html', {
        "u": u,
        "superuser": superuser,
        "menu_active": "dashboard",
        "balance_day": balance_day,
        "balance_month": balance_month,
        "apps": apps,
        },
        context_instance=RequestContext(request)
    )


@login_required
def info(request):
    user = request.session.get('switched_user', request.user)
    superuser = request.user

    return render_to_response('info.html',
            {
                "u": user,
                "superuser": superuser,
                "menu_active": "dashboard",
                "config": config,
                "not_payed": user.credit_set.filter(date_payed=None),
            },
        context_instance=RequestContext(request)
    )


@login_required
def requests(request):
    u = request.session.get('switched_user', request.user)
    superuser = request.user

    requests = u.request_set.order_by("add_date").reverse()

    return render_to_response('old/requests.html', {
            "u": u,
            "superuser": superuser,
            "menu_active": "dashboard",
            "requests": requests[:20],
        }, context_instance=RequestContext(request)
    )


@login_required
def ok(request):
    u = request.session.get('switched_user', request.user)
    superuser = request.user
    return render_to_response('ok.html',
            {"u": u, "superuser": superuser, },
                              context_instance=RequestContext(request)
    )

class PasswordView(FormView):
    template_name = 'passwd_form.html'

    def __init__(self, *args, **kwargs):
        super(PasswordView, self).__init__(*args, **kwargs)
        self.success_url = reverse('login')

    def get_form_class(self):
        return SendPwdForm

    def get_context_data(self, **kwargs):
        data = super(PasswordView, self).get_context_data(**kwargs)
        data['form_helper'] = RostiFormHelper()
        data['menu_active'] = "reset_passwd"
        return data

    def form_valid(self, form):
        print form
        print dir(form)
        user = form.user_object
        print user

        pwd = md5( str(time()*randint(1, 300)) ).hexdigest()[:7]
        message = ugettext("Your password has been reseted: %s" % pwd)
        user.set_password(pwd)

        try:
            send_mail(_('Password reset'), message, settings.EMAIL_FROM, [user.email], fail_silently=False)
        except:
            pass
        else:
            #save changed password only on notification success
            user.save()

        messages.add_message(self.request, messages.SUCCESS, _("Password has been reseted and sent to your email"))
        return super(PasswordView, self).form_valid(form)


@login_required
def change_passwd(request):
    u = request.session.get('switched_user', request.user)
    superuser = request.user

    if request.method == 'POST':
        form = AdminPasswd(request.POST)
        if form.is_valid():
            u.set_password(form.cleaned_data["password1"])
            u.save()

            messages.add_message(request, messages.SUCCESS, _('Password has been changed'))
            return HttpResponseRedirect(reverse("wsgiadmin.useradmin.views.change_passwd"))
    else:
        form = AdminPasswd()

    return render_to_response('universal.html',
            {
            "form": form,
            "title": _("Change password for this administration"),
            "u": u,
            "superuser": superuser,
            "menu_active": "settings",
            },
        context_instance=RequestContext(request)
    )

def reg(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            # machine
            if settings.OLD:
                m_web = get_object_or_404(Machine, name=config.default_web_machine)
                m_mail = get_object_or_404(Machine, name=config.default_mail_machine)
                m_mysql = get_object_or_404(Machine, name=config.default_mysql_machine)
                m_pgsql = get_object_or_404(Machine, name=config.default_pgsql_machine)

            # user
            u = user.objects.create_user(form.cleaned_data["username"],
                                         form.cleaned_data["email"],
                                         form.cleaned_data["password1"])
            u.is_active = True
            u.save()

            # parms
            p = Parms()
            p.home = "/dev/null"
            p.note = ""
            p.uid = 0
            p.gid = 0
            p.discount = 0
            if settings.OLD:
                p.web_machine = m_web
                p.mail_machine = m_mail
                p.mysql_machine = m_mysql
                p.pgsql_machine = m_pgsql
            p.user = u
            p.save()

            if config.credit_registration:
                add_credit(u, float(config.credit_registration), free=True)

            message = Message.objects.filter(purpose="reg")
            if message:
                message[0].send(form.cleaned_data["email"])

            message = _("User %s has been registered." % u.username)
            send_mail(_('New registration'),
                      message,
                      settings.EMAIL_FROM,
                [address for (name, address) in settings.ADMINS],
                      fail_silently=True)
            #fail_silently - nechci 500 kvuli neodeslanemu mailu

            return HttpResponseRedirect(
                reverse("wsgiadmin.useradmin.views.regok"))
    else:
        form = RegistrationForm()

    return render_to_response('reg.html',
        {
            "form": form,
            "title": _("Registration"),
            "action": reverse("wsgiadmin.useradmin.views.reg"),
            "config": config,
            "menu_active": "registration",
        },
        context_instance=RequestContext(request)
    )


def regok(request):
    return render_to_response('regok.html', context_instance=RequestContext(request))
