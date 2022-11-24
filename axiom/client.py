"""Client provides an easy-to use client library to connect to Axiom."""
import ndjson
import dacite
import ujson
import os
from typing import Optional
from logging import getLogger
from dataclasses import dataclass, field
from requests_toolbelt.sessions import BaseUrlSession
from requests_toolbelt.utils.dump import dump_response, dump_all
from requests.adapters import HTTPAdapter, Retry
from .datasets import DatasetsClient, ContentType
from .users import UsersClient
from .__init__ import __version__


AXIOM_URL = "https://cloud.axiom.co"


@dataclass
class Error:
    status: int = field(default=None)
    message: str = field(default=None)
    error: str = field(default=None)


def raise_response_error(r):
    if r.status_code >= 400:
        print("==== Response Debugging ====")
        print("##Request Headers", r.request.headers)

        # extract content type
        ct = r.headers["content-type"].split(";")[0]
        if ct == ContentType.JSON.value:
            dump = dump_response(r)
            print(dump)
            print("##Response:", dump.decode("UTF-8"))
            err = dacite.from_dict(data_class=Error, data=r.json())
            print(err)
        elif ct == ContentType.NDJSON.value:
            decoded = ndjson.loads(r.text)
            print("##Response:", decoded)

        r.raise_for_status()
        # TODO: Decode JSON https://github.com/axiomhq/axiom-go/blob/610cfbd235d3df17f96a4bb156c50385cfbd9edd/axiom/error.go#L35-L50


class Client:  # pylint: disable=R0903
    """The client class allows you to connect to Axiom."""

    datasets: DatasetsClient
    users: UsersClient

    def __init__(self, token: Optional[str], org_id: Optional[str] = None, url_base: Optional[str] = None):
        # fallback to env variables if token, org_id or url are not provided
        if token is None:
            token = os.getenv("AXIOM_TOKEN")
        if org_id is None:
            org_id = os.getenv("AXIOM_ORG_ID")
        if url_base is None:
            url_base = AXIOM_URL
        # Append /api/v1 to the url_base
        url_base = url_base.rstrip("/") + "/api/v1/"

        logger = getLogger()
        session = BaseUrlSession(url_base)
        # set exponential retries
        retries = Retry(
            total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504]
        )
        session.mount("http://", HTTPAdapter(max_retries=retries))
        session.mount("https://", HTTPAdapter(max_retries=retries))
        # hook on responses, raise error when response is not successfull
        session.hooks = {"response": lambda r, *args, **kwargs: raise_response_error(r)}
        session.headers.update(
            {
                "Authorization": "Bearer %s" % token,
                # set a default Content-Type header, can be overriden by requests.
                "Content-Type": "application/json",
                "User-Agent": f"axiom-py/{__version__}",
            }
        )

        # if there is an organization id passed,
        # set it in the header
        if org_id:
            logger.info("found organization id: %s" % org_id)
            session.headers.update({"X-Axiom-Org-Id": org_id})

        self.datasets = DatasetsClient(session, logger)
        self.users = UsersClient(session)
