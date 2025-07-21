import argparse
import csv
import statistics
import time
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import psutil
from DrissionPage import ChromiumPage, ChromiumOptions
import math

# 读取URL
def load_urls(file='url_timeout_list(HTTP).txt', limit=10000):        # 根据Chrome和HTTP模式切换URL列表
    with open(file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls[:limit]

# 资源监控器
class ResourceMonitor:
    def __init__(self):
        self.cpu_samples = []
        self.mem_samples = []
        self.disk_io_start = psutil.disk_io_counters().read_bytes
        self.net_io_start  = psutil.net_io_counters().bytes_recv
        self._running = False

    def _sample(self):
        while self._running:
            self.cpu_samples.append(psutil.cpu_percent(interval=1))
            self.mem_samples.append(psutil.virtual_memory().used / 1024 / 1024)

    def start(self):
        self._running = True
        threading.Thread(target=self._sample, daemon=True).start()

    def stop(self, total_elapsed):
        self._running = False
        time.sleep(1)
        disk_end = psutil.disk_io_counters().read_bytes
        net_end  = psutil.net_io_counters().bytes_recv
        avg_cpu = sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0
        avg_mem = sum(self.mem_samples) / len(self.mem_samples) if self.mem_samples else 0
        disk_mb = (disk_end - self.disk_io_start) / 1024 / 1024
        net_mb  = (net_end  - self.net_io_start)  / 1024 / 1024
        disk_speed = disk_mb / total_elapsed if total_elapsed else 0
        net_speed  = net_mb  / total_elapsed if total_elapsed else 0
        return round(avg_cpu,2), round(avg_mem,2), round(disk_speed,2), round(net_speed,2)

# fetch with timeout

def fetch(url, mode, timeout):
    try:
        start = time.time()
        ok = False
        if mode == 'http':
            import requests
            from requests.adapters import HTTPAdapter, Retry
            sess = requests.Session()
            sess.mount('http://', HTTPAdapter(max_retries=Retry(total=0)))
            sess.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
            r = sess.get(url, timeout=timeout)
            ok = (r.status_code == 200 and len(r.text) > 0)
        else:
            co = ChromiumOptions()
            co.remote_port = 9222
            if mode == 'chrome-no-js':
                co.set_argument('--disable-javascript')
            elif mode == 'chrome-no-media':
                co.set_browser_path('chrome')
                co.set_argument('--blink-settings=imagesEnabled=false')
                co.set_argument('--disable-plugins')
            page = ChromiumPage(co)
            page.get(url, timeout=timeout)
            html = page.html
            ok = bool(html and len(html) > 0)
            page.close()
        dur = time.time() - start
        # clamp failure durations
        if ok and dur <= timeout:
            return dur, True
        else:
            return min(dur, timeout), False
    except Exception:
        dur = time.time() - start
        return min(dur, timeout), False

# run_test with timeout

def run_test(mode, concurrency, timeout):
    urls = load_urls()
    durations_success = []
    durations_fail = []
    succ = 0

    mon = ResourceMonitor()
    start_wall = time.time()
    mon.start()

    def worker(u):
        return fetch(u, mode, timeout)

    with ThreadPoolExecutor(concurrency) as ex:
        for elapsed, ok in tqdm(ex.map(worker, urls), total=len(urls), desc=f'{mode}@{concurrency}@{timeout}s'):
            if ok:
                durations_success.append(elapsed)
                succ += 1
            else:
                durations_fail.append(elapsed)

    wall_time = time.time() - start_wall
    cpu, mem, disk_speed, net_speed = mon.stop(wall_time)

    # 统计成功时延
    n = len(durations_success)
    avg = round(statistics.mean(durations_success),3) if n else 0
    p50 = round(statistics.median(durations_success),3) if n else 0
    p95 = round(sorted(durations_success)[max(0, min(n-1, math.ceil(0.95*n)-1))],3) if n else 0
    sr = round(succ / len(urls),3)
    throughput = round(succ / wall_time, 2) if wall_time > 0 else 0

    os.makedirs('results', exist_ok=True)
    lp = 'results/log.csv'
    write_hdr = not os.path.exists(lp)
    with open(lp,'a',newline='',encoding='utf-8') as f:
        w = csv.writer(f)
        if write_hdr:
            w.writerow(['Mode','Concurrency','Timeout(s)','AvgSucc(s)','P50Succ(s)','P95Succ(s)','SuccessRate'])
        w.writerow([f'DrissionPage-{mode}',concurrency,timeout,avg,p50,p95,sr])

    print(f"[Done] {mode}@{concurrency}@{timeout}s: AvgSucc={avg}s, P50Succ={p50}s, P95Succ={p95}s, SR={sr}")

if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['http','chrome','chrome-no-js','chrome-no-media'], required=True)
    p.add_argument('--concurrency', type=int, default=4)
    p.add_argument('--timeout', type=int, default=10, help='超时阈值(秒)')
    args = p.parse_args()
    run_test(args.mode, args.concurrency, args.timeout)
