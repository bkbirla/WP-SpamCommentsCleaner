import os
import sys
import argparse
import logging
import contextvars
from dotenv import load_dotenv

# Context variable for progress prefix
progress_ctx = contextvars.ContextVar("progress", default="")

class ProgressFilter(logging.Filter):
    def filter(self, record):
        progress = progress_ctx.get()
        record.progress = f"{progress} " if progress else ""
        return True

# Configure logging first with force=True to override any other imports' setup
log_handler = logging.StreamHandler(sys.stdout)
log_handler.addFilter(ProgressFilter())
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(progress)s%(message)s",
    handlers=[log_handler],
    force=True
)
logger = logging.getLogger("main")

# Try to import local modules
try:
    from wordpress_client import WordPressClient
    from spam_classifier import HeuristicClassifier, LLMClassifier, AkismetClassifier, strip_html
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Please make sure you are running the script from its parent directory.")
    sys.exit(1)

def load_config():
    """Load configuration from environment variables and .env file."""
    # Find .env file in the current directory or parent directory
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        # Fallback to general environment search
        load_dotenv(override=True)

def print_banner():
    print("=" * 70)
    print("              WordPress Comment Spam Detector")
    print("=" * 70)

def truncate_text(text: str, max_len: int = 50) -> str:
    """Helper to truncate comment text for display."""
    text = text.replace("\n", " ").replace("\r", "")
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text

def print_report_table(results: list):
    """Prints a beautiful formatted text table of comment classification results."""
    # Columns: ID, Author, Snippet, Verdict, Confidence, Reason
    header_fmt = "| {:<8} | {:<15} | {:<25} | {:<8} | {:<10} | {:<30} |"
    row_fmt    = "| {:<8} | {:<15} | {:<25} | {:<8} | {:<10} | {:<30} |"
    
    separator = "+" + "-"*10 + "+" + "-"*17 + "+" + "-"*27 + "+" + "-"*10 + "+" + "-"*12 + "+" + "-"*32 + "+"
    
    print("\nClassification Report:")
    print(separator)
    print(header_fmt.format("ID", "Author", "Comment Snippet", "Verdict", "Confidence", "Reason"))
    print(separator)
    
    for r in results:
        comment = r["comment"]
        verdict = "SPAM" if r["is_spam"] else "HAM"
        confidence = f"{r['confidence']:.2f}"
        
        # Format field strings
        cid = str(comment.get("id", ""))
        author = truncate_text(comment.get("author_name", "Anonymous"), 15)
        snippet = truncate_text(strip_html(comment.get("content", {}).get("rendered", "")), 25)
        reason = truncate_text(r["reason"], 30)
        
        # To avoid alignment offset due to ANSI escape characters, we format verdict carefully
        # ANSI escape codes count towards length in format, so we pad it manually if colored
        if sys.stdout.isatty():
            # verdict is 8 chars padding. The escape code adds 9 chars.
            # So we pad it manually.
            padded_verdict = f"\033[91m{verdict:<8}\033[0m" if verdict == "SPAM" else f"\033[92m{verdict:<8}\033[0m"
            print(row_fmt.replace("{:<8}", "{}").format(cid, author, snippet, padded_verdict, confidence, reason))
        else:
            print(row_fmt.format(cid, author, snippet, verdict, confidence, reason))
            
    print(separator)

