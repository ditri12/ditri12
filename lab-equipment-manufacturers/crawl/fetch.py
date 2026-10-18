#!/usr/bin/env python3
"""Fetch a list of web pages (plain HTTP or rendered with Playwright) and save
HTML, extracted text, extracted links and an index.json.

Usage: python fetch.py --jobs crawl/jobs/lists.json --out research/sources/lists [--workers 4] [--gzip]

Job file: JSON list of objects:
  {"id": "dutscher_brands", "url": "https://...", "render": true,
   "scroll": true, "click": "button.load-more", "click_max": 60, "wait_ms": 1500}
"""
import argparse
import gzip
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,fr;q=0.5",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def slug(s):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    return s[:120] or "page"


def html_to_text(html):
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "template"]):
        t.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if ln:
            out.append(ln)
            blank = 0
        else:
            blank += 1
            if blank == 1:
                out.append("")
    return "\n".join(out).strip() + "\n"


def extract_links(html, base):
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        txt = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        title = (a.get("title") or "").strip()
        img = a.find("img")
        alt = (img.get("alt") or "").strip() if img else ""
        links.append({"text": txt, "title": title, "alt": alt, "href": urljoin(base, href)})
    return links


def fetch_http(job):
    url = job["url"]
    r = requests.get(url, headers=HEADERS, timeout=job.get("timeout", 60), allow_redirects=True)
    ctype = r.headers.get("content-type", "")
    if "charset" not in ctype.lower():
        r.encoding = r.apparent_encoding or "utf-8"
    return {"status": r.status_code, "final_url": r.url, "content_type": ctype, "html": r.text}


def fetch_render(browser, job):
    url = job["url"]
    ctx = browser.new_context(user_agent=UA, viewport={"width": 1400, "height": 1000},
                              locale=job.get("locale", "en-US"))
    page = ctx.new_page()
    status = None
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=job.get("timeout", 90) * 1000)
        status = resp.status if resp else None
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        page.wait_for_timeout(job.get("wait_ms", 1500))
        if job.get("scroll", True):
            last = -1
            for _ in range(job.get("scroll_max", 40)):
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(400)
                h = page.evaluate("document.body ? document.body.scrollHeight : 0")
                if h == last:
                    break
                last = h
        sel = job.get("click")
        if sel:
            for _ in range(job.get("click_max", 60)):
                try:
                    loc = page.locator(sel).first
                    if loc.count() == 0 or not loc.is_visible():
                        break
                    loc.click(timeout=5000)
                    page.wait_for_timeout(job.get("click_wait_ms", 1500))
                except Exception:
                    break
        html = page.content()
        return {"status": status, "final_url": page.url, "content_type": "text/html (rendered)",
                "html": html, "title": page.title()}
    finally:
        page.close()
        ctx.close()


def save(job, res, out, use_gzip):
    jid = slug(job["id"])
    html = res.get("html") or ""
    if use_gzip:
        with gzip.open(os.path.join(out, jid + ".html.gz"), "wt", encoding="utf-8") as f:
            f.write(html)
    else:
        with open(os.path.join(out, jid + ".html"), "w", encoding="utf-8") as f:
            f.write(html)
    is_html = "html" in (res.get("content_type") or "") or html.lstrip()[:1] == "<"
    if is_html:
        with open(os.path.join(out, jid + ".txt"), "w", encoding="utf-8") as f:
            f.write(html_to_text(html))
        links = extract_links(html, res.get("final_url") or job["url"])
        with open(os.path.join(out, jid + ".links.json"), "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=0)
    else:
        links = []
    title = res.get("title")
    if title is None and is_html:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return {"id": jid, "url": job["url"], "final_url": res.get("final_url"), "status": res.get("status"),
            "content_type": res.get("content_type"), "title": title, "bytes": len(html.encode("utf-8")),
            "links": len(links), "render": bool(job.get("render")), "error": None}


def follow_jobs(job, out):
    """Depth-1 expansion: return extra jobs for links of the fetched page matching job['follow'] (regex on href or text)."""
    pat = job.get("follow")
    if not pat:
        return []
    jid = slug(job["id"])
    path = os.path.join(out, jid + ".links.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        links = json.load(f)
    rx = re.compile(pat, re.I)
    from urllib.parse import urlparse
    host = urlparse(job["url"]).netloc.lower().replace("www.", "")
    seen, extra = set(), []
    for l in links:
        href = l["href"].split("#")[0]
        if not href.startswith("http") or href in seen:
            continue
        h = urlparse(href).netloc.lower().replace("www.", "")
        if not job.get("follow_any_host") and h != host:
            continue
        if rx.search(href) or rx.search(l.get("text") or "") or rx.search(l.get("title") or ""):
            seen.add(href)
            extra.append({"id": jid + "__" + slug(re.sub(r"^https?://", "", href)), "url": href,
                          "render": job.get("follow_render", job.get("render", False)),
                          "scroll": job.get("scroll", True), "timeout": job.get("timeout", 60)})
        if len(extra) >= job.get("follow_max", 15):
            break
    return extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--gzip", action="store_true")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests per worker")
    args = ap.parse_args()
    with open(args.jobs, encoding="utf-8") as f:
        jobs = json.load(f)
    os.makedirs(args.out, exist_ok=True)
    index_path = os.path.join(args.out, "index.json")
    index = {}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            for e in json.load(f):
                index[e["id"]] = e
    t0 = time.time()
    for pass_no in (1, 2):
        run_pass(jobs, index, index_path, args)
        extra = []
        for j in jobs:
            e = index.get(slug(j["id"]))
            if e and not e.get("error"):
                extra.extend(follow_jobs(j, args.out))
        extra = [j for j in extra if slug(j["id"]) not in index]
        if pass_no == 1 and extra:
            print(f"follow pass: {len(extra)} extra pages", flush=True)
            jobs = extra
        else:
            break
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(list(index.values()), f, ensure_ascii=False, indent=1)
    ok = sum(1 for e in index.values() if e.get("status") and 200 <= e["status"] < 400)
    print(f"done: {len(index)} pages, {ok} ok, {time.time() - t0:.0f}s", flush=True)


def run_pass(jobs, index, index_path, args):
    http_jobs = [j for j in jobs if not j.get("render")]
    render_jobs = [j for j in jobs if j.get("render")]

    def run_http(job):
        time.sleep(args.delay)
        try:
            res = fetch_http(job)
            return save(job, res, args.out, args.gzip)
        except Exception as e:
            return {"id": slug(job["id"]), "url": job["url"], "status": None, "error": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(run_http, j) for j in http_jobs]
        for i, fu in enumerate(as_completed(futs), 1):
            e = fu.result()
            index[e["id"]] = e
            print(f"[http {i}/{len(http_jobs)}] {e['id']} -> {e.get('status')} {e.get('error') or ''}", flush=True)
            if i % 25 == 0:
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(list(index.values()), f, ensure_ascii=False, indent=1)

    if render_jobs:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for i, job in enumerate(render_jobs, 1):
                try:
                    res = fetch_render(browser, job)
                    e = save(job, res, args.out, args.gzip)
                except Exception as ex_:
                    e = {"id": slug(job["id"]), "url": job["url"], "status": None,
                         "error": f"{type(ex_).__name__}: {ex_}"}
                    traceback.print_exc()
                index[e["id"]] = e
                print(f"[render {i}/{len(render_jobs)}] {e['id']} -> {e.get('status')} {e.get('error') or ''}", flush=True)
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(list(index.values()), f, ensure_ascii=False, indent=1)
            browser.close()


if __name__ == "__main__":
    main()
