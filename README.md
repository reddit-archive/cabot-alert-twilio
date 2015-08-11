# cabot-alert-twilio

A [Cabot] alerting plugin that uses SMS and phone calls to get your attention.
This is loosely based on the [original Twilio alert plugin][orig] but rewritten
and has a different take on various aspects to better fit our needs,
specifically:

* The Twilio callback URL for voice messages is routed via Amazon S3 rather
  than directly hitting Cabot; this is important because our Cabot is not
  accessible externally.
* The text messages are more informative, listing which checks failed as much
  as space allows.  Text messages are also sent for ERROR and CRITICAL events
  only, not WARNING.
* Voice messages repeat a few times in case you missed the message.

## installation

```
# add the plugin to the list of enabled plugins
CABOT_PLUGINS_ENABLED=...,cabot_alert_twilio

# configure these based on your twilio account
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_OUTGOING_NUMBER=

# which s3 bucket to put the temporary TwiML files in
# a lifecycle policy to clear out old files is probably a good idea here
TWILIO_TWIML_BUCKET=

# a fallback twiml source for when S3 is unavailable.
TWILIO_TWIML_FALLBACK=
```

[Cabot]: https://github.com/arachnys/cabot
[orig]: https://github.com/bonniejools/cabot-alert-twilio
