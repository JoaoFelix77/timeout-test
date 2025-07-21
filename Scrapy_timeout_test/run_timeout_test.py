import os
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "scrapy_playwright_test.settings")

from scrapy.settings import Settings
import scrapy_playwright_test.settings as my_settings
import argparse
import time
import statistics
import psutil
import threading
import csv
from tqdm import tqdm

from scrapy.crawler import CrawlerProcess
from scrapy_playwright_test.spiders.test_spider_new import TestSpider


def load_urls(path="url_timeout_list(Chrome).txt"):              #根据Chrome和HTTP模式切换
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def update_stats(stats, total, pbar):
    now = time.time()
    done = stats["success"] + stats["failed"]
    pbar.n = done; pbar.refresh()

    # compute only on successful durations
    d = stats["durations_success"]
    avg = statistics.mean(d) if d else 0
    p50 = statistics.median(d) if d else 0
    p95 = statistics.quantiles(d, n=100)[94] if len(d) >= 100 else 0

    cpu = psutil.cpu_percent()
    mem_mb = psutil.virtual_memory().used / 1024 / 1024
    disk_curr = psutil.disk_io_counters().read_bytes
    net_io = psutil.net_io_counters()
    net_curr = net_io.bytes_sent + net_io.bytes_recv

    dt = now - stats["last_time"]
    delta_net = net_curr - stats["last_net"]
    net_rate = (delta_net / 1024 / 1024) / dt if dt > 0 else 0

    sr = stats["success"] / done if done > 0 else 0

    tqdm.write(
        f"[Progress] S={stats['success']} F={stats['failed']} | "
        f"avg_succ={avg:.2f}s p50={p50:.2f}s p95={p95:.2f}s | "
        f"CPU={cpu:.1f}% Mem={mem_mb:.1f}MB |  SR={sr:.3f}"
    )
    stats.update({"last_time": now, "last_net": net_curr})
    if done < total:
        threading.Timer(5, update_stats, args=[stats, total, pbar]).start()


def run_spider(mode, urls, concurrency, timeout):
    stats = {
        "durations_success": [],
        "durations_fail": [],
        "success": 0,
        "failed": 0,
        "start_time": time.time(),
        "last_time": time.time(),
        "last_net": (lambda io: io.bytes_sent + io.bytes_recv)(psutil.net_io_counters()),
    }
    total = len(urls)
    pbar = tqdm(total=total, desc="Crawling Progress")
    update_stats(stats, total, pbar)

    settings = Settings()
    settings.setmodule(my_settings)
    settings.set("CONCURRENT_REQUESTS", concurrency)
    settings.set("PLAYWRIGHT_MAX_CONTEXTS", concurrency)
    settings.set("DOWNLOAD_TIMEOUT", timeout)
    settings.set("PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT", timeout * 1000)

    process = CrawlerProcess(settings=settings)
    process.crawl(TestSpider, urls=urls, mode=mode, stats=stats, timeout=timeout)
    process.start()
    pbar.close()
    return stats


def save_stats(stats, mode, timeout, concurrency):
    d = stats["durations_success"]
    avg = statistics.mean(d) if d else 0
    p50 = statistics.median(d) if d else 0
    p95 = statistics.quantiles(d, n=100)[94] if len(d) >= 100 else 0
    cpu = psutil.cpu_percent()
    mem_mb = psutil.virtual_memory().used / 1024 / 1024
    end_net = (lambda io: io.bytes_sent + io.bytes_recv)(psutil.net_io_counters())
    duration = time.time() - stats["start_time"]
    net_rate = ((end_net - stats["last_net"]) / 1024 / 1024) / duration if duration > 0 else 0
    sr = stats["success"] / (stats["success"] + stats["failed"]) if duration > 0 else 0

    os.makedirs("results", exist_ok=True)
    path = "results/performance_logs.csv"
    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow([
                "Mode", "Concurrency", "Timeout(s)","AvgSuccess(s)", "P50Success(s)", "P95Success(s)","SuccessRate"
            ])
        w.writerow([
            mode, concurrency,timeout,
            f"{avg:.3f}", f"{p50:.3f}", f"{p95:.3f}", f"{sr:.3f}"
        ])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["http","chrome","chrome-no-js","chrome-no-media"])
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=my_settings.DOWNLOAD_TIMEOUT)
    args = parser.parse_args()

    urls = load_urls()
    print(f"Start crawl: mode={args.mode}, concurrency={args.concurrency}, timeout={args.timeout}s")
    stats = run_spider(args.mode, urls, args.concurrency, args.timeout)
    save_stats(stats, f"Scrapy-{args.mode}", args.timeout, args.concurrency)
    print("Saved to results/performance_logs.csv")
