import os
import logging
from newsapi import NewsApiClient
from app.utils.config import Settings
from app.state import SESSION_KEYS

settings = Settings()
logger = logging.getLogger(__name__)

async def get_top_headlines(country="us", category=None, page_size=5, api_key: str = None, session_id: str = None):
    """
    Fetch news headlines using NewsAPI.
    Priority: api_key param > session keys > env default
    """
    key = api_key
    if not key and session_id:
        session_keys = SESSION_KEYS.get(session_id, {})
        key = session_keys.get("NEWS")
    if not key:
        key = settings.NEWSAPI_KEY
    
    if not key:
        logger.warning("No NewsAPI key provided")
        return None

    try:
        client = NewsApiClient(api_key=key)
        resp = client.get_top_headlines(
            country=country, 
            category=category, 
            page_size=page_size
        )
        
        if resp.get("status") != "ok":
            logger.warning("NewsAPI error: %s", resp)
            return None
            
        articles = []
        for art in resp.get("articles", []):
            articles.append({
                "title": art["title"],
                "description": art.get("description"),
                "url": art.get("url"),
                "source": art["source"]["name"],
            })
        return articles
        
    except Exception as e:
        logger.exception("News fetch failed: %s", e)
        return None