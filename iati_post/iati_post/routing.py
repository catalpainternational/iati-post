from channels.auth import AuthMiddlewareStack
from channels.routing import ChannelNameRouter, ProtocolTypeRouter, URLRouter
from django.conf.urls import url

from iati_fetch import consumers

application = ProtocolTypeRouter(
    {
        # (http->django views is added by default)
        "channel": ChannelNameRouter(
            {
                "request": consumers.RequestConsumer,
                "iati": consumers.IatiRequestConsumer,
            }
        ),
        "websocket": AuthMiddlewareStack(
            URLRouter(
                [
                    url(r"^echo/$", consumers.EchoConsumer),
                    url(r"^fetchurl/$", consumers.FetchUrl),
                ]
            )
        ),
    }
)
