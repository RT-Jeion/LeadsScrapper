import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from pymongo import MongoClient

from logger import log_line


def clean_text(value):
    return " ".join(value.stripped_strings) if value else ""


def extract_username(url, snippet_text=""):
    match = re.search(r"@([A-Za-z0-9._]+)", snippet_text)
    if match:
        return match.group(1)

    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0] if parts else ""


def extract_instagram_profile_data(result):
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

    counts = {"followers": None, "following": None, "posts": None}
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
    for result in instagram_results:
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


def get_mongo_collections():
    mongo_uri = "mongodb://localhost:27017/"
    mongo_db_name = "Leads"

    client = MongoClient(mongo_uri)
    db = client[mongo_db_name]
    return {
        "profiles": db["Instra_Profiles"],
        "searched_queries": db["searched_queries"],
        "queries": db["Queries"],
    }


def save_profiles_to_mongodb(profile_data, collection):
    try:
        from pymongo.errors import DuplicateKeyError
    except ImportError:
        DuplicateKeyError = Exception

    inserted_count = 0
    updated_count = 0
    skipped_count = 0

    for profile in profile_data:
        username = profile.get("username")
        if not username:
            log_line("WARN", "Username missing so skipped this record")
            skipped_count += 1
            continue

        existing_profile = collection.find_one({"username": username})
        if existing_profile:
            updates = {}

            existing_queries = existing_profile.get("search_queries") or []
            incoming_queries = profile.get("search_queries") or []
            merged_queries = list(existing_queries)
            for query in incoming_queries:
                if query and query not in merged_queries:
                    merged_queries.append(query)
            if merged_queries != existing_queries:
                updates["search_queries"] = merged_queries

            for field in ["followers", "following", "posts"]:
                old_value = existing_profile.get(field)
                new_value = profile.get(field)
                if (old_value is None or old_value == "") and new_value not in (None, ""):
                    updates[field] = new_value

            if updates:
                collection.update_one({"_id": existing_profile["_id"]}, {"$set": updates})
                updated_count += 1
                log_line("UPDATE", f"Updated existing profile: {username}")
            else:
                log_line("SKIP", f"Profile already up to date: {username}")
                skipped_count += 1
            continue

        try:
            collection.insert_one(profile)
        except DuplicateKeyError:
            log_line("SKIP", f"Duplicate profile skipped: {username}")
            skipped_count += 1
            continue

        inserted_count += 1
        log_line("INSERT", f"Inserted profile: {username}")

    return {
        "inserted": inserted_count,
        "updated": updated_count,
        "skipped": skipped_count,
    }


def save_searched_query_to_mongodb(search_query, searched_collection, queries_collection=None):
    if not search_query:
        return

    if queries_collection is not None:
        result = queries_collection.delete_many({"query": search_query})
        if result.deleted_count > 0:
            log_line("INFO", f"Removed {result.deleted_count} query entries matching searched query '{search_query}'")

    existing = searched_collection.find_one({"query": search_query})
    if existing:
        log_line("SKIP", f"Searched query already exists: {search_query}")
        return

    searched_collection.insert_one({"query": search_query})
    log_line("OK", f"Saved searched query: {search_query}")


def save_related_queries_to_mongodb(related_queries, source_query, collection):
    inserted_count = 0
    skipped_count = 0

    for related_query in related_queries:
        query_text = related_query.strip()
        if not query_text:
            continue

        if source_query and query_text.lower() == source_query.lower():
            continue

        existing = collection.find_one({"query": query_text, "from_query": source_query})
        if existing:
            skipped_count += 1
            continue

        collection.insert_one({"query": query_text, "from_query": source_query})
        inserted_count += 1

    return {
        "inserted": inserted_count,
        "skipped": skipped_count,
    }