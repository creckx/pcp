import logging
import sys
from constance import config
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from wsgiadmin.apps.backend import typed_object
from wsgiadmin.old.apacheconf.tools import restart_master
from wsgiadmin.emails.models import Message


class Command(BaseCommand):
    help = "Killer for not payed apps"

    def kill_new_apps(self, user):
        for app in user.app_set.all():
            app = typed_object(app)
            app.disable()
            app.commit()
            logging.info("%s (%d) disabled" % (app.name, app.id))
            print "%s (%d) disabled" % (app.name, app.id)

    def kill_old_apps(self, user):
        restart_master(config.mode, user)

    def refresh_new_apps(self, user):
        for app in user.app_set.all():
            app = typed_object(app)
            app.enable()
            app.commit()
            logging.info("%s (%d) enabled" % (app.name, app.id))
            print "%s (%d) enabled" % (app.name, app.id)

    def refresh_old_apps(self, user):
        restart_master(config.mode, user)

    def check_user(self, user, parms):
        if parms.enable and parms.credit < settings.KILLER_TRESHOLD and parms.num_reminds > settings.NUMBER_OF_REMINDS_TO_KILL:
            print "Killing %s" % user.username, user.email
            parms.enable = False
            parms.save()
            if settings.OLD:
                self.kill_old_apps(user)
            self.kill_new_apps(user)
            sys.stdout.write("%s killed\n" % user.username)
            message = Message.objects.filter(purpose="webs_disabled")
            if message:
                message[0].send(user.email, {"username": user.username})
        elif not parms.enable and parms.credit > 0:
            print "Revival %s" % user.username, user.email
            parms.enable = True
            parms.save()
            if settings.OLD:
                self.refresh_old_apps(user)
            self.refresh_new_apps(user)
            sys.stdout.write("%s refreshed\n" % user.username)
            message = Message.objects.filter(purpose="webs_enabled")
            if message:
                message[0].send(user.email, {"username": user.username})

    def handle(self, *args, **options):
        for user in User.objects.all():
            parms = user.parms
            if parms.guard_enable:
                self.check_user(user, parms)
