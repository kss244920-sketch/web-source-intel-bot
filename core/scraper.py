import asyncio
import os
import re
import json
from typing import Dict, Tuple, List, Optional
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

# Mobile User-Agent fallback in case desktop gets challenged
MOBILE_UA = "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"

# Regex for CSS url(...) references and SourceMapping
CSS_URL_REGEX = re.compile(r"""url\(\s*['"]?(?!data:)([^'")]+)['"]?\s*\)""", re.IGNORECASE)
SOURCEMAP_REGEX = re.compile(r"""//[#@]\s*sourceMappingURL=([^\s]+)""", re.IGNORECASE)


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
    elif ext in ['.json', '.webmanifest'] or 'json' in content_type:
        folder = "assets/configs"
    elif ext in ['.mp4', '.webm', '.ogg', '.mp3', '.wav'] or 'audio' in content_type or 'video' in content_type:
        folder = "assets/media"
    else:
        folder = "assets/misc"

    return folder, raw_name


def format_js_code(code: str) -> str:
    """Lightweight beautifier for minified single-line JS files."""
    if len(code) < 300 or code.count('\n') > len(code) / 120:
        return code
    try:
        # Add clean linebreaks after semicolons and braces
        formatted = re.sub(r';(?!\s*\n)', ';\n', code)
        formatted = re.sub(r'([{}])', r'\n\1\n', formatted)
        formatted = re.sub(r'\n{2,}', '\n', formatted)
        return formatted
    except Exception:
        return code


class WebScraper:
    """Smart Async Website Cloner, Deep Source-Map Unpacker and Asset Downloader."""

    def __init__(self, target_url: str, timeout: float = 7.0, max_concurrency: int = 25, max_assets: int = 90):
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'https://' + target_url
        self.target_url = target_url
        self.domain = urlparse(target_url).netloc
        self.timeout = timeout
        self.max_assets = max_assets
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
        Deep Cloner & Source Map Unpacker:
        - Downloads HTML with Chrome headers and fallback support.
        - Deep extracts HTML, CSS, JS, Fonts, Media, Manifests, and SVG icons.
        - Detects and unpacks .js.map Source Maps into original unminified code!
        - Rewrites URLs for offline viewing.
        """
        files_map: Dict[str, bytes] = {}
        download_queue: List[str] = []
        url_to_local_path: Dict[str, str] = {}
        name_counter: Dict[str, int] = {}
        sourcemap_candidates: List[Tuple[str, str]] = []  # (orig_js_url, map_url)

        transport = httpx.AsyncHTTPTransport(retries=2, verify=False)
        async with httpx.AsyncClient(headers=CHROME_DESKTOP_HEADERS, transport=transport) as client:
            # 1. Fetch main HTML page with smart fallback
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

            # Scan raw HTML for APIs & Keys
            self.intel.analyze_text(raw_html, source_label="index.html")

            soup = BeautifulSoup(raw_html, "html.parser")
            self.intel.extract_metadata_from_soup(soup)

            # Check for <base href="...">
            base_tag = soup.find('base')
            effective_base = urljoin(final_url, base_tag.get('href', '')) if base_tag and base_tag.get('href') else final_url

            # 2. Smart Asset Discovery across HTML5 tags
            tag_attrs = [
                ("link", "href"),
                ("script", "src"),
                ("img", "src"),
                ("img", "data-src"),
                ("source", "src"),
                ("video", "src"),
                ("video", "poster"),
                ("audio", "src"),
                ("object", "data"),
                ("embed", "src"),
                ("use", "href"),
                ("use", "xlink:href"),
            ]

            for tag, attr in tag_attrs:
                for elem in soup.find_all(tag):
                    val = elem.get(attr)
                    if not val or val.startswith("data:"):
                        continue
                    full_url = urljoin(effective_base, val)
                    if full_url not in download_queue:
                        download_queue.append(full_url)

            # Parse srcset for high-res responsive images
            for elem in soup.find_all(["img", "source"]):
                srcset = elem.get("srcset")
                if srcset:
                    for part in srcset.split(","):
                        u = part.strip().split()[0]
                        if u and not u.startswith("data:"):
                            full_url = urljoin(effective_base, u)
                            if full_url not in download_queue:
                                download_queue.append(full_url)

            # OpenGraph Image & Favicons
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                full_og = urljoin(effective_base, og_img.get("content"))
                if full_og not in download_queue:
                    download_queue.append(full_og)

            # Inline style background urls
            for elem in soup.find_all(style=True):
                style_text = elem["style"]
                for match in CSS_URL_REGEX.findall(style_text):
                    clean_u = match.strip()
                    if clean_u and not clean_u.startswith("data:"):
                        full_u = urljoin(effective_base, clean_u)
                        if full_u not in download_queue:
                            download_queue.append(full_u)

            # Cap total queue to max_assets
            download_queue = download_queue[:self.max_assets]

            # 3. Asynchronously download all queued assets
            tasks = [self._fetch_url(client, u) for u in download_queue]
            results = await asyncio.gather(*tasks)

            css_sub_assets_queue = []

            # 4. Process downloaded assets and map to local paths
            for res in results:
                if not res:
                    continue
                orig_url, content_bytes, content_type = res
                folder, base_name = get_asset_folder_and_name(orig_url, content_type)

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

                # Deep scan JS files for APIs, Secrets, and SourceMaps
                if "assets/js" in folder or "javascript" in content_type:
                    try:
                        js_text = content_bytes.decode("utf-8", errors="ignore")
                        self.intel.analyze_text(js_text, source_label=local_path)

                        # Format minified JS for developer readability
                        formatted_js = format_js_code(js_text)
                        if formatted_js != js_text:
                            files_map[local_path] = formatted_js.encode("utf-8")

                        # Check for SourceMappingURL
                        sm_match = SOURCEMAP_REGEX.search(js_text)
                        if sm_match:
                            sm_url = urljoin(orig_url, sm_match.group(1).strip())
                            sourcemap_candidates.append((orig_url, sm_url))
                        elif orig_url.endswith(".js"):
                            # Opportunistically check .js.map
                            sourcemap_candidates.append((orig_url, orig_url + ".map"))
                    except Exception:
                        pass

                # Scan CSS for fonts and images
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
                sub_tasks = [self._fetch_url(client, item[2]) for item in css_sub_assets_queue[:30]]
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

            # 5. SOURCE MAP DEEP UNPACKER (.map files)
            if sourcemap_candidates:
                # Limit to top 5 sourcemap checks to preserve fast execution
                sm_tasks = [self._fetch_url(client, candidate[1]) for candidate in sourcemap_candidates[:5]]
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

            # Remove base tag
            if base_tag:
                base_tag.decompose()

            # Save modified index.html
            modified_html = str(soup)
            files_map["index.html"] = modified_html.encode("utf-8")

            return modified_html, files_map, self.intel
