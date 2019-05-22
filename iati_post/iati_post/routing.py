from channels.routing import ProtocolTypeRouter, ChannelNameRouter
from iati_fetch import consumers

application = ProtocolTypeRouter(
    {
        # (http->django views is added by default)
        "channel": ChannelNameRouter(
            {"print": consumers.PrintConsumer, "request": consumers.RequestConsumer}
        )
    }
)

