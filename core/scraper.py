import asyncio
import os
import re
import json
from typing import Dict, Tuple, List, Optional, Set
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
import httpx

from core.extractor import IntelExtractor

# Realistic Desktop Chrome Headers to bypass basic bot-detection & WAF blocks
CHROME_DESKTOP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

MOBILE_UA = "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"

# Regex for CSS url(...) and SourceMapping
CSS_URL_REGEX = re.compile(r"""url\(\s*['"]?(?!data:)([^'")]+)['"]?\s*\)""", re.IGNORECASE)
SOURCEMAP_REGEX = re.compile(r"""//[#@]\s*sourceMappingURL=([^\s]+)""", re.IGNORECASE)

# Regex to detect Webpack, Vite, Nuxt, Next.js dynamic chunk imports inside JS
CHUNK_REGEX = re.compile(
    r"""(?:/|\./|["'`])((?:assets/js|assets/css|static/chunks|_next/static/chunks|_nuxt|static/js)/[a-zA-Z0-9_\-]+\.(?:js|css))["'`]""",
    re.IGNORECASE
)


def get_clean_relative_path(url: str, content_type: str = "") -> str:
    """Determines accurate, clean relative file path preserving original directory hierarchy."""
    parsed = urlparse(url)
    raw_path = unquote(parsed.path).lstrip("/")
    
    # If path is empty, make it index.html
    if not raw_path:
        return "index.html"

    # Strip illegal characters
    parts = raw_path.split("/")
    cleaned_parts = [re.sub(r'[\\:*?"<>|]', '_', p) for p in parts if p]
    if not cleaned_parts:
        cleaned_parts = ["asset"]

    filename = cleaned_parts[-1]
    name, ext = os.path.splitext(filename)

    # If file has no extension, infer from Content-Type
    if not ext:
        if 'javascript' in content_type:
            cleaned_parts[-1] = filename + ".js"
        elif 'css' in content_type:
            cleaned_parts[-1] = filename + ".css"
        elif 'json' in content_type:
            cleaned_parts[-1] = filename + ".json"
        elif 'png' in content_type:
            cleaned_parts[-1] = filename + ".png"
        elif 'jpeg' in content_type or 'jpg' in content_type:
            cleaned_parts[-1] = filename + ".jpg"
        elif 'svg' in content_type:
            cleaned_parts[-1] = filename + ".svg"
        elif 'font' in content_type or 'woff2' in content_type:
            cleaned_parts[-1] = filename + ".woff2"

    return "/".join(cleaned_parts)


def format_js_code(code: str) -> str:
    """Lightweight beautifier for minified single-line JS files."""
    if len(code) < 300 or code.count('\n') > len(code) / 120:
        return code
    try:
        formatted = re.sub(r';(?!\s*\n)', ';\n', code)
        formatted = re.sub(r'([{}])', r'\n\1\n', formatted)
        formatted = re.sub(r'\n{2,}', '\n', formatted)
        return formatted
    except Exception:
        return code


