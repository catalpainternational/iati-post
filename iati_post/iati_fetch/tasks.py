from . import requesters

async def xml_requests_get(
    organisations: list = None, exclude_cached: bool = False
):
    if not organisations:
        orl = requesters.OrganisationRequestList()
        organisations = await orl.to_list()

    assert isinstance(organisations, list)
    # Limit parallel requests avoiding an OSError: too many open files
    sem = asyncio.Semaphore(2000)
    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        request_count = 0
        tasks = []
        count_orgs = len(organisations)
        print(f"Gathering {count_orgs} Organisations")
        for abbr in organisations:
            instance = requesters.OrganisationRequestDetail(organisation_handle=abbr)
            xml_requests = await instance.iati_xml_requests(session=session)

            for request in xml_requests:
                if exclude_cached:
                    cached = await request.is_cached()
                    if cached:
                        continue
                request_count += 1
                tasks.append(request.bound_get(sem, session=session))
        task_count = len(tasks)
        print(f"Gathering {request_count} XML requests")
        print(f"Gathering {task_count} tasks")
        await asyncio.gather(*tasks)