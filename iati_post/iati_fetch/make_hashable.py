# Credit to https://stackoverflow.com/a/42151923/2219724

import logging

logger = logging.getLogger(__name__)


def make_hashable(o) -> tuple:
    if isinstance(o, (tuple, list)):
        return tuple((make_hashable(e) for e in o))

    if isinstance(o, dict):
        return tuple(sorted((k, make_hashable(v)) for k, v in o.items()))

    if isinstance(o, (set, frozenset)):
        return tuple(sorted(make_hashable(e) for e in o))

    return o


def request_hash(
    params: dict = None, url: str = "www.example.com", method: str = "GET", **kwargs
) -> tuple:
    dict_to_hash = {"__url__": url, "__method__": method}
    if params:
        dict_to_hash.update(params)
    rhash = make_hashable(dict_to_hash)
    logger.debug("Hash generated: %s -> %s", dict_to_hash, rhash)
    return rhash


if __name__ == "__main__":
    o = dict(x=1, b=2, c=[3, 4, 5], d={6, 7})
    o2 = dict(x=1, d={6, 7}, b=2, c=[5, 4, 3])
    print(make_hashable(o))
    # (('b', 2), ('c', (3, 4, 5)), ('d', (6, 7)), ('x', 1))
    print(make_hashable(2))
