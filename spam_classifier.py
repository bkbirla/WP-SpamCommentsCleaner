import json
import logging
import re
import requests
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

def strip_html(html_text: str) -> str:
    """Utility to remove HTML tags from text."""
    if not html_text:
        return ""
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", html_text)
    # Unescape common HTML entities
    clean = clean.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    return clean.strip()

class SpamClassifier(ABC):
    @abstractmethod
    def classify(self, comment: dict) -> dict:
        """
        Analyze a comment and return spam classification.
        
        :param comment: Dictionary of comment data from WordPress API
        :return: Dict containing:
                 - 'is_spam': bool
                 - 'confidence': float (0.0 to 1.0)
                 - 'reason': str
        """
        pass

class HeuristicClassifier(SpamClassifier):
    def __init__(self):
        # A list of common words found in comment spam
        self.spam_keywords = [
            "casino", "gambling", "poker", "slots", "betting", "crypto", "bitcoin",
            "ethereum", "blockchain", "forex", "trading", "viagra", "cialis",
            "levitra", "porn", "sex", "dating", "pills", "pharmacy", "loan",
            "insurance", "mortgage", "cheap", "discount", "replica", "rolex",
            "essay writing", "write my paper", "seo service", "backlink", "rank higher",
            "traffic generator", "make money online", "passive income", "earn cash",
            "cbd oil", "cannabis", "weed", "hack", "crack", "torrent",
            "weight loss", "diet pill", "free money", "winner", "prize",
            "gift card", "luxury", "payday", "debt relief", "credit score",
            "binary option", "nft", "airdrop", "token sale", "ico",
            "dropshipping", "affiliate", "click here", "act now", "limited time",
            "buy now", "order now", "best price", "lowest price"
        ]
        
        # Generic praise expressions often used by automated spammers to look natural
        self.generic_praise = [
            "nice post", "great article", "thank you for this post",
            "very informative", "extremely helpful", "awesome blog",
            "good read", "keep up the good work", "i really like your blog",
            "excellent post", "love your blog", "thanks for sharing",
            "wonderful article", "amazing post", "great work",
            "this is exactly what i was looking for", "very useful",
            "great information", "bookmarked", "i have bookmarked",
            "i will bookmark", "helpful information", "useful information",
            "wonderful blog", "fantastic post", "brilliant article",
            "well written", "nicely written", "perfectly written",
            "quality content", "quality articles", "high quality"
        ]

        # Spam-heavy Top-Level Domains (TLDs)
        self.suspicious_tlds = {
            ".ru", ".su", ".xyz", ".top", ".club", ".info", ".work", ".click",
            ".biz", ".loan", ".tk", ".cf", ".gq", ".ml", ".ga", ".date", ".win",
            ".download", ".online", ".site", ".website", ".space",
            ".icu", ".buzz", ".fun", ".monster", ".cyou", ".rest", ".beauty",
            ".hair", ".skin", ".quest", ".stream", ".racing", ".review",
            ".accountant", ".science", ".party", ".faith", ".cricket",
            ".webcam", ".bid", ".trade", ".pw", ".cc"
        }

        # URL shortener domains
        self.url_shorteners = {
            "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd",
            "buff.ly", "adf.ly", "bit.do", "mcaf.ee", "su.pr", "lnkd.in",
            "db.tt", "qr.ae", "cur.lv", "ity.im", "q.gs", "po.st",
            "bc.vc", "twitthis.com", "u.to", "j.mp", "buzurl.com",
            "cutt.us", "u.bb", "yourls.org", "x.co", "prettylinkpro.com",
            "scrnch.me", "filourl.com", "vzturl.com", "qr.net", "1url.com",
            "tweez.me", "v.gd", "tr.im", "link.zip.net", "rb.gy",
            "shorturl.at", "t.ly"
        }

        # SEO / commercial keyword phrases often stuffed into anchor text
        self.seo_anchor_keywords = [
            "buy", "cheap", "best", "top", "online", "free", "discount",
            "order", "shop", "store", "deal", "offer", "price", "sale",
            "service", "services", "agency", "company", "professional",
            "expert", "hire", "website", "web design", "development"
        ]

    def _get_domain(self, text: str) -> str:
        """Helper to extract domain/TLD from email or URL."""
        if not text:
            return ""
        text = text.lower().strip()
        if "@" in text:
            parts = text.split("@")
            if len(parts) > 1:
                return parts[-1]
        if "://" in text:
            text = text.split("://")[1]
        return text.split("/")[0].split("?")[0]

    def _is_suspicious_tld(self, domain: str) -> bool:
        """Helper to check if a domain has a suspicious TLD."""
        if not domain:
            return False
        return any(domain.endswith(tld) for tld in self.suspicious_tlds)

    def _is_gibberish(self, name: str) -> bool:
        """Helper to detect randomized bot author names using consonant/vowel patterns."""
        if not name or len(name) < 4:
            return False
        name_clean = re.sub(r"[^a-zA-Z]", "", name).lower()
        if not name_clean:
            return False
        vowels = sum(1 for c in name_clean if c in "aeiouy")
        consonants = len(name_clean) - vowels
        
        # 1. No vowels in a name with at least 4 letters
        if vowels == 0 and len(name_clean) >= 4:
            return True
        # 2. Too many consonants relative to vowels (bot-like random names)
        if consonants > 4 * vowels and len(name_clean) >= 5:
            return True
        # 3. Excessive repeating characters (e.g. "aaaaa", "xxx")
        if re.search(r"(.)\1\1\1", name_clean):
            return True
        return False

    def _has_mixed_scripts(self, text: str) -> bool:
        """Detect mixed script usage (e.g., Cyrillic + Latin) which is a common obfuscation technique."""
        if not text:
            return False
        has_latin = bool(re.search(r"[a-zA-Z]", text))
        has_cyrillic = bool(re.search(r"[\u0400-\u04FF]", text))
        has_cjk = bool(re.search(r"[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]", text))
        has_arabic = bool(re.search(r"[\u0600-\u06FF]", text))
        script_count = sum([has_latin, has_cyrillic, has_cjk, has_arabic])
        return script_count >= 2

    def _extract_anchor_texts(self, html: str) -> list:
        """Extract anchor text from <a> tags in HTML."""
        return re.findall(r"<a\s+[^>]*>(.*?)</a>", html, re.IGNORECASE | re.DOTALL)

    def _is_seo_stuffed_anchor(self, anchor_text: str) -> bool:
        """Check if anchor text looks like SEO keyword stuffing."""
        anchor_lower = strip_html(anchor_text).lower().strip()
        if not anchor_lower:
            return False
        words = anchor_lower.split()
        if len(words) < 2:
            return False
        seo_word_count = sum(1 for w in words if w in self.seo_anchor_keywords)
        # If more than half the words are SEO keywords, it's stuffed
        return seo_word_count >= 2 and seo_word_count / len(words) >= 0.5

    def _count_emojis(self, text: str) -> int:
        """Count emoji characters in text."""
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"   # symbols & pictographs
            "\U0001F680-\U0001F6FF"   # transport & map
            "\U0001F1E0-\U0001F1FF"   # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"   # supplemental symbols
            "\U0001FA00-\U0001FA6F"   # chess symbols
            "\U0001FA70-\U0001FAFF"   # symbols extended-A
            "]+", flags=re.UNICODE
        )
        return len(emoji_pattern.findall(text))

    def _has_duplicate_phrases(self, text: str) -> bool:
        """Detect repeated phrases in comment text (common in spun/bot content)."""
        if not text or len(text) < 40:
            return False
        words = text.lower().split()
        if len(words) < 10:
            return False
        # Check for repeated trigrams (3-word phrases)
        trigrams = [" ".join(words[i:i+3]) for i in range(len(words) - 2)]
        seen = {}
        for trigram in trigrams:
            seen[trigram] = seen.get(trigram, 0) + 1
        # If any non-trivial trigram appears 3+ times, it's suspicious
        for trigram, count in seen.items():
            if count >= 3 and len(trigram) > 8:
                return True
        return False

    def _is_non_latin_name(self, name: str) -> bool:
        """Check if an author name is written entirely in non-Latin script.
        On an English-language blog, names in Korean, Arabic, Cyrillic, CJK, etc.
        are a strong spam indicator."""
        if not name or len(name.strip()) < 2:
            return False
        # Remove spaces, digits, and common punctuation
        cleaned = re.sub(r"[\s\d.,!?@#$%^&*()\-_=+\[\]{};:'\"<>/\\|`~]", "", name)
        if not cleaned:
            return False
        # Check if there are ANY Latin letters
        latin_chars = len(re.findall(r"[a-zA-Z]", cleaned))
        # If the name has zero Latin characters, it's entirely non-Latin
        return latin_chars == 0

    def classify(self, comment: dict) -> dict:
        content_html = comment.get("content", {}).get("rendered", "")
        content_text = strip_html(content_html)
        author_name = comment.get("author_name", "")
        author_url = comment.get("author_url", "")
        author_email = comment.get("author_email", "")
        author_id = comment.get("author", 0)  # WordPress user ID; 0 = guest

        score = 0.0
        reasons = []

        # 1. Analyze Links in Content
        urls_in_content = re.findall(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", content_text)
        html_links = len(re.findall(r"<a\s+[^>]*href", content_html, re.IGNORECASE))
        link_count = max(len(urls_in_content), html_links)
        
        if link_count > 0:
            if link_count > 2:
                # 3+ links is highly indicative of spam
                score += 1.2
                reasons.append(f"Excessive links ({link_count} found)")
            else:
                score += 0.4 * link_count
                reasons.append(f"Contains link(s)")

            # Check if any link in content has a suspicious TLD
            susp_link = False
            for url in urls_in_content:
                domain = self._get_domain(url)
                if self._is_suspicious_tld(domain):
                    susp_link = True
                    break
            if susp_link:
                score += 0.5
                reasons.append("Links point to suspicious TLDs")

            # Check for URL shorteners in content
            for url in urls_in_content:
                domain = self._get_domain(url)
                if domain in self.url_shorteners:
                    score += 0.6
                    reasons.append("Contains URL shortener link")
                    break

        # 2. Analyze Spam Keywords
        matched_keywords = []
        content_lower = content_text.lower()
        for keyword in self.spam_keywords:
            if keyword in content_lower:
                matched_keywords.append(keyword)

        if matched_keywords:
            keyword_score = 0.3 + (len(matched_keywords) * 0.15)
            # Short comments with keywords are highly suspicious
            word_count = len(content_text.split())
            if word_count < 15:
                keyword_score += 0.3
                reasons.append("Short comment containing spam keywords")
            else:
                reasons.append(f"Contains spam keywords: {', '.join(matched_keywords)}")
            score += keyword_score

        # 3. Analyze Author Name
        author_lower = author_name.lower()
        
        # Author Name looks like a URL/Domain
        author_url_match = re.search(r"https?://|www\.|\.com\b|\.net\b|\.org\b", author_name, re.IGNORECASE)
        if author_url_match:
            score += 1.0
            reasons.append("Author name contains a URL or domain extension")
        else:
            # Check for spam keywords in author name
            matched_author_keywords = [kw for kw in self.spam_keywords if kw in author_lower]
            if matched_author_keywords:
                score += 0.6
                reasons.append(f"Author name contains spam keyword: {', '.join(matched_author_keywords)}")
            
            # Check for gibberish author name
            if self._is_gibberish(author_name):
                score += 0.5
                reasons.append("Author name appears to be random gibberish")

            # Check for entirely non-Latin author name (e.g. Korean, Arabic, Cyrillic)
            if self._is_non_latin_name(author_name):
                score += 0.7
                reasons.append(f"Author name is entirely non-Latin script: '{author_name}'")

            # Author name matches author URL domain (SEO name spam)
            if author_url:
                author_url_domain = self._get_domain(author_url)
                # Normalize: strip TLD from domain, compare with name
                domain_name = re.sub(r"\.(com|net|org|io|co|me|us|uk|ca|au|de|fr|in)$", "", author_url_domain)
                domain_name = domain_name.replace(".", "").replace("-", "").replace("www", "")
                name_normalized = re.sub(r"[^a-z0-9]", "", author_lower)
                if domain_name and name_normalized and len(domain_name) > 3:
                    if domain_name == name_normalized or domain_name in name_normalized or name_normalized in domain_name:
                        score += 0.4
                        reasons.append("Author name matches author URL domain (SEO pattern)")

        # 4. Analyze Author URL
        if author_url:
            domain = self._get_domain(author_url)
            if self._is_suspicious_tld(domain):
                score += 0.6
                reasons.append(f"Author URL points to a suspicious TLD ({domain})")
            
            # Check if domain contains any spam keywords
            matched_url_keywords = [kw for kw in self.spam_keywords if kw in domain]
            if matched_url_keywords:
                score += 0.5
                reasons.append(f"Author URL domain contains spam keyword")
            
            # Author URL present but name is suspicious or blank
            if not author_name or author_name.strip() == "" or len(author_name) < 2:
                score += 0.5
                reasons.append("Author URL provided without a valid Author Name")

        # 5. Analyze Author Email
        if author_email:
            domain = self._get_domain(author_email)
            if self._is_suspicious_tld(domain):
                score += 0.6
                reasons.append(f"Author email is from a suspicious TLD ({domain})")
                
            # Check if email domain contains any spam keywords
            matched_email_keywords = [kw for kw in self.spam_keywords if kw in domain]
            if matched_email_keywords:
                score += 0.5
                reasons.append(f"Author email domain contains spam keyword")

        # 6. Combined Patterns (Generic Praise + Link)
        if link_count > 0 and any(p in content_lower for p in self.generic_praise):
            score += 0.8
            reasons.append("Generic praise combined with link")

        # 7. Short Comment with Link
        if len(content_text.split()) < 8 and link_count > 0:
            score += 0.6
            reasons.append("Short comment containing a link")

        # 8. Excessive Repeating Characters / Punctuation in Content
        if re.search(r"(.)\1\1\1\1", content_lower) or re.search(r"[!?.]{4,}", content_lower):
            score += 0.4
            reasons.append("Excessive repeating characters or punctuation")

        # 9. Phone Number / Call To Action WhatsApp Pattern
        if re.search(r"(\+?[0-9\-\s\(\)]{8,})", content_text) and any(kw in content_lower for kw in ["whatsapp", "telegram", "call", "phone", "contact"]):
            score += 0.5
            reasons.append("Contains contact info / phone pattern")

        # 10. Generic Praise Only (no substance, even without links)
        word_count = len(content_text.split())
        praise_matches = [p for p in self.generic_praise if p in content_lower]
        if praise_matches and word_count < 12:
            # Check if the comment is ONLY generic praise with no real content
            remaining = content_lower
            for p in praise_matches:
                remaining = remaining.replace(p, "")
            remaining_words = remaining.strip().split()
            remaining_meaningful = [w for w in remaining_words if len(w) > 2]
            if len(remaining_meaningful) < 3:
                score += 0.3
                reasons.append("Comment is only generic praise with no substance")

        # 11. Anchor Text SEO Stuffing
        anchor_texts = self._extract_anchor_texts(content_html)
        seo_stuffed_count = sum(1 for a in anchor_texts if self._is_seo_stuffed_anchor(a))
        if seo_stuffed_count > 0:
            score += 0.5 + (0.2 * min(seo_stuffed_count, 3))
            reasons.append(f"SEO-stuffed anchor text ({seo_stuffed_count} links)")

        # 12. All-Caps / Shouting Detection
        if word_count > 4:
            caps_words = sum(1 for w in content_text.split() if w.isupper() and len(w) > 2)
            caps_ratio = caps_words / word_count if word_count > 0 else 0
            if caps_ratio > 0.5 and caps_words >= 3:
                score += 0.4
                reasons.append("Excessive ALL-CAPS text")

        # 13. Mixed Script Detection (obfuscation)
        if self._has_mixed_scripts(content_text):
            score += 0.4
            reasons.append("Mixed scripts detected (possible obfuscation)")
        if self._has_mixed_scripts(author_name):
            score += 0.5
            reasons.append("Author name uses mixed scripts")

        # 14. Content-to-Markup Ratio (mostly HTML/links, little text)
        if content_html and len(content_html) > 50:
            text_len = len(content_text.strip())
            html_len = len(content_html)
            if text_len > 0:
                markup_ratio = html_len / text_len
                if markup_ratio > 5.0 and link_count > 0:
                    score += 0.5
                    reasons.append("Very high markup-to-text ratio")

        # 15. Emoji Spam
        emoji_count = self._count_emojis(content_text)
        if emoji_count > 5:
            score += 0.4
            reasons.append(f"Excessive emoji usage ({emoji_count})")

        # 16. Duplicate Phrase Detection (spun content)
        if self._has_duplicate_phrases(content_text):
            score += 0.5
            reasons.append("Repeated phrases detected (possible spun content)")

        # 17. Author URL with generic praise and no real content
        if author_url and praise_matches and word_count < 15 and link_count == 0:
            score += 0.4
            reasons.append("Author URL + generic praise comment (link-drop pattern)")

        # 18. Disposable/Temporary Email Patterns
        if author_email:
            email_domain = self._get_domain(author_email)
            disposable_domains = {
                "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
                "yopmail.com", "sharklasers.com", "guerrillamailblock.com", "grr.la",
                "dispostable.com", "maildrop.cc", "fakeinbox.com", "trashmail.com",
                "10minutemail.com", "temp-mail.org", "emailondeck.com"
            }
            if email_domain in disposable_domains:
                score += 0.6
                reasons.append("Disposable/temporary email address")

        # === TRUST DISCOUNT for registered WordPress users ===
        # Registered users (author ID > 0) are less likely to be spammers.
        # Apply a score discount to reduce false positives for legitimate users.
        if author_id and int(author_id) > 0:
            discount = 0.4
            if score > 0 and score < 2.0:
                score = max(0, score - discount)
                reasons.append(f"Trust discount applied (registered user ID {author_id})")

        # Final Verdict
        is_spam = score >= 1.0

        if is_spam:
            return {
                "is_spam": True,
                "confidence": round(min(score, 1.0), 2),
                "reason": "; ".join(reasons)
            }
        
        return {
            "is_spam": False,
            "confidence": 0.0,
            "reason": "Passed heuristic checks (score: {:.2f})".format(score)
        }

class LLMClassifier(SpamClassifier):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        """
        Initialize the LLM-based Spam Classifier using Google Gemini API.
        """
        self.api_key = api_key
        self.model_name = model_name
        
        # Initialize Google Generative AI SDK
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"Gemini LLM Classifier initialized with model: {self.model_name}")
        except ImportError:
            logger.error("google-generativeai package not found. Run pip install -r requirements.txt")
            raise

    def classify(self, comment: dict) -> dict:
        content_html = comment.get("content", {}).get("rendered", "")
        content_text = strip_html(content_html)
        author_name = comment.get("author_name", "")
        author_url = comment.get("author_url", "")
        author_email = comment.get("author_email", "")
        author_ip = comment.get("author_ip", "")

        # Format the comment metadata into a clear structure for the LLM
        comment_info = {
            "author_name": author_name,
            "author_email": author_email,
            "author_url": author_url,
            "author_ip": author_ip,
            "comment_content": content_text
        }

        # Prompt instruction
        prompt = (
            "You are an advanced spam detection system for a WordPress website.\n"
            "Analyze the following comment details and determine if the comment is SPAM or HAM (legitimate).\n\n"
            "Criteria for SPAM:\n"
            "- Unsolicited advertising, marketing, or self-promotion.\n"
            "- Irrelevant links pointing to commercial or sketchy websites.\n"
            "- Generic compliments that feel automated (e.g., 'Nice blog, thanks for sharing' paired with a link).\n"
            "- Gibberish or spun text.\n"
            "- Text focusing on high-spam subjects (crypto, casinos, pharmaceuticals, fake documents, essay writing services, etc.).\n\n"
            "Analyze these details:\n"
            f"{json.dumps(comment_info, indent=2)}\n\n"
            "You MUST respond ONLY with a valid JSON object. Do not include markdown formatting or backticks around the JSON. The JSON object must have exactly these keys:\n"
            "{\n"
            "  \"is_spam\": boolean,\n"
            "  \"confidence\": float (between 0.0 and 1.0),\n"
            "  \"reason\": \"string explaining your decision briefly\"\n"
            "}"
        )

        try:
            # We can use Gemini's standard generate_content
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse the response
            text = response.text.strip()
            result = json.loads(text)
            
            # Validate output structure
            is_spam = bool(result.get("is_spam", False))
            confidence = float(result.get("confidence", 0.5))
            reason = str(result.get("reason", "No reason provided by LLM."))
            
            return {
                "is_spam": is_spam,
                "confidence": confidence,
                "reason": f"LLM: {reason}"
            }
            
        except Exception as e:
            logger.error(f"Error classifying with Gemini LLM: {e}")
            # Fallback to safe response
            return {
                "is_spam": False,
                "confidence": 0.0,
                "reason": f"LLM Classifier failed (Error: {str(e)})"
            }

