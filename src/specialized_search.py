"""
Specialized data engines for Lokality.
Includes Finance, News, and Weather integrations.
"""
import asyncio
import yfinance as yf
import python_weather
from gnews import GNews

from logger import logger
from profiler import Profiler
from utils import debug_print

class SpecializedSearch:
    """
    Namespace for specialized data retrieval methods.
    """
    @staticmethod
    def get_ticker_data(symbol):
        """
        Fetches real-time price and recent news for a given ticker symbol.
        Returns a formatted string for context injection.
        """
        Profiler().start("Finance Lookup")
        debug_print(f"[*] Finance Lookup: {symbol}")
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = info.get('last_price')
            currency = info.get('currency', 'USD')

            if price is None:
                full_info = ticker.info
                price = (full_info.get('currentPrice') or
                         full_info.get('regularMarketPrice'))
                currency = full_info.get('currency', 'USD')

            if price is None:
                Profiler().stop("Finance Lookup")
                return None

            name = ticker.info.get('longName', symbol)
            result = [
                f"--- Finance Data for {name} ({symbol.upper()}) ---",
                f"Current Price: {price:.2f} {currency}",
                f"Market: {ticker.info.get('exchange', 'Unknown')}"
            ]

            news = ticker.news
            if news:
                result.append("\nRecent News:")
                for item in news[:3]:
                    title = item.get('title')
                    link = item.get('link')
                    pub = item.get('publisher')
                    result.append(f"- {title} (Source: {pub}, Link: {link})")

            Profiler().stop("Finance Lookup")
            return "\n".join(result)
        except (RuntimeError, ValueError) as exc:
            logger.error("Finance Error for '%s': %s", symbol, exc)
            Profiler().stop("Finance Lookup")
            return None

    @staticmethod
    def get_news(query=None, max_results=5):
        """
        Fetches news based on a query or general headlines.
        Returns a formatted string for context injection.
        """
        Profiler().start("News Lookup")
        debug_print(f"[*] News Lookup: {query if query else 'Top Stories'}")
        try:
            # Initialize with language and region for better reliability
            google_news = GNews(language='en', country='US', max_results=max_results)
            news = google_news.get_news(query) if query else google_news.get_top_news()

            if not news:
                Profiler().stop("News Lookup")
                return None

            result = [f"--- News Data {'for ' + query if query else '(Top Stories)'} ---"]
            for item in news:
                title = item.get('title')
                pub = item.get('publisher', {}).get('title', 'Unknown')
                link = item.get('url')
                date = item.get('published date')
                result.append(f"- {title} (Source: {pub}, Date: {date}, Link: {link})")

            Profiler().stop("News Lookup")
            return "\n".join(result)
        except (RuntimeError, ValueError) as exc:
            logger.error("News Error: %s", exc)
            Profiler().stop("News Lookup")
            return None

    @staticmethod
    def clean_weather_location(location):
        """
        Cleans the location string for better weather lookup.
        Removes conversational noise and keywords like 'weather' or 'forecast'.
        """
        if not location:
            return ""

        loc = location.strip().strip("'\"?. ")
        loc_lower = loc.lower()

        # Remove common prefixes
        prefixes = [
            "weather in ", "weather for ", "weather at ",
            "current weather in ", "forecast for ", "forecast in ",
            "what is the weather in ", "how is the weather in ",
            "the weather in ", "temperature in "
        ]
        for p in prefixes:
            if loc_lower.startswith(p):
                loc = loc[len(p):].strip()
                loc_lower = loc.lower()

        # Remove common suffixes
        suffixes = [
            " weather", " forecast", " today", " now", " current", " temperature"
        ]
        for s in suffixes:
            if loc_lower.endswith(s):
                loc = loc[:-len(s)].strip()
                loc_lower = loc.lower()

        return loc

    @staticmethod
    async def _fetch_weather(location):
        """Internal async method to fetch weather."""
        async with python_weather.Client(unit=python_weather.IMPERIAL) as client:
            return await client.get(location)

    @staticmethod
    def get_weather(location):
        """
        Synchronous wrapper for weather fetching.
        Returns a formatted string for context injection.
        """
        Profiler().start("Weather Lookup")
        clean_loc = SpecializedSearch.clean_weather_location(location)
        if not clean_loc:
            Profiler().stop("Weather Lookup")
            return None

        debug_print(f"[*] Weather Lookup: {clean_loc} (Original: {location})")
        try:
            weather = asyncio.run(SpecializedSearch._fetch_weather(clean_loc))
            result = [
                f"--- Weather Data for {clean_loc.title()} ---",
                f"Temperature: {weather.temperature}°F",
                f"Condition: {weather.description}",
                f"Humidity: {weather.humidity}%",
                f"Wind Speed: {weather.wind_speed} mph",
                "\nForecast:"
            ]

            for daily in list(weather.daily_forecasts)[:3]:
                # Use midday forecast for the condition if available
                condition = "Unknown"
                if daily.hourly_forecasts:
                    mid_idx = len(daily.hourly_forecasts) // 2
                    condition = daily.hourly_forecasts[mid_idx].description

                result.append(
                    f"- {daily.date.strftime('%Y-%m-%d')}: "
                    f"High {daily.highest_temperature}°F, "
                    f"Low {daily.lowest_temperature}°F, "
                    f"Condition: {condition}"
                )

            Profiler().stop("Weather Lookup")
            return "\n".join(result)
        except (RuntimeError, ValueError, ConnectionError) as exc:
            logger.error("Weather Error for '%s': %s", clean_loc, exc)
            Profiler().stop("Weather Lookup")
            return None
