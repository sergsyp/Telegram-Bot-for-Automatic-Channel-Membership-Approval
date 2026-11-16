import unittest

from view_stats import (
    ViewCountError,
    extract_view_count,
    parse_vk_video_id,
    parse_youtube_video_id,
)


class ViewStatsTest(unittest.TestCase):
    def test_extracts_telegram_compact_count(self):
        html = '<div data-post="sergsyp/314"><span class="tgme_widget_message_views">12.5K</span></div>'
        self.assertEqual(extract_view_count("telegram", html, "314"), 12500)

    def test_extracts_each_supported_video_platform(self):
        fixtures = {
            "youtube": '"viewCount":"12345"',
            "vk_video": '"views":23456',
            "rutube": '"view_count":34567',
            "dzen": '"viewsCount":45678',
        }
        for platform, body in fixtures.items():
            with self.subTest(platform=platform):
                self.assertGreater(extract_view_count(platform, body), 0)

    def test_missing_public_counter_is_an_error(self):
        with self.assertRaises(ViewCountError):
            extract_view_count("yandex_music", "<html>Нет публичного счётчика</html>")

    def test_extracts_dzen_open_graph_counter(self):
        html = '<meta property="ya:ovs:views_total" content="106"/>'
        self.assertEqual(extract_view_count("dzen", html), 106)

    def test_parses_vk_video_url(self):
        self.assertEqual(
            parse_vk_video_id("https://vkvideo.ru/video-227129566_456239030"),
            "-227129566_456239030",
        )

    def test_parses_youtube_video_url(self):
        self.assertEqual(parse_youtube_video_id("https://youtu.be/EAZvhLhImec"), "EAZvhLhImec")


class LocalOnlyCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_no_cms_credentials_keeps_local_collection_without_delivery_alert(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        import view_stats

        database = MagicMock()
        database.active_publications.return_value = []
        database.start_stats_run.return_value = 1
        database.finish_stats_run.return_value = "success"
        bot = AsyncMock()
        with patch.object(view_stats, "ANALYTICS_API_URL", ""), patch.object(
            view_stats, "ANALYTICS_INGEST_TOKEN", ""
        ), patch.object(view_stats, "deliver_history") as deliver:
            await view_stats.run_daily_collection(database, bot, 127626487)
        deliver.assert_not_called()
        bot.send_message.assert_not_called()
        database.finish_stats_run.assert_called_once_with(1, 0, 0)


if __name__ == "__main__":
    unittest.main()
