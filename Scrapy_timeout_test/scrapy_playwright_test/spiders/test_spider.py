import scrapy
import time
from scrapy_playwright.page import PageMethod

class TestSpider(scrapy.Spider):
    name = "test_spider"

    def __init__(self, urls=None, mode="http", stats=None, timeout=30, **kwargs):
        super().__init__(**kwargs)
        self.urls = urls.split(",") if isinstance(urls, str) else (urls or [])
        self.mode = mode
        self.timeout = timeout
        # Initialize stats dict with separate lists
        self.stats = stats or {
            "durations_success": [],
            "durations_fail": [],
            "success": 0,
            "failed": 0,
        }
        self.logger.info(f"[Spider init] URLs={len(self.urls)}, mode={self.mode}, timeout={self.timeout}s")

    def start_requests(self):
        for url in self.urls:
            meta = {"start_time": time.time()}

            if self.mode == "http":
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    errback=self.errback,
                    meta=meta,
                    dont_filter=True,
                )
            else:
                # Playwright modes
                meta.update({
                    "playwright": True,
                    "playwright_context": self.mode,
                    "playwright_include_page": False,
                })
                if self.mode == "chrome-no-media":
                    meta["playwright_page_methods"] = [
                        PageMethod(
                            "route",
                            "**/*",
                            lambda route, request: (
                                route.abort() if request.resource_type in ("image", "media", "font") else route.continue_()
                            ),
                        )
                    ]
                yield scrapy.Request(
                    url,
                    callback=self.parse,
                    errback=self.errback,
                    meta=meta,
                    dont_filter=True,
                )

    async def parse(self, response):
        dur = time.time() - response.meta.get("start_time", time.time())
        # Strict success condition: status 200, non-empty text, and within timeout
        if response.status == 200 and len(response.text) > 0 and dur <= self.timeout:
            self.stats["durations_success"].append(dur)
            self.stats["success"] += 1
        else:
            # treat as failure
            self.stats["durations_fail"].append(min(dur, self.timeout))
            self.stats["failed"] += 1
        self.logger.debug(f"[parse] {response.url} | dur={dur:.2f}s | status={response.status}")

    def errback(self, failure):
        dur = time.time() - failure.request.meta.get("start_time", time.time())
        # clamp to timeout
        self.stats["durations_fail"].append(min(dur, self.timeout))
        self.stats["failed"] += 1
        self.logger.warning(f"[errback] {failure.request.url} failed after {dur:.2f}s")
