#TODO:Remove, put it in settings
#^WUT?
import logging

from constance import config

from django.contrib import messages
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, Http404
from django.core.mail import send_mail
from django.template.context import RequestContext
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _, ugettext
from django.conf import settings
from django.views.generic import ListView

from wsgiadmin.apacheconf.views import JsonResponse
from wsgiadmin.domains.models import Domain, form_registration_request
from wsgiadmin.requests.request import BindRequest
from wsgiadmin.keystore.tools import *


class RostiListView(ListView):

    paginate_by = 10

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(RostiListView, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset(user=request.session.get('switched_user', request.user), **kwargs)
        allow_empty = self.get_allow_empty()
        if not allow_empty and not len(self.object_list):
            raise Http404(_(u"Empty list and '%(class_name)s.allow_empty' is False.")
                          % {'class_name': self.__class__.__name__})
        context = self.get_context_data(object_list=self.object_list, request=request, **kwargs)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super(RostiListView, self).get_context_data(**kwargs)
        context['menu_active'] = self.menu_active
        context['u'] = self.request.session.get('switched_user', self.request.user)
        context['superuser'] = self.request.user
        return context


class DomainsListView(RostiListView):

    menu_active = 'domains'
    template_name = 'domains.html'

    def get_queryset(self, user):
        return user.domain_set.all()

    def get_context_data(self, **kwargs):
        context = super(DomainsListView, self).get_context_data(**kwargs)
        context['menu_active'] = self.menu_active
        return context



@login_required
def rm(request):

    try:
        u = request.session.get('switched_user', request.user)

        d = get_object_or_404(Domain, id=request.POST['object_id'])
        if d.owner == u:
            logging.info(_("Deleting domain %s") % d.name)

            if config.handle_dns:
                pri_br = BindRequest(u, "master")
                pri_br.remove_zone(d)
                pri_br.mod_config()
                pri_br.reload()

                sec_br = BindRequest(u, "slave")
                sec_br.mod_config()
                sec_br.reload()

            d.delete()

        return JsonResponse("OK", {1: ugettext("Domain was successfuly deleted")})
    except Exception, e:
        return JsonResponse("KO", {1: ugettext("Error deleting domain")})


@login_required
def add(request):
    """
    Add domain of customer
    """
    u = request.session.get('switched_user', request.user)
    superuser = request.user

    if request.method == 'POST':
        form = form_registration_request(request.POST)
        if form.is_valid():
            name = form.cleaned_data["domain"]

            instance, created = Domain.objects.get_or_create(name=name, owner=u)

            if config.handle_dns:
                pri_br = BindRequest(u, "master")
                pri_br.mod_zone(instance)
                pri_br.mod_config()
                pri_br.reload()
                sec_br = BindRequest(u, "slave")
                sec_br.mod_config()
                sec_br.reload()

            logging.info(_("Added domain %s ") % name)
            message = _("Domain %s has been successfuly added") % name
            send_mail(_('Added new domain: %s') % name, message, settings.EMAIL_FROM, [mail for (name, mail) in settings.ADMINS if mail], fail_silently=True)

            messages.add_message(request, messages.SUCCESS, _('Domain has been added'))
            return HttpResponseRedirect(reverse("domains_list"))
    else:
        form = form_registration_request()

    return render_to_response('universal.html',
            {
            "form": form,
            "title": _("Add domain"),
            "submit": _("Save domain"),
            "action": reverse("wsgiadmin.domains.views.add"),
            "u": u,
            "superuser": superuser,
            "menu_active": "domains",
            },
        context_instance=RequestContext(request)
    )
