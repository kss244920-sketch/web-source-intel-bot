import asyncio
import os
import re
from typing import Dict, Tuple, List, Optional
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
import httpx

from core.extractor import IntelExtractor

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Regex for CSS url(...) references
CSS_URL_REGEX = re.compile(r"""url\(\s*['"]?(?!data:)([^'")]+)['"]?\s*\)""", re.IGNORECASE)


def sanitize_filename(filename: str, default: str = "asset") -> str:
    """Cleans a string to be safely used as a filename."""
    if not filename:
        return default
    # Remove query string / hash
    name = filename.split('?')[0].split('#')[0]
    # Remove illegal characters
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    name = os.path.basename(name)
    return name if name else default


def get_asset_folder_and_name(url: str, content_type: str = "") -> Tuple[str, str]:
    """Determines asset category folder and safe filename."""
    parsed = urlparse(url)
    raw_name = sanitize_filename(unquote(parsed.path))
    ext = os.path.splitext(raw_name)[1].lower()

    if ext in ['.css'] or 'css' in content_type:
        folder = "assets/css"
        if not ext:
            raw_name += ".css"
    elif ext in ['.js', '.mjs', '.cjs'] or 'javascript' in content_type:
        folder = "assets/js"
        if not ext:
            raw_name += ".js"
    elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.avif'] or 'image' in content_type:
        folder = "assets/images"
        if not ext:
            raw_name += ".png"
    elif ext in ['.woff', '.woff2', '.ttf', '.otf', '.eot'] or 'font' in content_type:
        folder = "assets/fonts"
    else:
        folder = "assets/misc"

    return folder, raw_name


class WebScraper:
    """Fast Async Website Cloner and Asset Downloader."""

    def __init__(self, target_url: str, timeout: float = 8.0, max_concurrency: int = 20):
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'https://' + target_url
        self.target_url = target_url
        self.domain = urlparse(target_url).netloc
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.client_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.intel = IntelExtractor(self.target_url)

    async def _fetch_url(self, client: httpx.AsyncClient, url: str) -> Optional[Tuple[str, bytes, str]]:
        """Safely downloads a single resource with timeout and concurrency limiter."""
        async with self.semaphore:
            try:
                resp = await client.get(url, timeout=self.timeout, follow_redirects=True)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "").lower()
                    return url, resp.content, content_type
            except Exception:
                pass
            return None

    async def clone_website(self) -> Tuple[str, Dict[str, bytes], IntelExtractor]:
        """
        Downloads HTML and all linked assets (CSS, JS, Images, Fonts).
        Rewrites URLs for offline viewing.
        Returns:
            - modified_html: str
            - files_map: dict of relative_filepath -> bytes
            - intel: IntelExtractor instance with all discovered APIs and keys
        """
        files_map: Dict[str, bytes] = {}
        download_queue: List[str] = []
        url_to_local_path: Dict[str, str] = {}
        name_counter: Dict[str, int] = {}

        async with httpx.AsyncClient(headers=self.client_headers, verify=False) as client:
            # 1. Fetch main HTML page
            try:
                html_resp = await client.get(self.target_url, timeout=self.timeout, follow_redirects=True)
                raw_html = html_resp.text
                final_url = str(html_resp.url)
            except Exception as e:
                raise RuntimeError(f"Failed to fetch website: {str(e)}")

            # Update base url in intel
            self.intel.base_url = final_url
            self.intel.domain = urlparse(final_url).netloc

            # Scan raw HTML for APIs & Keys
            self.intel.analyze_text(raw_html, source_label="index.html")

            soup = BeautifulSoup(raw_html, "html.parser")
            self.intel.extract_metadata_from_soup(soup)

            # 2. Extract and queue assets from HTML
            # Tags to search: (tag_name, attribute)
            tag_attrs = [
                ("link", "href"),
                ("script", "src"),
                ("img", "src"),
                ("img", "data-src"),
                ("source", "src"),
                ("video", "src"),
                ("audio", "src"),
            ]

            for tag, attr in tag_attrs:
                for elem in soup.find_all(tag):
                    val = elem.get(attr)
                    if not val or val.startswith("data:"):
                        continue
                    full_url = urljoin(final_url, val)
                    if full_url not in download_queue:
                        download_queue.append(full_url)

            # Also scan inline scripts for endpoints
            for s in soup.find_all("script"):
                if s.string:
                    self.intel.analyze_text(s.string, source_label="inline_script")

            # 3. Asynchronously download all assets
            tasks = [self._fetch_url(client, u) for u in download_queue]
            results = await asyncio.gather(*tasks)

            # 4. Process downloaded assets and map to local file paths
            for res in results:
                if not res:
                    continue
                orig_url, content_bytes, content_type = res
                folder, base_name = get_asset_folder_and_name(orig_url, content_type)

                # Avoid filename collisions
                counter = name_counter.get(base_name, 0)
                name_counter[base_name] = counter + 1
                if counter > 0:
                    stem, ext = os.path.splitext(base_name)
                    final_filename = f"{stem}_{counter}{ext}"
                else:
                    final_filename = base_name

                local_path = f"{folder}/{final_filename}"
                files_map[local_path] = content_bytes
                url_to_local_path[orig_url] = local_path

                # If asset is JS, scan deeply for APIs & Secrets!
                if "assets/js" in folder or "javascript" in content_type:
                    try:
                        js_text = content_bytes.decode("utf-8", errors="ignore")
                        self.intel.analyze_text(js_text, source_label=local_path)
                    except Exception:
                        pass

            # 5. Rewrite URLs in HTML for 100% offline viewing
            for tag, attr in tag_attrs:
                for elem in soup.find_all(tag):
                    val = elem.get(attr)
                    if not val or val.startswith("data:"):
                        continue
                    full_url = urljoin(final_url, val)
                    if full_url in url_to_local_path:
                        elem[attr] = url_to_local_path[full_url]

            # Save modified index.html
            modified_html = str(soup)
            files_map["index.html"] = modified_html.encode("utf-8")

            return modified_html, files_map, self.intel