class WebScraper:
    """True Deep Website Cloner, Recursive Chunk Spider & Source-Map Unpacker."""

    def __init__(self, target_url: str, timeout: float = 7.0, max_concurrency: int = 30, max_chunks: int = 150):
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'https://' + target_url
        self.target_url = target_url
        self.domain = urlparse(target_url).netloc
        self.timeout = timeout
        self.max_chunks = max_chunks
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.intel = IntelExtractor(self.target_url)

    async def _fetch_url(self, client: httpx.AsyncClient, url: str) -> Optional[Tuple[str, bytes, str]]:
        """Safely downloads a single resource with timeout and concurrency limiter."""
        async with self.semaphore:
            try:
                resp = await client.get(url, timeout=self.timeout, follow_redirects=True)
                if resp.status_code == 200:
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
        Deep Spider Cloner:
        - Downloads HTML.
        - Spiders and recursively downloads all dynamic Webpack/Vite chunks.
        - Scans every chunk for hidden APIs, routes, and secrets.
        - Unpacks sourcemaps if available.
        - Rewrites URLs for offline viewing.
        """
        files_map: Dict[str, bytes] = {}
        download_queue: List[str] = []
        downloaded_urls: Set[str] = set()
        url_to_local_path: Dict[str, str] = {}
        sourcemap_candidates: List[Tuple[str, str]] = []

        transport = httpx.AsyncHTTPTransport(retries=2, verify=False)
        async with httpx.AsyncClient(headers=CHROME_DESKTOP_HEADERS, transport=transport) as client:
            # 1. Fetch main HTML page
            try:
                html_resp = await client.get(self.target_url, timeout=self.timeout, follow_redirects=True)
                if html_resp.status_code in [403, 406]:
                    html_resp = await client.get(
                        self.target_url,
                        headers={"User-Agent": MOBILE_UA},
                        timeout=self.timeout,
                        follow_redirects=True
                    )
                raw_html = html_resp.text
                final_url = str(html_resp.url)
            except Exception:
                if self.target_url.startswith("https://"):
                    fallback_url = "http://" + self.target_url[8:]
                    html_resp = await client.get(fallback_url, timeout=self.timeout, follow_redirects=True)
                    raw_html = html_resp.text
                    final_url = str(html_resp.url)
                else:
                    raise

            # Update base url in intel
            self.intel.base_url = final_url
            self.intel.domain = urlparse(final_url).netloc
            parts = self.intel.domain.split(".")
            self.intel.root_domain = ".".join(parts[-2:]) if len(parts) >= 2 else self.intel.domain

            # Scan raw HTML
            self.intel.analyze_text(raw_html, source_label="index.html")

            soup = BeautifulSoup(raw_html, "html.parser")
            self.intel.extract_metadata_from_soup(soup)

            base_tag = soup.find('base')
            effective_base = urljoin(final_url, base_tag.get('href', '')) if base_tag and base_tag.get('href') else final_url

            # 2. Extract initial assets from HTML tags
            tag_attrs = [
                ("link", "href"),
                ("script", "src"),
                ("img", "src"),
                ("img", "data-src"),
                ("source", "src"),
                ("video", "src"),
                ("video", "poster"),
                ("audio", "src"),
            ]

            for tag, attr in tag_attrs:
                for elem in soup.find_all(tag):
                    val = elem.get(attr)
                    if not val or val.startswith("data:"):
                        continue
                    full_url = urljoin(effective_base, val)
                    if full_url not in download_queue:
                        download_queue.append(full_url)

            # 3. Round 1: Asynchronously download initial assets
            tasks = [self._fetch_url(client, u) for u in download_queue[:60]]
            results = await asyncio.gather(*tasks)

            dynamic_chunks_queue: List[str] = []

            for res in results:
                if not res:
                    continue
                orig_url, content_bytes, content_type = res
                downloaded_urls.add(orig_url)
                local_path = get_clean_relative_path(orig_url, content_type)
                files_map[local_path] = content_bytes
                url_to_local_path[orig_url] = local_path

                # Deep scan JS & spider dynamic chunks
                if local_path.endswith(".js") or "javascript" in content_type:
                    try:
                        js_text = content_bytes.decode("utf-8", errors="ignore")
                        self.intel.analyze_text(js_text, source_label=local_path)

                        # SPIDER: Extract all referenced dynamic Webpack/Vite chunks
                        for match in CHUNK_REGEX.findall(js_text):
                            chunk_path = match.strip()
                            full_chunk_url = urljoin(final_url, chunk_path)
                            if full_chunk_url not in downloaded_urls and full_chunk_url not in dynamic_chunks_queue:
                                dynamic_chunks_queue.append(full_chunk_url)

                        # Format minified JS
                        formatted = format_js_code(js_text)
                        if formatted != js_text:
                            files_map[local_path] = formatted.encode("utf-8")

                        # Check for SourceMaps
                        sm_match = SOURCEMAP_REGEX.search(js_text)
                        if sm_match:
                            sm_url = urljoin(orig_url, sm_match.group(1).strip())
                            sourcemap_candidates.append((orig_url, sm_url))
                        elif orig_url.endswith(".js"):
                            sourcemap_candidates.append((orig_url, orig_url + ".map"))
                    except Exception:
                        pass

                # Scan CSS for fonts and background images
                if local_path.endswith(".css") or "css" in content_type:
                    try:
                        css_text = content_bytes.decode("utf-8", errors="ignore")
                        for css_u in CSS_URL_REGEX.findall(css_text):
                            css_u = css_u.strip()
                            if css_u and not css_u.startswith("data:"):
                                full_css_asset = urljoin(orig_url, css_u)
                                if full_css_asset not in downloaded_urls and full_css_asset not in dynamic_chunks_queue:
                                    dynamic_chunks_queue.append(full_css_asset)
                    except Exception:
                        pass

            # 4. Round 2: DYNAMIC CHUNKS SPIDER (Download up to max_chunks referenced JS chunks!)
            if dynamic_chunks_queue:
                chunk_tasks = [self._fetch_url(client, u) for u in dynamic_chunks_queue[:self.max_chunks]]
                chunk_results = await asyncio.gather(*chunk_tasks)

                for c_res in chunk_results:
                    if not c_res:
                        continue
                    c_url, c_bytes, c_type = c_res
                    downloaded_urls.add(c_url)
                    c_local_path = get_clean_relative_path(c_url, c_type)
                    files_map[c_local_path] = c_bytes
                    url_to_local_path[c_url] = c_local_path

                    # Deep Scan the internal chunk for APIs & Routes
                    if c_local_path.endswith(".js") or "javascript" in c_type:
                        try:
                            c_text = c_bytes.decode("utf-8", errors="ignore")
                            self.intel.analyze_text(c_text, source_label=c_local_path)

                            # Check for sourcemap in chunk
                            sm_match = SOURCEMAP_REGEX.search(c_text)
                            if sm_match:
                                sourcemap_candidates.append((c_url, urljoin(c_url, sm_match.group(1).strip())))
                        except Exception:
                            pass

            # 5. SOURCE MAP DEEP UNPACKER (.map files)
            if sourcemap_candidates:
                sm_tasks = [self._fetch_url(client, candidate[1]) for candidate in sourcemap_candidates[:6]]
                sm_results = await asyncio.gather(*sm_tasks)
                for sm_res in sm_results:
                    if not sm_res:
                        continue
                    sm_url, sm_bytes, _ = sm_res
                    try:
                        sm_json = json.loads(sm_bytes.decode("utf-8", errors="ignore"))
                        sources = sm_json.get("sources", [])
                        contents = sm_json.get("sourcesContent", [])
                        if sources and contents:
                            self.intel.sourcemaps_found.append(sm_url)
                            for src_path, src_content in zip(sources, contents):
                                if src_content and isinstance(src_content, str):
                                    clean_p = src_path.replace("webpack:///", "").replace("../", "").lstrip("/")
                                    files_map[f"original_src/{clean_p}"] = src_content.encode("utf-8")
                    except Exception:
                        pass

            # 6. Rewrite URLs in HTML for offline viewing
            for tag, attr in tag_attrs:
                for elem in soup.find_all(tag):
                    val = elem.get(attr)
                    if not val or val.startswith("data:"):
                        continue
                    full_url = urljoin(effective_base, val)
                    if full_url in url_to_local_path:
                        elem[attr] = url_to_local_path[full_url]

            if base_tag:
                base_tag.decompose()

            # Save modified index.html
            modified_html = str(soup)
            files_map["index.html"] = modified_html.encode("utf-8")

            return modified_html, files_map, self.intel
