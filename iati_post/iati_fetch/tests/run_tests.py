from asgiref.sync import async_to_sync 
from channels.layers import get_channel_layer
from random import randint

def signal_get(url:str=None):
    async_to_sync(get_channel_layer().send)('request', {'type': 'get', 'url': url, 'params': {'id': randint(1,1e18)}})

def fetch_organisation():
    async_to_sync(get_channel_layer().send)('iati', {'type': 'parse_xml', 'url': 'https://files.transparency.org/content/download/2279/14136/file/IATI_TIS_Organisation.xml', 'abbreviation': 'TIS'})