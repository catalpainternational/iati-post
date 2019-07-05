import pytest
from channels.testing import WebsocketCommunicator

from iati_post.routing import application


@pytest.mark.asyncio
async def test_echo():
    """
    Demonstrates how to send/receive from a websocket
    """
    communicator = WebsocketCommunicator(application, "/fetchurl/")
    connected, subprotocol = await communicator.connect()
    assert connected
    # Test sending text
    await communicator.send_to(text_data="hello")
    response = await communicator.receive_from()
    assert response.startswith("<!doctype")
    # Close
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_fetch_organisation_list():
    """
    Demonstrates how to send/receive from a websocket
    """
    communicator = WebsocketCommunicator(application, "/iati/")
    connected, subprotocol = await communicator.connect()
    assert connected
    # Test sending text
    await communicator.send_to(text_data="hello")
    # We expect to receive a list of Organisations
    # response = await communicator.receive_from()
    # assert "result" in response
    # Close
    await communicator.disconnect()
