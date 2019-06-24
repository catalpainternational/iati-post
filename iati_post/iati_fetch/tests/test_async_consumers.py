import pytest
from channels.testing import WebsocketCommunicator
from iati_post.routing import application

@pytest.mark.asyncio
async def test_echo():
    communicator = WebsocketCommunicator(application, "/echo/")
    connected, subprotocol = await communicator.connect()
    assert connected
    # Test sending text
    await communicator.send_to(text_data="hello")
    response = await communicator.receive_from()
    assert response == "hello"
    # Close
    await communicator.disconnect()