def main():
    print_banner()
    load_config()

    # Define arguments
    parser = argparse.ArgumentParser(description="WordPress Comment Spam Detector API Tool")
    parser.add_argument("--url", default=os.getenv("WP_URL"), help="WordPress site URL")
    parser.add_argument("--username", default=os.getenv("WP_USERNAME"), help="WordPress Username")
    parser.add_argument("--password", default=os.getenv("WP_APP_PASSWORD"), help="WordPress Application Password")
    parser.add_argument("--classifier", choices=["heuristic", "llm", "akismet"], 
                        default=os.getenv("CLASSIFIER_TYPE", "heuristic"), help="Spam Classifier type")
    parser.add_argument("--status", default="hold", help="Comment status to retrieve (e.g. hold, approve, spam, or comma-separated)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of comments to fetch")
    parser.add_argument("--action", choices=["prompt", "mark-spam", "none"], default="prompt",
                        help="Action to perform on detected spam comments: 'prompt' (interactive), 'mark-spam' (automatic), or 'none'")
    parser.add_argument("--gemini-key", default=os.getenv("GEMINI_API_KEY"), help="Google Gemini API Key")
    parser.add_argument("--akismet-key", default=os.getenv("AKISMET_API_KEY"), help="Akismet API Key")
    
    args = parser.parse_args()

    # Validate core arguments
    if not args.url or not args.username or not args.password:
        logger.error("Missing WordPress credentials. Set them in a .env file or pass them as CLI arguments.")
        parser.print_help()
        sys.exit(1)

    # Initialize WordPress client
    try:
        wp_client = WordPressClient(args.url, args.username, args.password)
        wp_client.verify_connection()
    except Exception as e:
        logger.error(f"Could not connect to WordPress: {e}")
        sys.exit(1)

    # Initialize Classifier
    classifier = None
    if args.classifier == "heuristic":
        logger.info("Using HEURISTIC rule-based classifier.")
        classifier = HeuristicClassifier()
    elif args.classifier == "llm":
        logger.info("Using GEMINI LLM classifier.")
        if not args.gemini_key:
            logger.error("Gemini API key is required for LLM classification. Define GEMINI_API_KEY in .env or pass it.")
            sys.exit(1)
        try:
            classifier = LLMClassifier(api_key=args.gemini_key)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM Classifier: {e}")
            sys.exit(1)
    elif args.classifier == "akismet":
        logger.info("Using AKISMET API classifier.")
        if not args.akismet_key:
            logger.error("Akismet API key is required for Akismet classification. Define AKISMET_API_KEY in .env or pass it.")
            sys.exit(1)
        try:
            classifier = AkismetClassifier(api_key=args.akismet_key, blog_url=args.url)
        except Exception as e:
            logger.error(f"Failed to initialize Akismet Classifier: {e}")
            sys.exit(1)

    if not classifier:
        logger.error(f"Unknown classifier type: {args.classifier}")
        sys.exit(1)

    # Fetch comments
    try:
        comments = wp_client.fetch_comments(status=args.status, limit=args.limit)
    except Exception as e:
        logger.error(f"Failed to fetch comments: {e}")
        sys.exit(1)

    if not comments:
        logger.info("No comments found matching the criteria.")
        sys.exit(0)

    # Classify comments concurrently (up to 10 threads)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    spam_comments = []
    marked_inline_count = 0
    failed_inline_count = 0
    total_comments = len(comments)

    logger.info(f"Classifying {total_comments} comments concurrently (up to 10 threads)...")

    def classify_and_act(idx, comment):
        comment_id = comment.get("id")
        author = comment.get("author_name", "Anonymous")
        token = progress_ctx.set(f"[{idx}/{total_comments}]")
        try:
            logger.info(f"Classifying comment #{comment_id} by {author}...")
            classification = classifier.classify(comment)
            res = {
                "comment": comment,
                "is_spam": classification.get("is_spam", False),
                "confidence": classification.get("confidence", 0.0),
                "reason": classification.get("reason", ""),
                "action_taken": None,
                "action_success": False
            }
            
            # Inline WordPress action for mark-spam
            if res["is_spam"] and args.action == "mark-spam":
                logger.info(f"Comment #{comment_id} classified as SPAM. Marking as spam immediately...")
                try:
                    if wp_client.mark_as_spam(comment_id):
                        res["action_taken"] = "mark-spam"
                        res["action_success"] = True
                    else:
                        res["action_taken"] = "mark-spam"
                        res["action_success"] = False
                except Exception as e:
                    logger.error(f"Failed to mark comment #{comment_id} as spam inline: {e}")
                    res["action_taken"] = "mark-spam"
                    res["action_success"] = False
            return res
        except Exception as e:
            logger.error(f"Failed to classify comment #{comment_id}: {e}")
            return {
                "comment": comment,
                "is_spam": False,
                "confidence": 0.0,
                "reason": f"Classification failed: {str(e)}",
                "action_taken": None,
                "action_success": False
            }
        finally:
            progress_ctx.reset(token)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(classify_and_act, i, comment): comment
            for i, comment in enumerate(comments, 1)
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
                if res["is_spam"]:
                    spam_comments.append(res["comment"])
                    if res["action_taken"] == "mark-spam":
                        if res["action_success"]:
                            marked_inline_count += 1
                        else:
                            failed_inline_count += 1
            except Exception as e:
                logger.error(f"Worker thread error during classification: {e}")

    # Sort results by comment ID so the report table is cleanly ordered
    results.sort(key=lambda r: r["comment"].get("id", 0))

    # Print summary table
    print_report_table(results)
    
    # Summary message
    total_spam = len(spam_comments)
    logger.info(f"Analysis complete. Found {total_spam} spam comments out of {len(comments)} analyzed.")

    # Action Phase
    if total_spam == 0:
        logger.info("No action needed. No spam comments identified.")
        sys.exit(0)

    should_mark = False
    if args.action == "mark-spam":
        logger.info(f"Done. Automatically marked {marked_inline_count} of {total_spam} comments as spam on WordPress.")
        if failed_inline_count > 0:
            logger.warning(f"Failed to mark {failed_inline_count} comments as spam.")
        sys.exit(0)
    elif args.action == "prompt":
        # Interactive mode
        try:
            user_input = input(f"\nDo you want to mark these {total_spam} comments as SPAM on WordPress? (y/N): ")
            if user_input.lower().strip() in ["y", "yes"]:
                should_mark = True
            else:
                logger.info("Skipping marking. No changes made to WordPress.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)
    else:
        logger.info("Action set to 'none'. No changes made to WordPress.")

    if should_mark:
        success_count = 0
        logger.info(f"Marking {total_spam} comments as spam concurrently (up to 10 threads)...")

        def process_comment(idx, comment):
            comment_id = comment.get("id")
            token = progress_ctx.set(f"[{idx}/{total_spam}]")
            try:
                if wp_client.mark_as_spam(comment_id):
                    return 1
                return 0
            except Exception as e:
                logger.error(f"Error marking comment #{comment_id}: {e}")
                return 0
            finally:
                progress_ctx.reset(token)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(process_comment, i, comment): i
                for i, comment in enumerate(spam_comments, 1)
            }
            for future in as_completed(futures):
                try:
                    success_count += future.result()
                except Exception as e:
                    logger.error(f"Worker thread error: {e}")

        logger.info(f"Done. Successfully marked {success_count} of {total_spam} comments as spam on WordPress.")

if __name__ == "__main__":
    main()
