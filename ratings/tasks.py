import json
import requests

from celery.task import Task
from celery.utils.log import get_task_logger
from django.conf import settings
from seed_services_client.message_sender import MessageSenderApiClient

from .models import Invite


ms_client = MessageSenderApiClient(
    api_url=settings.MESSAGE_SENDER_URL,
    auth_token=settings.MESSAGE_SENDER_TOKEN
)


class SendInviteMessage(Task):
    """ Task to send a servicerating invitation message
    """
    name = "seed_service_rating.ratings.tasks.send_invite_message"
    l = get_task_logger(__name__)

    def compile_msg_payload(self, invite):
        """ Determine recipient, message content, return it as
        a dict that can be Posted to the message sender
        """
        self.l.info("Compiling the outbound message payload")
        # Determine the recipient address
        if "to_addr" in invite.invite:
            to_addr = invite.invite["to_addr"]
        else:
            # TODO: Lookup default address if to_addr not provided
            #       This is a potential future improvement
            pass

        # Determine the message content
        if "content" in invite.invite:
            content = invite.invite["content"]
        else:
            content = settings.INVITE_TEXT

        msg_payload = {
            "to_addr": to_addr,
            "content": content,
            "metadata": {}
        }
        self.l.info("Compiled the outbound message payload")
        return msg_payload

    def send_message(self, payload):
        """ Create a post request to the message sender
        """
        self.l.info("Creating outbound message request")
        result = ms_client.create_outbound(payload)
        self.l.info("Created outbound message request")
        return result

    def run(self, invite_id, **kwargs):
        """ Sends a message about service rating to invitee
        """
        self.l = self.get_logger(**kwargs)
        self.l.info("Looking up the invite")
        invite = Invite.objects.get(id=invite_id)
        msg_payload = self.compile_msg_payload(invite)
        result = self.send_message(msg_payload)
        print(result)
        return "Message queued for send. ID: <%s>" % str(result["id"])


send_invite_message = SendInviteMessage()


class DeliverHook(Task):
    def run(self, target, payload, instance_id=None, hook_id=None, **kwargs):
        """
        target:     the url to receive the payload.
        payload:    a python primitive data structure
        instance_id:   a possibly None "trigger" instance ID
        hook_id:       the ID of defining Hook object
        """
        requests.post(
            url=target,
            data=json.dumps(payload),
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Token %s' % settings.HOOK_AUTH_TOKEN
            }
        )


def deliver_hook_wrapper(target, payload, instance, hook):
    if instance is not None:
        instance_id = instance.id
    else:
        instance_id = None
    kwargs = dict(target=target, payload=payload,
                  instance_id=instance_id, hook_id=hook.id)
    DeliverHook.apply_async(kwargs=kwargs)
