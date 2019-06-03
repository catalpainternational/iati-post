# Credit to https://stackoverflow.com/a/42151923/2219724

import base64
import hashlib
import logging

logger = logging.getLogger(__name__)


def make_hash_sha256(o):
    hasher = hashlib.sha256()
    hasher.update(repr(make_hashable(o)).encode())
    return base64.b64encode(hasher.digest()).decode()


def make_hashable(o):
    if isinstance(o, (tuple, list)):
        print(o)
        return tuple((make_hashable(e) for e in o))

    if isinstance(o, dict):
        return tuple(sorted((k, make_hashable(v)) for k, v in o.items()))

    if isinstance(o, (set, frozenset)):
        return tuple(sorted(make_hashable(e) for e in o))

    return o


def request_hash(params: dict, url: str, method: str = "GET"):
    if method != "GET":
        params["_method"] = method
    hash_content = {"__url__": url, **params}
    sha_hash = make_hash_sha256(hash_content)
    logger.debug("%s %s -> %s", url, params, sha_hash)
    return sha_hash


if __name__ == "__main__":
    o = dict(x=1, b=2, c=[3, 4, 5], d={6, 7})
    o2 = dict(x=1, d={6, 7}, b=2, c=[5, 4, 3])
    print(make_hashable(o))
    # (('b', 2), ('c', (3, 4, 5)), ('d', (6, 7)), ('x', 1))
    print(make_hashable(2))

    print(make_hash_sha256(o))
    # fyt/gK6D24H9Ugexw+g3lbqnKZ0JAcgtNW+rXIDeU2Y=
    print(make_hash_sha256(o2))
