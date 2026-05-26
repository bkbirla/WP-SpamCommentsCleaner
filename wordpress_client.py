import logging
import requests
from requests.auth import HTTPBasicAuth

# Configure logging
logger = logging.getLogger(__name__)

class WordPressClient:
    def __init__(self, site_url: str, username: str, app_password: str):
        """
        Initialize the WordPress REST API client.
        
        :param site_url: Base URL of the WordPress site (e.g., https://example.com)
        :param username: WordPress username or email
        :param app_password: WordPress Application Password (24 characters, spaces are fine)
        """
        self.raw_url = site_url.strip()
        # Ensure we have a proper scheme
        if not self.raw_url.startswith("http://") and not self.raw_url.startswith("https://"):
            self.raw_url = "https://" + self.raw_url
            
        self.site_url = self.raw_url.rstrip("/")
        # We'll use standard WordPress REST API endpoint path
        self.api_base = f"{self.site_url}/wp-json/wp/v2"
        
        # Clean the application password by removing any spaces the user might have copied
        cleaned_password = app_password.replace(" ", "")
        self.auth = HTTPBasicAuth(username, cleaned_password)
        self.headers = {
            "User-Agent": "WP-Spam-Detector/1.0"
        }

    def _request(self, method: str, endpoint: str, params=None, json=None):
        """Helper to make authenticated requests with proper error handling."""
        # Handle cases where endpoint is absolute or relative
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = f"{self.api_base}/{endpoint.lstrip('/')}"
            
        try:
            logger.debug(f"Making {method} request to {url}")
            response = requests.request(
                method,
                url,
                auth=self.auth,
                headers=self.headers,
                params=params,
                json=json,
                timeout=15
            )
            
            # If we get a 404, maybe pretty permalinks are disabled. Try fallback URL.
            if response.status_code == 404 and "/wp-json/wp/v2/" in url:
                fallback_url = url.replace("/wp-json/wp/v2/", "/index.php?rest_route=/wp/v2/")
                logger.info(f"404 encountered. Retrying with fallback REST API URL: {fallback_url}")
                response = requests.request(
                    method,
                    fallback_url,
                    auth=self.auth,
                    headers=self.headers,
                    params=params,
                    json=json,
                    timeout=15
                )
                
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "Unknown"
            error_msg = f"HTTP Error {status_code}: {e}"
            if e.response is not None:
                try:
                    # Try to extract the WP API error message if available
                    wp_err = e.response.json()
                    if isinstance(wp_err, dict) and "message" in wp_err:
                        error_msg = f"WP API Error: {wp_err['message']} (HTTP {status_code})"
                except ValueError:
                    pass
            if status_code == 401:
                error_msg += " Hint: Ensure you are using a WordPress Application Password, not your regular login password. You can generate one in your WordPress Admin Panel under Users -> Profile -> Application Passwords."
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            raise Exception(f"Connection to WordPress failed: {e}") from e

    def verify_connection(self) -> bool:
        """
        Verify credentials and connection to the WordPress REST API.
        
        :return: True if connection is verified successfully, raises Exception otherwise.
        """
        logger.info(f"Verifying connection to {self.site_url}...")
        try:
            # Fetch 1 comment with edit context to test actual credentials and authorization
            self._request("GET", "comments", params={"per_page": 1, "context": "edit"})
            logger.info("WordPress connection verified successfully!")
            return True
        except Exception as e:
            logger.error(f"Failed to verify WordPress connection: {e}")
            raise

    def fetch_comments(self, status: str = "hold", limit: int = None, per_page: int = 50) -> list:
        """
        Fetch comments from WordPress concurrently using multiple threads.
        
        :param status: Comment status filter (e.g. 'hold', 'approve', 'spam', 'trash', or comma-separated list)
        :param limit: Maximum number of comments to retrieve. If None, fetch all matching comments.
        :param per_page: Number of comments per page/request (max 100)
        :return: List of comment dictionaries
        """
        logger.info(f"Fetching comments with status '{status}'...")
        
        # 1. Fetch the first page to get initial comments and find out total pages
        page_size = min(per_page, 100)
        params = {
            "status": status,
            "per_page": page_size,
            "page": 1,
            "context": "edit",
            "_fields": "id,author,author_name,author_email,author_url,author_ip,author_user_agent,status,date"
        }
        
        try:
            response = self._request("GET", "comments", params=params)
            first_page_comments = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch initial page of comments: {e}")
            raise

        if not first_page_comments:
            return []

        # Read pagination headers
        total_comments = int(response.headers.get("X-WP-Total", len(first_page_comments)))
        total_pages = int(response.headers.get("X-WP-TotalPages", 1))
        
        # Apply limit to total_pages if necessary
        if limit and limit < total_comments:
            total_pages = min(total_pages, (limit + page_size - 1) // page_size)
            
        logger.info(f"Total comments matching filter: {total_comments}. Total pages to fetch: {total_pages}.")
        
        all_comments = list(first_page_comments)
        
        if total_pages <= 1:
            if limit:
                all_comments = all_comments[:limit]
        else:
            # 2. Fetch subsequent pages concurrently
            pages_to_fetch = list(range(2, total_pages + 1))
            logger.info(f"Fetching pages 2 to {total_pages} concurrently (up to 10 threads)...")
            
            pages_data = {}
            
            def fetch_page(p):
                p_params = {
                    "status": status,
                    "per_page": page_size,
                    "page": p,
                    "context": "edit",
                    "_fields": "id,author,author_name,author_email,author_url,author_ip,author_user_agent,status,date"
                }
                try:
                    p_resp = self._request("GET", "comments", params=p_params)
                    p_comments = p_resp.json()
                    logger.info(f"Fetched page {p}/{total_pages} ({len(p_comments)} comments)")
                    return p, p_comments
                except Exception as e:
                    logger.error(f"Error fetching page {p}: {e}")
                    return p, []

            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(fetch_page, p): p for p in pages_to_fetch}
                for future in as_completed(futures):
                    p, p_comments = future.result()
                    pages_data[p] = p_comments
                    
            # Assemble comments in the correct order
            for p in sorted(pages_data.keys()):
                all_comments.extend(pages_data[p])
                
            if limit:
                all_comments = all_comments[:limit]

        # 3. Fetch content for each comment individually in parallel using context=view
        if all_comments:
            logger.info(f"Fetching content for {len(all_comments)} comments individually using context=view...")
            from concurrent.futures import ThreadPoolExecutor
            
            def populate_content(comment):
                # Skip if content is already populated (e.g. in tests)
                if "content" in comment and comment["content"]:
                    return
                cid = comment.get("id")
                try:
                    # Fetch only the content field with context=view to bypass server buffers
                    c_resp = self._request("GET", f"comments/{cid}", params={"context": "view", "_fields": "content"})
                    comment["content"] = c_resp.json().get("content", {"rendered": "", "raw": ""})
                except Exception as e:
                    logger.warning(f"Could not retrieve content for comment #{cid}: {e}")
                    comment["content"] = {
                        "rendered": "[Content failed to load - server connection closed]",
                        "raw": "[Content failed to load - server connection closed]"
                    }

            with ThreadPoolExecutor(max_workers=15) as executor:
                list(executor.map(populate_content, all_comments))
            
        logger.info(f"Successfully fetched {len(all_comments)} comments in total.")
        return all_comments

    def mark_as_spam(self, comment_id: int) -> bool:
        """
        Mark a comment as spam.
        
        :param comment_id: The ID of the comment to mark
        :return: True if successful, False otherwise
        """
        logger.info(f"Marking comment #{comment_id} as SPAM...")
        try:
            self._request("POST", f"comments/{comment_id}", json={"status": "spam"})
            logger.info(f"Comment #{comment_id} marked as spam successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to mark comment #{comment_id} as spam: {e}")
            return False
