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
    name = filename.split('?')[0].split('#')[0]
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
    """Enterprise Fast Async Website Cloner and Asset Downloader."""

    def __init__(self, target_url: str, timeout: float = 7.0, max_concurrency: int = 25, max_assets: int = 80):
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'https://' + target_url
        self.target_url = target_url
        self.domain = urlparse(target_url).netloc
        self.timeout = timeout
        self.max_assets = max_assets
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
                    # Ignore single assets > 8MB to protect serverless memory
                    content_length = int(resp.headers.get("content-length", len(resp.content)))
                    if content_length > 8 * 1024 * 1024:
                        return None
                    content_type = resp.headers.get("content-type", "").lower()
                    return url, resp.content, content_type
            except Exception:
                pass
            return None

    async def clone_website(self) -> Tuple[str, Dict[str, bytes], IntelExtractor]:
        """
        Downloads HTML and all linked assets (CSS, JS, Images, Fonts, CSS Sub-assets).
        Rewrites URLs for offline viewing.
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

            # Check for <base href="...">
            base_tag = soup.find('base')
            effective_base_url = urljoin(final_url, base_tag.get('href', '')) if base_tag and base_tag.get('href') else final_url

            # 2. Extract and queue assets from HTML tags
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
                    full_url = urljoin(effective_base_url, val)
                    if full_url not in download_queue:
                        download_queue.append(full_url)

            # Also parse srcset for responsive images
            for img in soup.find_all("img"):
                srcset = img.get("srcset")
                if srcset:
                    for part in srcset.split(","):
                        u = part.strip().split()[0]
                        if u and not u.startswith("data:"):
                            full_url = urljoin(effective_base_url, u)
                            if full_url not in download_queue:
                                download_queue.append(full_url)

            # Extract inline style urls
            for elem in soup.find_all(style=True):
                style_text = elem["style"]
                for match in CSS_URL_REGEX.findall(style_text):
                    clean_u = match.strip()
                    if clean_u and not clean_u.startswith("data:"):
                        full_u = urljoin(effective_base_url, clean_u)
                        if full_u not in download_queue:
                            download_queue.append(full_u)

            # Cap total queue to max_assets to ensure fast processing
            download_queue = download_queue[:self.max_assets]

            # 3. Asynchronously download all queued assets
            tasks = [self._fetch_url(client, u) for u in download_queue]
            results = await asyncio.gather(*tasks)

            css_sub_assets_queue = []

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

                # If asset is JS, scan deeply for APIs & Secrets
                if "assets/js" in folder or "javascript" in content_type:
                    try:
                        js_text = content_bytes.decode("utf-8", errors="ignore")
                        self.intel.analyze_text(js_text, source_label=local_path)
                    except Exception:
                        pass

                # If asset is CSS, extract nested fonts and images
                if "assets/css" in folder or "css" in content_type:
                    try:
                        css_text = content_bytes.decode("utf-8", errors="ignore")
                        for css_u in CSS_URL_REGEX.findall(css_text):
                            css_u = css_u.strip()
                            if css_u and not css_u.startswith("data:"):
                                full_css_asset = urljoin(orig_url, css_u)
                                if full_css_asset not in url_to_local_path and full_css_asset not in css_sub_assets_queue:
                                    css_sub_assets_queue.append((orig_url, css_u, full_css_asset))
                    except Exception:
                        pass

            # Download sub-assets (fonts/images inside CSS)
            if css_sub_assets_queue:
                sub_tasks = [self._fetch_url(client, item[2]) for item in css_sub_assets_queue[:25]]
                sub_results = await asyncio.gather(*sub_tasks)
                for s_res in sub_results:
                    if not s_res:
                        continue
                    s_orig_url, s_content, s_type = s_res
                    s_folder, s_base = get_asset_folder_and_name(s_orig_url, s_type)
                    s_cnt = name_counter.get(s_base, 0)
                    name_counter[s_base] = s_cnt + 1
                    s_fname = f"{os.path.splitext(s_base)[0]}_{s_cnt}{os.path.splitext(s_base)[1]}" if s_cnt > 0 else s_base
                    s_local = f"{s_folder}/{s_fname}"
                    files_map[s_local] = s_content
                    url_to_local_path[s_orig_url] = s_local

            # 5. Rewrite URLs in HTML for 100% offline viewing
            for tag, attr in tag_attrs:
                for elem in soup.find_all(tag):
                    val = elem.get(attr)
                    if not val or val.startswith("data:"):
                        continue
                    full_url = urljoin(effective_base_url, val)
                    if full_url in url_to_local_path:
                        elem[attr] = url_to_local_path[full_url]

            # Remove base tag if present so local relative paths resolve properly
            if base_tag:
                base_tag.decompose()

            # Save modified index.html
            modified_html = str(soup)
            files_map["index.html"] = modified_html.encode("utf-8")

            return modified_html, files_map, self.intel
