from channels.routing import ProtocolTypeRouter, ChannelNameRouter, URLRouter
from iati_fetch import consumers
from django.conf.urls import url

from channels.auth import AuthMiddlewareStack


application = ProtocolTypeRouter(
    {
        # (http->django views is added by default)
        "channel": ChannelNameRouter(
            {
                "request": consumers.RequestConsumer,
                "iati": consumers.IatiRequestConsumer,
            }
        )
    }
)

