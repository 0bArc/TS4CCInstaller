from __future__ import annotations
import sys
from multiprocessing import freeze_support


def run_cli():
    """Legacy clipboard-monitoring downloader (deprecated).

    Kept for reference / power users behind the `--cli` flag.
    """
    from TSRUrl import TSRUrl
    from TSRDownload import TSRDownload
    from logger import logger
    from exceptions import InvalidURL, InvalidCaptchaCode
    from multiprocessing import Pool
    from TSRSession import TSRSession
    from config import CONFIG, CURRENT_DIR, resolve_download_dir, needs_onboarding
    import clipboard, time, os

    if needs_onboarding(CONFIG):
        raise SystemExit(
            "Setup incomplete. Run the app once without --cli to finish onboarding, "
            "or set downloadDirectory + setupComplete in config.json."
        )
    download_dir = resolve_download_dir(CONFIG)

    def processTarget(url: TSRUrl, tsrdlsession: str, downloadPath: str):
        try:
            downloader = TSRDownload(url, tsrdlsession)
            downloader.init()
            refreshed = downloader.current_session_id()
            if refreshed and refreshed != tsrdlsession:
                tsrdlsession = refreshed
                open(CURRENT_DIR + "/session", "w").write(tsrdlsession)
            file_name = downloader.download(downloadPath)
            from sims_install import install_into_library
            import library_store

            files = install_into_library(downloadPath, file_name)
            library_store.record_install(
                item_id=url.itemId,
                title=f"Item {url.itemId}",
                files=files,
                url=url.url,
            )
            logger.info(f"Completed download for: {url.url}")
        except Exception as e:
            logger.error(e)

        return url

    def callback(url: TSRUrl):
        logger.debug(f"Removing {url.itemId} from queue")
        runningDownloads.remove(url.itemId)
        updateUrlFile()
        if len(runningDownloads) == 0:
            logger.info("All downloads have been completed")

    def updateUrlFile():
        logger.debug(f"Updating URL file")
        if CONFIG["saveDownloadQueue"]:
            open(CURRENT_DIR + "/urls.txt", "w").write(
                "\n".join(
                    [
                        DETAILS_URL + str(id)
                        for id in [*runningDownloads, *downloadQueue, *vipItemIds]
                    ]
                )
            )

    DETAILS_URL = "https://www.thesimsresource.com/downloads/details/id/"
    lastPastedText = ""
    runningDownloads: list[int] = []
    downloadQueue: list[int] = []
    vipItemIds: list[int] = []

    logger.debug(f"downloadDirectory: {download_dir}")
    logger.debug(f'maxActiveDownloads: {CONFIG["maxActiveDownloads"]}')
    logger.debug(f'saveDownloadQueue: {CONFIG["saveDownloadQueue"]}')
    logger.debug(f'debug: {CONFIG["debug"]}')

    if not os.path.exists(download_dir):
        raise FileNotFoundError(
            f"The directory: {download_dir} does not exist! Please make sure the directory exists or the directory is set correctly in the config."
        )

    session = None
    sessionId = None
    if os.path.exists(CURRENT_DIR + "/session"):
        sessionId = open(CURRENT_DIR + "/session", "r").read()

    while session is None:
        try:
            session = TSRSession(sessionId)
            if hasattr(session, "tsrdlsession") and session.tsrdlsession != "":
                open(CURRENT_DIR + "/session", "w").write(session.tsrdlsession)
                logger.info("Session with captcha successfully created")
        except InvalidCaptchaCode:
            logger.error(
                "Invalid captcha code entered, please make sure the code is correct"
            )
            sessionId = None
        except Exception as e:
            logger.error(f"Failed to create TSR session: {e}")
            sys.exit(1)

    if os.path.exists(CURRENT_DIR + "/urls.txt") and CONFIG["saveDownloadQueue"]:
        for url in open(CURRENT_DIR + "/urls.txt", "r").read().split("\n"):
            try:
                url = TSRUrl(url)
                if url.isVipExclusive():
                    logger.info(f"Url is still a VIP exclusive: {url.url}")
                    vipItemIds.append(url.itemId)
                    continue

                if url.itemId in downloadQueue:
                    continue
                downloadQueue.append(url.itemId)
            except InvalidURL:
                continue

    logger.info(
        "The tool is now ready to be used. Simply copy links from The Sims Resource and the tool will automatically download them for you."
    )

    while True:
        pastedText = clipboard.paste()
        if lastPastedText == pastedText:
            for id in downloadQueue:
                if len(runningDownloads) == CONFIG["maxActiveDownloads"]:
                    break

                url = TSRUrl(DETAILS_URL + str(id))
                runningDownloads.append(url.itemId)
                downloadQueue.remove(url.itemId)
                logger.info(f"Moved {url.url} from queue to downloading")
                pool = Pool(1)
                pool.apply_async(
                    processTarget,
                    args=[
                        url,
                        session.tsrdlsession,
                        download_dir,
                    ],
                    callback=callback,
                )

                if len(downloadQueue) == 0:
                    logger.info("Queue is now empty")
        else:
            lastPastedText = pastedText
            for line in pastedText.split("\n"):
                try:
                    url = TSRUrl(line)
                except InvalidURL:
                    continue

                if url.itemId in runningDownloads:
                    logger.info(f"Url is already being downloaded: {url.url}")
                    continue
                if url.itemId in downloadQueue:
                    logger.info(
                        f"Url is already in queue (#{downloadQueue.index(url.itemId)}): {url.url}"
                    )
                    continue

                if url.itemId in vipItemIds:
                    logger.info(f"Url is currently a VIP exclusive: {url.url}")
                    continue
                elif url.isVipExclusive():
                    logger.info(
                        "Url is currently a VIP exclusive, "
                        + (
                            "storing url for later: "
                            if CONFIG["saveDownloadQueue"]
                            else "unable to download: "
                        )
                        + f"{url.url}"
                    )
                    vipItemIds.append(url.itemId)
                    updateUrlFile()
                    continue

                requirements = TSRUrl.getRequiredItems(url)
                logger.info(f"Found valid url in clipboard: {url.url}")
                if len(requirements) != 0:
                    logger.info(f"{url.url} has {len(requirements)} requirements")
                for url in [url, *requirements]:
                    if url.url in runningDownloads:
                        logger.info(f"Url is already being downloaded: {url.itemId}")
                        continue
                    if url.url in downloadQueue:
                        logger.info(
                            f"Url is already in queue (#{downloadQueue.index(url.itemId)}): {url.url}"
                        )
                        continue
                    if len(runningDownloads) == CONFIG["maxActiveDownloads"]:
                        logger.info(
                            f"Added url to queue (#{len(downloadQueue)}): {url.url}"
                        )
                        downloadQueue.append(url.itemId)
                    else:
                        runningDownloads.append(url.itemId)
                        pool = Pool(1)
                        pool.apply_async(
                            processTarget,
                            args=[
                                url,
                                session.tsrdlsession,
                                download_dir,
                            ],
                            callback=callback,
                        )
                updateUrlFile()

        time.sleep(0.1)


def _windows_app_id() -> None:
    """Un-group from python.exe so the taskbar can show our icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "CCInstaller.TSRCommunityManager.1"
        )
    except Exception:
        pass


if __name__ == "__main__":
    freeze_support()
    _windows_app_id()
    if "--cli" in sys.argv:
        run_cli()
    else:
        from webapp import main as web_main

        web_main()
