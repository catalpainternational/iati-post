from channels.consumer import SyncConsumer, AsyncConsumer
from aiohttp import ClientSession, TCPConnector


class RequestConsumer(AsyncConsumer):
    async def get(self, event):
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.get(
                url=event.get("url", "http://example.com"), data=event.get("params", "")
            ) as response:
                print(response)
