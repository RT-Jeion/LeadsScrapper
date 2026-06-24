import asyncio
import os
import random
import subprocess
import sys
import time

from playwright.async_api import async_playwright

from logger import log_line, section
from page_scraper import (
    extract_instagram_profiles_from_html,
    extract_related_queries_from_html,
    get_mongo_collections,
    save_profiles_to_mongodb,
    save_related_queries_to_mongodb,
    save_searched_query_to_mongodb,
)


def ensure_brave_browser_running():
    script_path = os.path.join(os.path.dirname(__file__), "start_brave_debug.sh")
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Brave launcher script not found: {script_path}")

    print("\n" + "=" * 72)
    print("Starting Brave browser for remote debugging")
    print("=" * 72)

    subprocess.Popen(
        ["bash", script_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(20):
        try:
            browser = subprocess.run(
                ["curl", "-s", "http://127.0.0.1:9222/json/version"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            if browser.returncode == 0:
                print("Brave browser is ready for connection.")
                print("=" * 72 + "\n")
                return
        except Exception:
            pass
        time.sleep(1)

    print("Brave did not become ready in time. Please check the launcher script.")
    print("=" * 72 + "\n")


async def main():
    collections = get_mongo_collections()
    query = input("Enter your search Query:\n").strip()
    if not query:
        print("No query entered.")
        return

    offset_range = 5

    ensure_brave_browser_running()
    section("Instagram Lead Scraper Started")
    log_line("INFO", "MongoDB target: Leads / Instra_Profiles")
    log_line("INFO", f"Search query: {query}")
    log_line("INFO", f"Total offsets to process: {offset_range}")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0]
        log_line("OK", "Connected to existing browser debug session")

        for i in range(offset_range):
            offset = str(i + 1)
            section(f"Offset {offset}/{offset_range}")

            sleep_time = random.uniform(7, 10)
            log_line("WAIT", f"Sleeping for {sleep_time:.2f} sec before next request")
            await asyncio.sleep(sleep_time)

            formatted_url = f"https://search.brave.com/search?q={query.replace(' ', '+')}&offset={offset}&spellcheck=0"
            log_line("NAV", f"Searching Brave for query='{query}' at offset={offset}")
            await page.goto(formatted_url, wait_until="domcontentloaded")
            log_line("OK", "Page loaded")

            html_content = await page.content()
            file_name = f"html_pages/page_no_{offset}.html"
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(html_content)

            log_line("OK", f"HTML saved to {file_name}")

            save_searched_query_to_mongodb(
                query,
                collections["searched_queries"],
                collections["queries"],
            )

            profile_data = extract_instagram_profiles_from_html(html_content, query)
            log_line("INFO", f"Instagram profiles extracted from page: {len(profile_data)}")

            result = save_profiles_to_mongodb(profile_data, collections["profiles"])
            related_queries = extract_related_queries_from_html(html_content, query)
            log_line("INFO", f"Related queries extracted from page: {len(related_queries)}")

            related_result = save_related_queries_to_mongodb(
                related_queries,
                query,
                collections["queries"],
            )

            log_line(
                "DB",
                f"Profiles sync: {result['inserted']} inserted, {result['updated']} updated, {result['skipped']} skipped",
            )
            log_line(
                "DB",
                f"Related queries sync: {related_result['inserted']} inserted, {related_result['skipped']} skipped",
            )

    section("Run Completed")
    log_line("DONE", "All offsets processed successfully")


asyncio.run(main())