class AkismetClassifier(SpamClassifier):
    def __init__(self, api_key: str, blog_url: str):
        """
        Initialize the Akismet Spam Classifier.
        
        :param api_key: Akismet API Key
        :param blog_url: The home URL of the site being checked
        """
        self.api_key = api_key
        # Clean blog url
        self.blog_url = blog_url.strip().rstrip("/")
        if not self.blog_url.startswith("http://") and not self.blog_url.startswith("https://"):
            self.blog_url = "https://" + self.blog_url
            
        # Verify Key
        self._verify_key()

    def _verify_key(self):
        """Verify Akismet key is valid."""
        verify_url = "https://rest.akismet.com/1.1/verify-key"
        payload = {
            "key": self.api_key,
            "blog": self.blog_url
        }
        try:
            response = requests.post(verify_url, data=payload, timeout=10)
            response.raise_for_status()
            if response.text.strip() != "valid":
                raise Exception(f"Akismet API key is invalid for blog {self.blog_url}. Response: {response.text}")
            logger.info("Akismet API key verified successfully!")
        except Exception as e:
            logger.error(f"Akismet verification failed: {e}")
            raise

    def classify(self, comment: dict) -> dict:
        # Akismet check endpoint: https://{api_key}.rest.akismet.com/1.1/comment-check
        check_url = f"https://{self.api_key}.rest.akismet.com/1.1/comment-check"
        
        content_html = comment.get("content", {}).get("rendered", "")
        content_text = strip_html(content_html)
        
        payload = {
            "blog": self.blog_url,
            "user_ip": comment.get("author_ip", ""),
            "user_agent": comment.get("author_user_agent", ""),
            "comment_type": "comment",
            "comment_author": comment.get("author_name", ""),
            "comment_author_email": comment.get("author_email", ""),
            "comment_author_url": comment.get("author_url", ""),
            "comment_content": content_text,
            "blog_lang": "en",
            "blog_charset": "UTF-8"
        }
        
        try:
            response = requests.post(check_url, data=payload, timeout=10)
            response.raise_for_status()
            
            result = response.text.strip()
            
            # Akismet returns "true" if it is spam, "false" if not
            if result == "true":
                # Check for X-Akismet-Pro-Tip header to see if it's "discard" (blatant spam)
                reason = "Akismet classified as SPAM"
                pro_tip = response.headers.get("X-Akismet-Pro-Tip")
                if pro_tip == "discard":
                    reason += " (Blatant spam - Akismet recommends discard)"
                    
                return {
                    "is_spam": True,
                    "confidence": 1.0,
                    "reason": reason
                }
            elif result == "false":
                return {
                    "is_spam": False,
                    "confidence": 0.0,
                    "reason": "Akismet classified as HAM"
                }
            else:
                # Akismet can return error details in headers or response body
                error_msg = response.headers.get("X-Akismet-Error", "Unknown Akismet error")
                logger.warning(f"Unexpected Akismet response: {result}. Error header: {error_msg}")
                return {
                    "is_spam": False,
                    "confidence": 0.0,
                    "reason": f"Akismet classification failed (Response: {result}, Error: {error_msg})"
                }
        except Exception as e:
            logger.error(f"Error checking comment with Akismet: {e}")
            return {
                "is_spam": False,
                "confidence": 0.0,
                "reason": f"Akismet check failed due to error: {str(e)}"
            }
