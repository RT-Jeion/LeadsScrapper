"""
MongoDB database operations and connection management.
"""

from pymongo import MongoClient
from logger import log_line


def get_mongo_collections():
    """
    Connect to MongoDB and return collections for profiles, searched queries, and related queries.
    
    Returns:
        dict: Contains three MongoDB collections:
            - profiles: Instra_Profiles collection for Instagram profiles
            - searched_queries: searched_queries collection for search history
            - all_search_query: all_search_query collection for related queries
    """
    mongo_uri = "mongodb://localhost:27017/"
    mongo_db_name = "Leads"

    client = MongoClient(mongo_uri)
    db = client[mongo_db_name]
    return {
        "profiles": db["Instra_Profiles"],
        "searched_queries": db["searched_queries"],
        "all_search_query": db["all_search_query"],
    }


def save_profiles_to_mongodb(profile_data, collection):
    """
    Save or update Instagram profile records in MongoDB with duplicate checking.
    
    For duplicate usernames found:
    - Appends new search queries to existing record
    - Updates followers, following, posts if old values were empty
    
    Args:
        profile_data: List of profile dictionaries
        collection: MongoDB collection object
        
    Returns:
        dict: Statistics with inserted, updated, and skipped counts
    """
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

            # Merge search queries
            existing_queries = existing_profile.get("search_queries") or []
            incoming_queries = profile.get("search_queries") or []
            merged_queries = list(existing_queries)
            for query in incoming_queries:
                if query and query not in merged_queries:
                    merged_queries.append(query)
            if merged_queries != existing_queries:
                updates["search_queries"] = merged_queries

            # Update missing stats from new data
            for field in ["followers", "following", "posts"]:
                old_value = existing_profile.get(field)
                new_value = profile.get(field)
                if (old_value is None or old_value == "") and new_value not in (None, ""):
                    updates[field] = new_value

            if updates:
                collection.update_one({"_id": existing_profile["_id"]}, {"$set": updates})
                updated_count += 1
                log_line("UPDATE", f"Copy found. Existing record updated: {username}")
            else:
                log_line("SKIP", f"Copy found so skipped this: {username}")
                skipped_count += 1
            continue

        try:
            collection.insert_one(profile)
        except DuplicateKeyError:
            log_line("SKIP", f"Copy found so skipped this: {username}")
            skipped_count += 1
            continue

        inserted_count += 1
        log_line("INSERT", f"Inserted into MongoDB: {username}")

    return {
        "inserted": inserted_count,
        "updated": updated_count,
        "skipped": skipped_count,
    }


def save_searched_query_to_mongodb(search_query, collection, offset=None):
    """
    Log a searched query with timestamp and offset.
    
    Args:
        search_query: The search query string
        collection: MongoDB searched_queries collection
        offset: Search result page offset
    """
    if not search_query:
        return

    from scraper import get_time_parts

    timestamp = get_time_parts()
    payload = {
        "search_query": search_query,
        "offset": offset,
        "day": timestamp["day"],
        "time": timestamp["time"],
        "year": timestamp["year"],
    }
    collection.insert_one(payload)
    log_line("OK", f"Saved searched query (offset {offset}): {search_query}")


def save_related_queries_to_mongodb(related_queries, source_query, collection):
    """
    Save related queries found in search results with duplicate checking.
    
    Args:
        related_queries: List of related query strings
        source_query: The original search query these came from
        collection: MongoDB all_search_query collection
        
    Returns:
        dict: Statistics with inserted and skipped counts
    """
    from scraper import get_time_parts

    inserted_count = 0
    skipped_count = 0

    for related_query in related_queries:
        existing = collection.find_one(
            {
                "related_query": related_query,
                "from_search_query": source_query,
            }
        )
        if existing:
            skipped_count += 1
            continue

        timestamp = get_time_parts()
        collection.insert_one(
            {
                "related_query": related_query,
                "from_search_query": source_query,
                "day": timestamp["day"],
                "time": timestamp["time"],
                "year": timestamp["year"],
            }
        )
        inserted_count += 1

    return {
        "inserted": inserted_count,
        "skipped": skipped_count,
    }
