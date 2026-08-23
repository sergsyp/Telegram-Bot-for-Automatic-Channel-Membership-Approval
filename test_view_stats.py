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


if __name__ == "__main__":
    unittest.main()
