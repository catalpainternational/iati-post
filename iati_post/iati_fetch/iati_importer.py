import asyncio
import logging
from . import fetch

logger = logging.getLogger(__name__)


async def main(truncate=True, fetch_names=True):
    if truncate:
        await fetch.truncate_tables()

    if fetch_names:
        await fetch.organisation_list()
    organisation_names = await fetch.organisation_names()

    organisation_names = ["ec-devco"]

    logger.debug("%s", ",".join(organisation_names[:5]) + "...")

    for name in organisation_names:
        await fetch.organisation_xml(name)


def run():
    loop = asyncio.run(main(truncate=False, fetch_names=True))
