"""
Unit tests for SpecializedSearch engines.
"""
import unittest
from unittest.mock import MagicMock, patch
from specialized_search import SpecializedSearch

class TestEngines(unittest.TestCase):
    """Test suite for specialized engines."""

    @patch('specialized_search.GNews')
    def test_news_engine_success(self, mock_gnews):
        """Test successful news lookup."""
        mock_instance = mock_gnews.return_value
        mock_instance.get_news.return_value = [
            {
                'title': 'Test News Title',
                'publisher': {'title': 'Test Publisher'},
                'url': 'https://test.news/1',
                'published date': '2026-01-24'
            }
        ]

        results = SpecializedSearch.get_news("test topic")

        self.assertIn("--- News Data for test topic ---", results)
        self.assertIn("Test News Title", results)
        self.assertIn("Source: Test Publisher", results)
        self.assertIn("Link: https://test.news/1", results)

    @patch('specialized_search.GNews')
    def test_news_engine_no_results(self, mock_gnews):
        """Test news lookup with no results."""
        mock_instance = mock_gnews.return_value
        mock_instance.get_news.return_value = []

        results = SpecializedSearch.get_news("nonexistent topic")
        self.assertIsNone(results)

    @patch('specialized_search.python_weather.Client')
    def test_weather_engine_success(self, mock_client):
        """Test successful weather lookup."""
        # Setup complex async mock structure for python-weather
        mock_weather = MagicMock()
        mock_weather.temperature = 72
        mock_weather.description = "Sunny"
        mock_weather.humidity = 45
        mock_weather.wind_speed = 10

        mock_forecast = MagicMock()
        mock_forecast.date.strftime.return_value = '2026-01-25'
        mock_forecast.highest_temperature = 75
        mock_forecast.lowest_temperature = 60

        mock_hourly = MagicMock()
        mock_hourly.description = "Partly Cloudy"
        mock_forecast.hourly_forecasts = [mock_hourly]

        mock_weather.daily_forecasts = [mock_forecast]

        # Use an async mock for the Client's get method
        async def mock_get(_location):
            return mock_weather

        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get.side_effect = mock_get

        results = SpecializedSearch.get_weather("Los Angeles")

        self.assertIn("--- Weather Data for Los Angeles ---", results)
        self.assertIn("Temperature: 72°F", results)
        self.assertIn("Condition: Sunny", results)
        self.assertIn("Forecast:", results)
        self.assertIn("2026-01-25", results)
        self.assertIn("High 75°F", results)

    @patch('specialized_search.python_weather.Client')
    def test_weather_engine_failure(self, mock_client):
        """Test weather lookup failure."""
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get.side_effect = RuntimeError("Network error")

        results = SpecializedSearch.get_weather("London")
        self.assertIsNone(results)

if __name__ == "__main__":
    unittest.main()
