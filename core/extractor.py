import re
from typing import Dict, List, Set, Any
from urllib.parse import urlparse

# Regular expressions for API endpoints and routes
RELATIVE_API_REGEX = re.compile(
    r"""(?:"|'|`)(/(?:api|v[0-9]|auth|user|admin|wallet|game|pay|service|order|history|account|ws|socket)[a-zA-Z0-9_\-/.?=&%]*)(?:"|'|`)""",
    re.IGNORECASE
)

ABSOLUTE_URL_REGEX = re.compile(
    r"""https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?::[0-9]{1,5})?(?:/[^\s"'`<>()\\]*)?""",
    re.IGNORECASE
)

WEBSOCKET_REGEX = re.compile(
    r"""wss?://[^\s"'`<>()\\]+""",
    re.IGNORECASE
)

FETCH_AXIOS_REGEX = re.compile(
    r"""(?:fetch|axios(?:\.get|\.post|\.put|\.delete)?)\s*\(\s*['"`]([^'"`]+)['"`]""",
    re.IGNORECASE
)

# Regular expressions for detected keys and configurations
PATTERNS_SECRETS = {
    "Google / Cloud API Key": re.compile(r"""AIza[0-9A-Za-z-_]{35}"""),
    "Razorpay Key": re.compile(r"""rzp_(?:test|live)_[0-9a-zA-Z]{14,}"""),
    "Stripe Publishable Key": re.compile(r"""pk_(?:test|live)_[0-9a-zA-Z]{24,}"""),
    "Telegram Bot Token": re.compile(r"""[0-9]{8,10}:[a-zA-Z0-9_-]{35}"""),
    "Firebase Config": re.compile(r"""apiKey\s*:\s*["']([A-Za-z0-9_-]{30,})["']"""),
    "JWT Bearer Token": re.compile(r"""eyJ[A-Za-z0-9-_=]{10,}\.eyJ[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_.+/=]{10,}"""),
    "Frontend Env Variables": re.compile(r"""(?:REACT_APP_|NEXT_PUBLIC_|VITE_)[A-Z0-9_]{3,}"""),
}


class IntelExtractor:
    """Extracts all embedded APIs, routes, websockets, and public config keys from code."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.relative_apis: Set[str] = set()
        self.external_apis: Set[str] = set()
        self.websockets: Set[str] = set()
        self.detected_keys: Dict[str, Set[str]] = {key: set() for key in PATTERNS_SECRETS}
        self.metadata: Dict[str, Any] = {}

    def analyze_text(self, content: str, source_label: str = "source"):
        """Scans raw JS/HTML text for APIs, secrets, and routes."""
        if not content or not isinstance(content, str):
            return

        # 1. Extract Relative API Endpoints
        for match in RELATIVE_API_REGEX.findall(content):
            cleaned = match.strip()
            if len(cleaned) > 2 and not cleaned.endswith(('.css', '.png', '.jpg', '.jpeg', '.svg', '.gif')):
                self.relative_apis.add(cleaned)

        # 2. Extract Fetch / Axios Calls
        for match in FETCH_AXIOS_REGEX.findall(content):
            cleaned = match.strip()
            if cleaned.startswith('/'):
                self.relative_apis.add(cleaned)
            elif cleaned.startswith('http'):
                self.external_apis.add(cleaned)

        # 3. Extract WebSockets
        for match in WEBSOCKET_REGEX.findall(content):
            self.websockets.add(match.strip())

        # 4. Extract Absolute URLs (Filter out standard static assets and CDN anchors)
        for match in ABSOLUTE_URL_REGEX.findall(content):
            clean_url = match.strip().rstrip(".,;'\")")
            parsed = urlparse(clean_url)
            # Check if url points to API or backend or another host
            if any(k in clean_url.lower() for k in ['/api', '/v1', '/v2', '/auth', '/user', '/socket', '/ws']):
                self.external_apis.add(clean_url)
            elif parsed.netloc and parsed.netloc != self.domain and not clean_url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css')):
                # Keep significant backend/service hosts
                if any(x in clean_url.lower() for x in ['backend', 'server', 'gateway', 'cloud', 'service']):
                    self.external_apis.add(clean_url)

        # 5. Detect Keys & Configs
        for key_type, pattern in PATTERNS_SECRETS.items():
            matches = pattern.findall(content)
            for m in matches:
                # Store detected matches (masked for security if needed)
                self.detected_keys[key_type].add(m)

    def extract_metadata_from_soup(self, soup):
        """Extracts SEO, social, and web app metadata from BeautifulSoup."""
        title = soup.find('title')
        self.metadata['title'] = title.get_text().strip() if title else self.domain

        # Meta tags
        meta_desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        self.metadata['description'] = meta_desc.get('content', '').strip() if meta_desc else ''

        # OpenGraph & Icons
        og_image = soup.find('meta', attrs={'property': 'og:image'})
        self.metadata['og_image'] = og_image.get('content', '').strip() if og_image else ''

        icon = soup.find('link', rel=lambda x: x and ('icon' in x.lower() or 'shortcut' in x.lower()))
        self.metadata['favicon'] = icon.get('href', '').strip() if icon else ''

    def get_summary_report(self) -> Dict[str, Any]:
        """Returns structured JSON report of all findings."""
        clean_keys = {k: list(v) for k, v in self.detected_keys.items() if v}
        return {
            "target_url": self.base_url,
            "domain": self.domain,
            "metadata": self.metadata,
            "statistics": {
                "total_relative_apis": len(self.relative_apis),
                "total_external_apis": len(self.external_apis),
                "total_websockets": len(self.websockets),
                "total_keys_found": sum(len(v) for v in clean_keys.values())
            },
            "apis": {
                "relative_endpoints": sorted(list(self.relative_apis)),
                "external_and_backend_apis": sorted(list(self.external_apis)),
                "websocket_endpoints": sorted(list(self.websockets))
            },
            "detected_configs_and_keys": clean_keys
        }

    def generate_text_report(self) -> str:
        """Generates a formatted text file content with A-to-Z findings."""
        report = []
        report.append("=" * 60)
        report.append(f"   A-TO-Z INTEL & API REPORT FOR: {self.domain}")
        report.append(f"   Target URL: {self.base_url}")
        report.append("=" * 60)
        report.append("")

        report.append("--- [1] RELATIVE API ENDPOINTS & ROUTES ---")
        if self.relative_apis:
            for api in sorted(self.relative_apis):
                report.append(f"  • {api}")
        else:
            report.append("  (No relative endpoints identified)")
        report.append("")

        report.append("--- [2] BACKEND / EXTERNAL APIS & SERVICES ---")
        if self.external_apis:
            for api in sorted(self.external_apis):
                report.append(f"  • {api}")
        else:
            report.append("  (No external API endpoints identified)")
        report.append("")

        report.append("--- [3] WEBSOCKET CONNECTIONS ---")
        if self.websockets:
            for ws in sorted(self.websockets):
                report.append(f"  • {ws}")
        else:
            report.append("  (No websocket endpoints detected)")
        report.append("")

        report.append("--- [4] DETECTED CONFIGS, TOKENS & PUBLIC KEYS ---")
        found_any_key = False
        for k, v in self.detected_keys.items():
            if v:
                found_any_key = True
                report.append(f"  [{k}] ({len(v)} found):")
                for item in sorted(v):
                    report.append(f"    - {item}")
        if not found_any_key:
            report.append("  (No hardcoded public keys or configs detected)")
        report.append("")

        report.append("=" * 60)
        report.append("   Generated by Advance WebSource & Intel Bot")
        report.append("=" * 60)
        return "\n".join(report)
