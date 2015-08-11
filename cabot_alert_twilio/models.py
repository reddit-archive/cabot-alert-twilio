import logging
import os
import uuid

from boto import connect_s3
from cabot.cabotapp.alert import AlertPlugin, AlertPluginUserData
from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from twilio import twiml
from twilio.rest import TwilioRestClient


_LOG = logging.getLogger(__name__)


def _make_twilio_client():
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    outgoing_number = os.environ["TWILIO_OUTGOING_NUMBER"]
    return TwilioRestClient(account_sid, auth_token), outgoing_number


class TwilioUserData(AlertPluginUserData):
    name = "Twilio Plugin"
    phone_number = models.CharField(max_length=30, blank=True, null=True)

    def save(self, *args, **kwargs):
        if str(self.phone_number).startswith("+"):
            self.phone_number = self.phone_number[1:]
        return super(TwilioUserData, self).save(*args, **kwargs)

    @property
    def prefixed_phone_number(self):
        return "+" + self.phone_number


class TwilioSMS(AlertPlugin):
    name = "Twilio SMS"
    author = ""
    _max_length = 160

    @classmethod
    def _make_message(cls, service):
        if service.overall_status == service.PASSING_STATUS:
            return "<{service_name}> has returned to normal!".format(
                service_name=service.name)
        else:
            prefix = "<{service_name}> is reporting {status}".format(
                service_name=service.name,
                status=service.overall_status,
            )

            suffix = "{scheme}://{host}{url}".format(
                scheme=settings.WWW_SCHEME,
                host=settings.WWW_HTTP_HOST,
                url=reverse("service", kwargs={"pk": service.id}),
            )

            failing_checks = list(service.all_failing_checks())
            criticals = ["- " + check.name for check in failing_checks
                         if check.importance == "CRITICAL"]
            errors = ["- " + check.name for check in failing_checks
                      if check.importance == "ERROR"]
            body = "\n".join(criticals + errors)

            characters_consumed = len("\n".join((prefix, "", suffix)))
            characters_remaining = cls._max_length - characters_consumed
            if len(body) > characters_remaining:
                body = "- {:d} checks failing".format(len(criticals) + len(errors))

            return "\n".join((prefix, body, suffix))

    def send_alert(self, service, users, duty_officers):
        if (service.old_overall_status == service.PASSING_STATUS and
            service.overall_status == service.WARNING_STATUS):
            return

        message = self._make_message(service)

        users_to_alert = list(users) + list(duty_officers)
        on_call = TwilioUserData.objects.filter(user__user__in=users_to_alert)
        mobiles = [u.prefixed_phone_number for u in on_call if u.phone_number]

        twilio, outgoing_number = _make_twilio_client()
        for mobile in mobiles:
            try:
                twilio.sms.messages.create(
                    to=mobile,
                    from_=outgoing_number,
                    body=message,
                )
            except Exception as exception:
                _LOG.exception("Error sending SMS: %s", exception)


PHONE_TEMPLATE = (
    "This is an urgent message from reddit monitoring.  The {service_name} "
    "service is reporting critical errors.  Please check Cabot immediately. "
    "This message repeats."
)


class TwilioPhoneCall(AlertPlugin):
    name = "Twilio Phone Call"
    author = ""

    @staticmethod
    def _upload_to_s3(twiml):
        bucket = os.environ["TWILIO_TWIML_BUCKET"]
        try:
            s3 = connect_s3()
            bucket = s3.get_bucket(bucket, validate=False)
            key = bucket.new_key("/" + str(uuid.uuid1()))
            key.set_contents_from_string(
                twiml,
                headers={
                    "Content-Type": "text/xml",
                },
                reduced_redundancy=False,
                replace=True,
            )
            return key.generate_url(expires_in=60)
        except Exception as exception:
            _LOG.exception("Error uploading to S3: %s", exception)

    def send_alert(self, service, users, duty_officers):
        if service.overall_status != service.CRITICAL_STATUS:
            return

        message = PHONE_TEMPLATE.format(
            service_name=service.name,
        )

        # since cabot is running behind a firewall, we can't have twilio hit us
        # directly for TwiML.  so, we build it and throw it up on s3.  this
        # means that phone calls require s3 to be available, which isn't ideal,
        # but the SMS alerts should be going out too so it's not entirely
        # silent if s3 is off the ranch.
        response = twiml.Response()
        response.say(message, voice="alice", loop=3)
        twiml_callback_url = self._upload_to_s3(str(response))
        if not twiml_callback_url:
            return

        on_call = TwilioUserData.objects.filter(user__user__in=duty_officers)
        mobiles = [u.prefixed_phone_number for u in on_call if u.phone_number]

        twilio, outgoing_number = _make_twilio_client()
        for mobile in mobiles:
            try:
                twilio.calls.create(
                    to=mobile,
                    from_=outgoing_number,
                    url=twiml_callback_url,
                    method="GET",
                )
            except Exception as exception:
                _LOG.exception("Error making phone call: %s", exception)
