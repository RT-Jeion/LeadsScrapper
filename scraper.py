"""
HTML scraping and data extraction utilities for Brave Search results.
"""

import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


def get_time_parts(now=None):
    """
    Get formatted time parts for timestamp storage.
    
    Args:
        now: Optional datetime object (uses current time if None)
        
    Returns:
        dict: Contains formatted day, time, and year strings
              day format: "June 22, Monday"
              time format: "06:58:30 PM"
              year format: "2026"
    """
    if now is None:
        now = datetime.now()

    return {
        "day": now.strftime("%B %d, %A"),
        "time": now.strftime("%I:%M:%S %p"),
        "year": now.strftime("%Y"),
    }


def clean_text(value):
    """
    Extract and clean text from a BeautifulSoup element.
    
    Args:
        value: BeautifulSoup element
        
    Returns:
        str: Cleaned text with single spaces between words
    """
    return " ".join(value.stripped_strings) if value else ""


def extract_username(url, snippet_text=""):
    """
    Extract Instagram username from URL or snippet text.
    
    Args:
        url: Instagram profile URL
        snippet_text: Search result snippet text
        
    Returns:
        str: Extracted username or empty string
    """
    match = re.search(r"@([A-Za-z0-9._]+)", snippet_text)
    if match:
        return match.group(1)

    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0] if parts else ""


def extract_instagram_profile_data(result):
    """
    Extract Instagram profile information from a Brave Search result element.
    
    Args:
        result: BeautifulSoup element containing a search result
        
    Returns:
        dict: Profile data with name, username, followers, following, posts, bio, url, snippet
              Returns None if result is not a valid Instagram profile
    """
    link = result.select_one("div.result-content > a[href]")
    if not link:
        return None

    url = link["href"]
    title = clean_text(link.select_one("div.title")) or link.get("title", "")
    snippet = clean_text(result.select_one("div.generic-snippet .content"))
    site_name = clean_text(link.select_one("div.site-name-content .desktop-small-semibold"))
    display_url = clean_text(link.select_one("cite.snippet-url"))

    username = extract_username(url, f"{title} {snippet} {display_url}")
    name = title.split("(@")[0].split("|")[0].strip()

    counts = {
        "followers": None,
        "following": None,
        "posts": None,
    }
    bio = ""
    count_match = re.search(
        r"(?P<followers>[\d.,]+[KMB]?)\s+Followers,\s+(?P<following>[\d.,]+[KMB]?)\s+Following,\s+(?P<posts>[\d.,]+[KMB]?)\s+Posts",
        snippet,
        re.IGNORECASE,
    )
    if count_match:
        counts.update(count_match.groupdict())
        remainder = snippet[count_match.end():].strip()
        remainder = remainder.lstrip("-–—: ").strip()
        if remainder:
            bio_match = re.search(r'[:\-]?\s*"(?P<bio>.+?)"\s*$', remainder)
            if bio_match:
                bio = bio_match.group("bio").strip()
            else:
                bio = remainder.strip('"').strip()

    return {
        "type": "instagram_profile",
        "name": name,
        "username": username,
        "followers": counts["followers"],
        "following": counts["following"],
        "posts": counts["posts"],
        "bio": bio,
        "url": url,
        "site": site_name or "Instagram",
        "snippet": snippet,
    }


def extract_instagram_profiles_from_html(html_content, search_query=None):
    """
    Extract all Instagram profile results from Brave Search HTML.
    
    Args:
        html_content: Full HTML page content
        search_query: Optional search query to tag profiles with source
        
    Returns:
        list: Profiles formatted for MongoDB storage
    """
    soup = BeautifulSoup(html_content, "lxml")
    results = soup.select('div.snippet[data-type="web"]')
    instagram_results = []

    for result in results:
        link = result.select_one("div.result-content > a[href]")
        if not link:
            continue

        url = link["href"]
        if "instagram.com" not in url.lower():
            continue

        instagram_results.append(result)

    profile_data = []

    for _, result in enumerate(instagram_results, 1):
        data = extract_instagram_profile_data(result)
        if not data:
            continue

        profile = {
            "name": data["name"],
            "username": data["username"],
            "link": data["url"],
            "followers": data["followers"],
            "following": data["following"],
            "posts": data["posts"],
            "bio": data["bio"],
            "snippet": data["snippet"],
        }
        if search_query:
            profile["search_queries"] = [search_query]

        profile_data.append(profile)

    return profile_data


def extract_related_queries_from_html(html_content, source_query=None):
    """
    Extract related search queries from Brave's "Related queries" section.
    
    Only searches within div#related-queries to avoid picking up pagination
    or other unrelated search links.
    
    Args:
        html_content: Full HTML page content
        source_query: Optional source query to filter out (avoid duplicates)
        
    Returns:
        list: Related query strings found
    """
    soup = BeautifulSoup(html_content, "lxml")
    related_queries = []
    seen_queries = set()

    related_section = soup.select_one("div#related-queries")
    if not related_section:
        return related_queries

    for link in related_section.select('a.related-query[href*="source=relatedQueries"]'):
        href = link.get("href", "")
        if "search?q=" not in href:
            continue

        parsed_href = urlparse(href)
        query_params = parse_qs(parsed_href.query)
        query_value = query_params.get("q", [""])[0].strip()
        if not query_value:
            continue

        if source_query and query_value.lower() == source_query.lower():
            continue

        if query_value.lower() in seen_queries:
            continue

        seen_queries.add(query_value.lower())
        related_queries.append(query_value)

    return related_queries
