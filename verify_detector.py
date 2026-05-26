import unittest
from unittest.mock import patch, MagicMock

# Import modules to test
from spam_classifier import HeuristicClassifier, strip_html
from wordpress_client import WordPressClient

class TestSpamDetector(unittest.TestCase):
    def setUp(self):
        self.heuristic_classifier = HeuristicClassifier()

    def test_strip_html(self):
        self.assertEqual(strip_html("<p>Hello World</p>"), "Hello World")
        self.assertEqual(strip_html("Hello &amp; Welcome"), "Hello & Welcome")
        self.assertEqual(strip_html("<a href='http://spam.com'>Click here</a> for details"), "Click here for details")

    def test_heuristic_clean_comment(self):
        # A normal clean comment
        clean_comment = {
            "id": 1,
            "author_name": "Jane Doe",
            "author_email": "jane@example.com",
            "author_url": "",
            "content": {"rendered": "<p>Thank you for the detailed walkthrough of WordPress REST API. It was very clear and helped me build my app!</p>"}
        }
        res = self.heuristic_classifier.classify(clean_comment)
        self.assertFalse(res["is_spam"])
        self.assertEqual(res["confidence"], 0.0)

    def test_heuristic_excessive_links(self):
        # A comment with too many links
        spam_comment = {
            "id": 2,
            "author_name": "SEO Consultant",
            "author_email": "seo@spammers.net",
            "author_url": "http://spammers.net",
            "content": {
                "rendered": (
                    "Great website! Check out our services: <a href='http://spam1.com'>low loans</a>, "
                    "<a href='http://spam2.com'>cheap viagra</a>, and <a href='http://spam3.com'>casino online</a>!"
                )
            }
        }
        res = self.heuristic_classifier.classify(spam_comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("Excessive links", res["reason"])
        self.assertGreater(res["confidence"], 0.6)

    def test_heuristic_spam_keywords(self):
        # A comment containing specific spam keywords
        spam_comment = {
            "id": 3,
            "author_name": "CryptoGuy",
            "author_email": "cryptoguy@bitcoin.org",
            "author_url": "",
            "content": {
                "rendered": "<p>You should really invest in our new bitcoin token! It is going to moon. Guaranteed return on investment.</p>"
            }
        }
        res = self.heuristic_classifier.classify(spam_comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("Contains spam keywords", res["reason"])

    def test_heuristic_suspicious_author_name(self):
        # Comment with a URL in the author name
        spam_comment = {
            "id": 4,
            "author_name": "Buy Bitcoin Online - Cheap",
            "author_email": "sales@bitcoinspammer.com",
            "author_url": "http://bitcoinspammer.com",
            "content": {"rendered": "<p>I think this is a nice blog post, thanks for sharing.</p>"}
        }
        res = self.heuristic_classifier.classify(spam_comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("Author name contains", res["reason"])

    def test_heuristic_suspicious_tld_and_email(self):
        # A comment with suspicious email TLD and author URL TLD
        spam_comment = {
            "id": 5,
            "author_name": "John Doe",
            "author_email": "john@spammer.ru",
            "author_url": "http://spammer.xyz",
            "content": {"rendered": "<p>I think this is a nice blog post, thanks for sharing.</p>"}
        }
        res = self.heuristic_classifier.classify(spam_comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("suspicious TLD", res["reason"])

    def test_heuristic_gibberish_author_name(self):
        # Comment with a gibberish author name
        spam_comment = {
            "id": 6,
            "author_name": "xrzqtwp",
            "author_email": "john@example.com",
            "author_url": "",
            "content": {"rendered": "<p>Check out our site crypto for more info.</p>"}
        }
        res = self.heuristic_classifier.classify(spam_comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("gibberish", res["reason"])

    def test_heuristic_repeating_characters_and_phone(self):
        # Comment with repeating characters and a whatsapp number call-to-action
        spam_comment = {
            "id": 7,
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "author_url": "",
            "content": {"rendered": "<p>This is so amazinggggg!!!!! Contact us on WhatsApp +1-555-0199 for cheap crypto.</p>"}
        }
        res = self.heuristic_classifier.classify(spam_comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("repeating characters", res["reason"])
        self.assertIn("phone pattern", res["reason"])

    @patch("requests.request")
    def test_wp_client_verify(self, mock_request):
        # Mock WordPress connection verification
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 123, "content": {"rendered": "test"}}]
        mock_request.return_value = mock_response

        client = WordPressClient("https://mock-wp-site.com", "admin", "mock-app-pass")
        self.assertTrue(client.verify_connection())
        mock_request.assert_called_once()

    @patch("requests.request")
    def test_wp_client_fetch_comments(self, mock_request):
        # Mock comment fetching
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-WP-TotalPages": "1"}
        mock_response.json.return_value = [
            {"id": 1, "author_name": "Alice", "content": {"rendered": "Nice post"}},
            {"id": 2, "author_name": "Bob", "content": {"rendered": "Casino links here"}}
        ]
        mock_request.return_value = mock_response

        client = WordPressClient("https://mock-wp-site.com", "admin", "mock-app-pass")
        comments = client.fetch_comments(status="hold")
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["author_name"], "Alice")

    @patch("requests.request")
    def test_wp_client_fetch_comments_concurrent(self, mock_request):
        # 1. First page response has 2 pages
        mock_response_p1 = MagicMock()
        mock_response_p1.status_code = 200
        mock_response_p1.headers = {"X-WP-TotalPages": "2", "X-WP-Total": "3"}
        mock_response_p1.json.return_value = [{"id": 1, "author_name": "Alice", "content": {"rendered": "test1"}}]

        # 2. Second page response has 2 comments
        mock_response_p2 = MagicMock()
        mock_response_p2.status_code = 200
        mock_response_p2.headers = {"X-WP-TotalPages": "2", "X-WP-Total": "3"}
        mock_response_p2.json.return_value = [
            {"id": 2, "author_name": "Bob", "content": {"rendered": "test2"}},
            {"id": 3, "author_name": "Charlie", "content": {"rendered": "test3"}}
        ]

        mock_request.side_effect = [mock_response_p1, mock_response_p2]

        client = WordPressClient("https://mock-wp-site.com", "admin", "mock-app-pass")
        comments = client.fetch_comments(status="hold")

        self.assertEqual(len(comments), 3)
        self.assertEqual(comments[0]["author_name"], "Alice")
        self.assertEqual(comments[1]["author_name"], "Bob")
        self.assertEqual(comments[2]["author_name"], "Charlie")
        self.assertEqual(mock_request.call_count, 2)

    @patch("requests.request")
    def test_wp_client_mark_as_spam(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        client = WordPressClient("https://mock-wp-site.com", "admin", "mock-app-pass")
        self.assertTrue(client.mark_as_spam(123))
        self.assertTrue(client.mark_as_spam(124))
        self.assertEqual(mock_request.call_count, 2)

    # --- New tests for enhanced heuristic signals ---

    def test_heuristic_url_shortener_in_content(self):
        """Comment with URL shortener link should be flagged."""
        comment = {
            "id": 20,
            "author_name": "Spammer",
            "author_email": "spam@example.com",
            "author_url": "",
            "content": {"rendered": "<p>Check out this great resource: https://bit.ly/3xYz123 you will love it!</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("URL shortener", res["reason"])

    def test_heuristic_seo_anchor_text_stuffing(self):
        """Comment with SEO-stuffed anchor text should be flagged."""
        comment = {
            "id": 21,
            "author_name": "SEO Bot",
            "author_email": "seo@example.com",
            "author_url": "",
            "content": {"rendered": '<p>Nice blog! <a href="http://example.com">buy cheap online services</a> for your needs.</p>'}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("SEO-stuffed anchor text", res["reason"])

    def test_heuristic_all_caps_shouting(self):
        """Comment with excessive ALL-CAPS should be flagged."""
        comment = {
            "id": 22,
            "author_name": "Shouty",
            "author_email": "shout@example.com",
            "author_url": "",
            "content": {"rendered": "<p>THIS IS THE BEST PRODUCT EVER BUY NOW CLICK HERE AMAZING DEAL TODAY</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("ALL-CAPS", res["reason"])

    def test_heuristic_mixed_scripts(self):
        """Comment with mixed Latin + Cyrillic should be flagged."""
        comment = {
            "id": 23,
            "author_name": "Тест User",
            "author_email": "test@example.com",
            "author_url": "",
            "content": {"rendered": "<p>Great article! Купить viagra here at cheap prices online now.</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])

    def test_heuristic_generic_praise_with_author_url(self):
        """Generic praise with author URL (link-drop pattern) should be flagged."""
        comment = {
            "id": 24,
            "author_name": "Marketing Guy",
            "author_email": "info@example.com",
            "author_url": "http://myseobusiness.xyz",
            "content": {"rendered": "<p>Thanks for sharing, great article!</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("link-drop pattern", res["reason"])

    def test_heuristic_author_name_matches_url_domain(self):
        """Author name matching URL domain + suspicious TLD = spam."""
        comment = {
            "id": 25,
            "author_name": "mybusiness",
            "author_email": "info@mybusiness.xyz",
            "author_url": "http://mybusiness.xyz",
            "content": {"rendered": "<p>Thanks for sharing! Nice post.</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("SEO pattern", res["reason"])

    def test_heuristic_disposable_email(self):
        """Comment from a disposable email address should be flagged."""
        comment = {
            "id": 26,
            "author_name": "Temp User",
            "author_email": "user123@mailinator.com",
            "author_url": "http://spam-site.xyz",
            "content": {"rendered": "<p>Nice post, very informative!</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("Disposable", res["reason"])

    def test_heuristic_emoji_spam(self):
        """Comment with excessive emojis + suspicious signals should be flagged."""
        comment = {
            "id": 27,
            "author_name": "Emoji Fan",
            "author_email": "emoji@example.ru",
            "author_url": "http://spamsite.xyz",
            "content": {"rendered": "<p>🔥 Amazing 🎯 deals 💰 right 🎁 now 🚀 check ⭐ this out!</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("emoji", res["reason"].lower())

    def test_heuristic_duplicate_phrases(self):
        """Comment with repeated phrases should be flagged."""
        comment = {
            "id": 28,
            "author_name": "Bot",
            "author_email": "bot@example.com",
            "author_url": "",
            "content": {"rendered": "<p>buy cheap pills buy cheap pills buy cheap pills buy cheap pills online now.</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])

    def test_heuristic_trust_discount_registered_user(self):
        """Registered WordPress users (author > 0) should get a score discount."""
        # Guest: suspicious email TLD (0.6) + author URL suspicious TLD (0.6) = 1.2 (spam)
        # With trust discount (-0.4) = 0.8 (HAM)
        comment_guest = {
            "id": 29,
            "author": 0,  # Guest
            "author_name": "John Doe",
            "author_email": "john@example.ru",
            "author_url": "http://example.xyz",
            "content": {"rendered": "<p>I really found this explanation of the WordPress API to be insightful and valuable.</p>"}
        }
        res_guest = self.heuristic_classifier.classify(comment_guest)
        # Guest should be flagged (score = 1.2)
        self.assertTrue(res_guest["is_spam"])

        # Same comment from a registered user
        comment_registered = {
            "id": 29,
            "author": 5,  # Registered user
            "author_name": "John Doe",
            "author_email": "john@example.ru",
            "author_url": "http://example.xyz",
            "content": {"rendered": "<p>I really found this explanation of the WordPress API to be insightful and valuable.</p>"}
        }
        res_registered = self.heuristic_classifier.classify(comment_registered)
        # Registered user should NOT be flagged due to trust discount (1.2 - 0.4 = 0.8)
        self.assertFalse(res_registered["is_spam"])

    def test_heuristic_trust_discount_does_not_help_blatant_spam(self):
        """Trust discount should NOT save blatant spam (score >= 2.0)."""
        comment = {
            "id": 30,
            "author": 2,  # Registered user
            "author_name": "http://casino-online.xyz",
            "author_email": "spam@casino.ru",
            "author_url": "http://casino-online.xyz",
            "content": {"rendered": '<p>Check <a href="http://casino1.xyz">casino</a> <a href="http://casino2.xyz">gambling</a> <a href="http://casino3.xyz">poker</a>!</p>'}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])

    def test_heuristic_clean_registered_user(self):
        """Normal comment from a registered user should remain HAM."""
        comment = {
            "id": 31,
            "author": 3,
            "author_name": "Alice Smith",
            "author_email": "alice@gmail.com",
            "author_url": "",
            "content": {"rendered": "<p>I followed your tutorial and it worked perfectly. The step about configuring the REST API was especially helpful for my project.</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertFalse(res["is_spam"])

    def test_heuristic_expanded_spam_keywords(self):
        """Test newly added spam keywords."""
        comment = {
            "id": 32,
            "author_name": "DealGuy",
            "author_email": "deal@example.com",
            "author_url": "",
            "content": {"rendered": "<p>Get your free gift card and buy now before this limited time offer expires!</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])

    def test_heuristic_non_latin_korean_author_with_praise(self):
        """Korean author name + generic praise should be spam."""
        comment = {
            "id": 40,
            "author_name": "판도라",
            "author_email": "test@example.com",
            "author_url": "",
            "content": {"rendered": "<p>Nice post!</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("non-Latin", res["reason"])

    def test_heuristic_non_latin_arabic_author_with_praise(self):
        """Arabic/Persian author name + generic praise should be spam."""
        comment = {
            "id": 41,
            "author_name": "فیتنس مکمل",
            "author_email": "test@example.com",
            "author_url": "",
            "content": {"rendered": "<p>Great article, thanks for sharing!</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertTrue(res["is_spam"])
        self.assertIn("non-Latin", res["reason"])

    def test_heuristic_non_latin_author_with_real_content(self):
        """Non-Latin author name with substantive content should NOT be spam on its own."""
        comment = {
            "id": 42,
            "author_name": "판도라",
            "author_email": "test@gmail.com",
            "author_url": "",
            "content": {"rendered": "<p>I followed your WordPress REST API tutorial step by step and it worked perfectly for my project.</p>"}
        }
        res = self.heuristic_classifier.classify(comment)
        self.assertFalse(res["is_spam"])

if __name__ == "__main__":
    unittest.main()
