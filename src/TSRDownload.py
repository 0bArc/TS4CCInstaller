from __future__ import annotations

import os
import random
import re
import time

import http_client
from TSRUrl import TSRUrl
from logger import logger
from exceptions import *

BASE = http_client.BASE
# Calm pacing: wait before first poll, then ~1-1.5s with jitter.
POLL_START_S = 7.0
POLL_INTERVAL_S = 1.2
POLL_JITTER_S = 0.4
POLL_TIMEOUT_S = 30.0
CHUNK = 1024 * 256


def stripForbiddenCharacters(string: str) -> str:
    return re.sub('[\\<>/:"|?*]', "", string)


class TSRDownload:
    """TSR free download flow:

    1. ajax initDownload -> ticket (+ ticket path)
    2. GET ticket page (required; binds ticket / refreshes tsrdlsession)
    3. poll getdownloadurl until CDN URL is ready
    4. stream file (Range resume supported)
    """

    def __init__(self, url: TSRUrl, sessionId: str):
        self.TSRDLTicket = ""
        self.url: TSRUrl = url
        self.sessionId = sessionId
        self.ticketInitializedTime = -1.0
        self.session = http_client.new_session()
        self.session.headers.update(
            {
                "Accept": "*/*",
                "Origin": BASE,
                "Referer": f"{BASE}/downloads/details/id/{url.itemId}/",
            }
        )

    def init(self):
        logger.info(f"Initializing TSRDownload for: {self.url.url}")
        self._set_session_cookie(self.sessionId)
        ticket, ticket_path = self.__getTSRDLTicket()
        self.TSRDLTicket = ticket
        self.__visitTicketPage(ticket_path)
        self.ticketInitializedTime = time.time()

    def current_session_id(self) -> str:
        return self.session.cookies.get("tsrdlsession") or self.sessionId or ""

    def download(self, downloadPath: str) -> str:
        logger.info(f"Starting download for: {self.url.url}")
        downloadUrl = self.__getDownloadUrl()
        logger.debug(f"Got downloadUrl: {downloadUrl}")

        part_path = os.path.join(downloadPath, f"tsr-{self.url.itemId}.part")
        startingBytes = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        logger.debug(f"Got startingBytes: {startingBytes}")

        request = http_client.get(
            downloadUrl,
            sess=self.session,
            stream=True,
            headers={"Range": f"bytes={startingBytes}-"},
            timeout=(10, 120),
            retries=2,
        )
        request.raise_for_status()
        logger.debug(f"Request status is: {request.status_code}")

        fileName = stripForbiddenCharacters(self.__fileNameFromResponse(request))
        final_path = os.path.join(downloadPath, fileName)
        named_part = os.path.join(downloadPath, f"{fileName}.part")
        if part_path != named_part and os.path.exists(part_path):
            if os.path.exists(named_part):
                os.replace(part_path, named_part)
            else:
                os.rename(part_path, named_part)
            part_path = named_part
        elif part_path != named_part:
            part_path = named_part

        mode = "ab" if startingBytes and request.status_code == 206 else "wb"
        if mode == "wb" and os.path.exists(part_path):
            startingBytes = 0

        with open(part_path, mode) as file:
            for chunk in request.iter_content(CHUNK):
                if chunk:
                    file.write(chunk)

        if os.path.exists(final_path):
            os.replace(part_path, final_path)
        else:
            os.rename(part_path, final_path)
        return fileName

    def _set_session_cookie(self, session_id: str) -> None:
        if not session_id:
            return
        self.session.cookies.set(
            "tsrdlsession",
            session_id,
            domain=".thesimsresource.com",
            path="/",
        )

    def __fileNameFromResponse(self, response) -> str:
        disposition = response.headers.get("Content-Disposition", "")
        match = re.search(r'filename="(.+)"', disposition)
        if match:
            return match.group(1)
        return f"tsr-{self.url.itemId}.zip"

    def __getDownloadUrl(self) -> str:
        elapsed = time.time() - self.ticketInitializedTime
        if elapsed < POLL_START_S:
            time.sleep(POLL_START_S - elapsed)

        deadline = self.ticketInitializedTime + POLL_TIMEOUT_S
        last_error = "Invalid download ticket"
        while time.time() < deadline:
            response = http_client.get(
                f"{BASE}/ajax.php?c=downloads&a=getdownloadurl&ajax=1"
                f"&itemid={self.url.itemId}&mid=0&lk=0&ticket={self.TSRDLTicket}",
                sess=self.session,
                retries=1,
            )
            response.raise_for_status()
            responseJSON = response.json()
            err = responseJSON.get("error")
            if err == "" and responseJSON.get("url"):
                return responseJSON["url"]
            last_error = err or "Unknown download error"
            if err and err != "Invalid download ticket":
                raise RuntimeError(last_error)
            time.sleep(POLL_INTERVAL_S + random.uniform(0, POLL_JITTER_S))

        if last_error == "Invalid download ticket":
            raise InvalidDownloadTicket(
                f"{BASE}/ajax.php?c=downloads&a=getdownloadurl",
                self.session.cookies,
            )
        raise RuntimeError(last_error)

    def __visitTicketPage(self, ticket_path: str | None) -> None:
        path = ticket_path or f"/downloads/download/itemId/{self.url.itemId}/ticket/{self.TSRDLTicket}"
        if not path.startswith("http"):
            path = BASE + path
        logger.info(f"Opening ticket page for: {self.url.url}")
        response = http_client.get(path, sess=self.session)
        response.raise_for_status()
        new_sid = self.session.cookies.get("tsrdlsession")
        if new_sid:
            self.sessionId = new_sid
            logger.debug(f"Session cookie after ticket page: {new_sid}")

    def __getTSRDLTicket(self) -> tuple[str, str | None]:
        logger.info(f"Getting download ticket for: {self.url.url}")
        response = http_client.get(
            f"{BASE}/ajax.php?c=downloads&a=initDownload"
            f"&itemid={self.url.itemId}&format=zip",
            sess=self.session,
        )
        response.raise_for_status()
        data = response.json()
        ticket = data.get("ticket")
        if not ticket:
            raise RuntimeError(f"initDownload missing ticket: {data}")
        return ticket, data.get("url")
