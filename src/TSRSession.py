from __future__ import annotations
import requests, webbrowser, os
from pathlib import Path
from exceptions import InvalidCaptchaCode
from typing import Optional
from logger import logger
from config import CURRENT_DIR

CAPTCHA_IMAGE_PATH = Path(CURRENT_DIR) / "captcha.png"
CAPTCHA_IMAGE_MAGIC = b"\x89PNG\r\n\x1a\n"


class TSRSession:
    @classmethod
    def __init__(self, sessionId: Optional[str] = None) -> None:
        logger.debug("Creating new TSRSession")
        self.session = requests.Session()
        if sessionId is not None:
            logger.debug("SessionId is not none")
            if self.__isValidSessionId(sessionId):
                logger.debug("SessionId is valid")
                self.tsrdlsession = sessionId
                return

        self.tsrdlsession = ""
        self.__getTSRDLTicketCookie()
        try:
            self.__saveCaptchaImage()
        except Exception as e:
            logger.warning(
                f"TSR captcha service unavailable ({e}). Skipping captcha. "
                "Downloads may still work."
            )
        else:
            self.__openImageInBrowser()
            print("Please enter captcha code:")
            captchaInput = input(">> ")
            if not self.__tryCaptchaCode(captchaInput):
                raise InvalidCaptchaCode

        self.tsrdlsession = self.session.cookies.get_dict().get("tsrdlsession")
        if not self.tsrdlsession:
            raise RuntimeError(
                "No tsrdlsession cookie received from TSR. Cannot create session."
            )

    @classmethod
    def __tryCaptchaCode(self, code: str) -> bool:
        logger.debug(f"Testing captcha code: {code}")
        r = self.session.post(
            "https://www.thesimsresource.com/downloads/session/itemId/1646133",
            data={"captchavalue": code},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www.thesimsresource.com",
            },
            allow_redirects=True,
        )

        isDownloadUrl = (
            r.url == "https://www.thesimsresource.com/downloads/download/itemId/1646133"
        )
        logger.debug(f"Captcha successfully completed: {isDownloadUrl}")
        return isDownloadUrl

    @classmethod
    def __isValidSessionId(self, sessionId: str) -> bool:
        logger.debug(f"Checking if SessionId: {sessionId} is valid")
        self.__getTSRDLTicketCookie()
        r = self.session.get(
            "https://www.thesimsresource.com/downloads/download/itemId/1646133",
            cookies={"tsrdlsession": sessionId},
        )
        return (
            r.url == "https://www.thesimsresource.com/downloads/download/itemId/1646133"
        )

    @classmethod
    def __getCaptchaImage(self) -> requests.Request:
        logger.debug("Getting captcha image")
        self.session.get(
            "https://www.thesimsresource.com/downloads/session/itemId/1646133"
        )
        return self.session.get(
            "https://www.thesimsresource.com/downloads/captcha-image"
        )

    @classmethod
    def __saveCaptchaImage(self):
        logger.debug("Saving captcha image")
        captcha_image = self.__getCaptchaImage()
        content = captcha_image.content

        content_type = captcha_image.headers.get("Content-Type", "").lower()
        if captcha_image.status_code != 200 or "image" not in content_type:
            raise RuntimeError(
                f"TSR returned HTTP {captcha_image.status_code} ({content_type}) for "
                f"{captcha_image.url} instead of a captcha image. "
                "The captcha service is currently broken on TSR's side."
            )
        if len(content) == 0:
            raise RuntimeError("Captcha has a length of 0.")
        if not content.startswith(CAPTCHA_IMAGE_MAGIC):
            raise RuntimeError(
                "Captcha response is not a PNG image. TSR captcha service may be broken."
            )

        CAPTCHA_IMAGE_PATH.write_bytes(content)
        logger.debug(f"Captcha image saved to {CAPTCHA_IMAGE_PATH}")

    @classmethod
    def __openImageInBrowser(self) -> None:
        webbrowser.open_new_tab(CAPTCHA_IMAGE_PATH.resolve().as_uri())

    @classmethod
    def __getTSRDLTicketCookie(self) -> str:
        logger.debug("Getting TSRDLTicket cookie")
        response = self.session.get(
            f"https://www.thesimsresource.com/ajax.php?c=downloads&a=initDownload&itemid=1646133&setItems=&format=zip"
        )
        return response.cookies.get("tsrdlticket")
