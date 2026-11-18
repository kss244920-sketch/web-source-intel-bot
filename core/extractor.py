import re
from typing import Dict, List, Set, Any
from urllib.parse import urlparse

# Famous LinkFinder Regex adapted for high-accuracy client-side route discovery
LINKFINDER_REGEX = re.compile(
    r"""(?:"|'|`)"""
    r"""("""
    r"""(?:[a-zA-Z]{1,10}://|//)[^"'/\s]{1,}\.[a-zA-Z]{2,}(?::[0-9]{1,5})?[^"'\s]{0,}"""
    r"""|"""
    r"""(?:/|\.\./|\./)[^"'><,;| *()%$^/\\\[\]][^"'><,;|()]{1,}"""
    r"""|"""
    r"""[a-zA-Z0-9_\-/]{1,}/[a-zA-Z0-9_\-/]{1,}\.(?:json|action|php|aspx|jsp|xml|do)(?:[\?#][^"'\\\s]{0,})?"""
    r"""|"""
    r"""/(?:api|v[0-9]|auth|user|admin|wallet|game|pay|service|order|history|account|ws|socket|gateway|graphql)[a-zA-Z0-9_\-/.?=&%#]*"""
    r""")"""
    r"""(?:"|'|`)""",
    re.IGNORECASE
)

WEBSOCKET_REGEX = re.compile(r"""wss?://[^\s"'`<>()\\]+""", re.IGNORECASE)
GRAPHQL_REGEX = re.compile(r"""(?:mutation|query)\s+[a-zA-Z0-9_]+\s*(?:\([^)]*\))?\s*\{""", re.IGNORECASE)

# Comprehensive secret & token signatures (SecretFinder + TruffleHog patterns)
PATTERNS_SECRETS = {
    "Google / Firebase API Key": re.compile(r"""AIza[0-9A-Za-z-_]{35}"""),
    "Razorpay Key ID": re.compile(r"""rzp_(?:test|live)_[0-9a-zA-Z]{14,}"""),
    "Stripe Publishable Key": re.compile(r"""pk_(?:test|live)_[0-9a-zA-Z]{24,}"""),
    "AWS Access Key ID": re.compile(r"""AKIA[0-9A-Z]{16}"""),
    "Telegram Bot Token": re.compile(r"""[0-9]{8,10}:[a-zA-Z0-9_-]{35}"""),
    "JWT Bearer Token": re.compile(r"""eyJ[A-Za-z0-9-_=]{10,}\.eyJ[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_.+/=]{10,}"""),
    "GitHub Personal Access Token": re.compile(r"""ghp_[0-9a-zA-Z]{36}"""),
    "Slack Webhook": re.compile(r"""https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+"""),
    "Discord Webhook": re.compile(r"""https://discord(?:app)?\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_-]+"""),
    "Frontend Env Variables": re.compile(r"""(?:REACT_APP_|NEXT_PUBLIC_|VITE_)[A-Z0-9_]{3,}"""),
}

FIREBASE_CONFIG_REGEX = re.compile(
    r"""apiKey\s*:\s*["']([A-Za-z0-9_-]{30,})["'][\s\S]*?projectId\s*:\s*["']([^"']+)["']""",
    re.IGNORECASE
)


class IntelExtractor:
    """Enterprise-grade client-side API, Route, and Secret Finder."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.relative_apis: Set[str] = set()
        self.external_apis: Set[str] = set()
        self.websockets: Set[str] = set()
        self.graphql_endpoints: Set[str] = set()
        self.detected_keys: Dict[str, Set[str]] = {key: set() for key in PATTERNS_SECRETS}
        self.metadata: Dict[str, Any] = {}

    def analyze_text(self, content: str, source_label: str = "source"):
        """Scans JS, HTML, or JSON content for routes, APIs, and leaked secrets."""
        if not content or not isinstance(content, str):
            return

        # 1. LinkFinder Deep Route Extraction
        for match in LINKFINDER_REGEX.findall(content):
            item = match.strip()
            if not item:
                continue

            # Filter out standard non-API file extensions
            if item.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif', '.ico', '.css', '.woff', '.woff2', '.ttf')):
                continue

            if item.startswith(('http://', 'https://', '//')):
                full = "https:" + item if item.startswith("//") else item
                parsed = urlparse(full)
                if any(x in full.lower() for x in ['/api', '/v1', '/v2', '/auth', '/user', '/socket', '/ws', '/graphql', 'backend', 'gateway']):
                    self.external_apis.add(full)
                elif parsed.netloc and parsed.netloc != self.domain:
                    self.external_apis.add(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
            elif item.startswith('/'):
                self.relative_apis.add(item)

        # 2. WebSockets & Realtime Channels
        for match in WEBSOCKET_REGEX.findall(content):
            self.websockets.add(match.strip())

        # 3. GraphQL Queries & Endpoints
        if "/graphql" in content.lower():
            self.graphql_endpoints.add("/graphql")
        for match in GRAPHQL_REGEX.findall(content):
            self.graphql_endpoints.add(match.strip())

        # 4. Secret & Config Detection
        for key_type, pattern in PATTERNS_SECRETS.items():
            for m in pattern.findall(content):
                self.detected_keys[key_type].add(m)

        # 5. Firebase Config
        for fb in FIREBASE_CONFIG_REGEX.findall(content):
            self.detected_keys["Google / Firebase API Key"].add(f"apiKey: {fb[0]}, projectId: {fb[1]}")

    def extract_metadata_from_soup(self, soup):
        """Extracts complete SEO, title, manifest, and OpenGraph metadata."""
        title = soup.find('title')
        self.metadata['title'] = title.get_text().strip() if title else self.domain

        meta_desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        self.metadata['description'] = meta_desc.get('content', '').strip() if meta_desc else ''

        og_image = soup.find('meta', attrs={'property': 'og:image'})
        self.metadata['og_image'] = og_image.get('content', '').strip() if og_image else ''

        icon = soup.find('link', rel=lambda x: x and ('icon' in x.lower() or 'shortcut' in x.lower()))
        self.metadata['favicon'] = icon.get('href', '').strip() if icon else ''

        generator = soup.find('meta', attrs={'name': 'generator'})
        if generator:
            self.metadata['framework'] = generator.get('content', '').strip()

    def get_summary_report(self) -> Dict[str, Any]:
        """Returns structured JSON summary of all findings."""
        clean_keys = {k: list(v) for k, v in self.detected_keys.items() if v}
        return {
            "target_url": self.base_url,
            "domain": self.domain,
            "metadata": self.metadata,
            "statistics": {
                "total_relative_apis": len(self.relative_apis),
                "total_external_apis": len(self.external_apis),
                "total_websockets": len(self.websockets),
                "total_graphql": len(self.graphql_endpoints),
                "total_secrets_detected": sum(len(v) for v in clean_keys.values())
            },
            "apis": {
                "relative_endpoints": sorted(list(self.relative_apis)),
                "external_and_backend_apis": sorted(list(self.external_apis)),
                "websocket_endpoints": sorted(list(self.websockets)),
                "graphql_queries_or_endpoints": sorted(list(self.graphql_endpoints))
            },
            "detected_configs_and_keys": clean_keys
        }

    def generate_text_report(self) -> str:
        """Generates formatted, comprehensive text intel report."""
        report = []
        report.append("=" * 65)
        report.append(f"   A-TO-Z INTEL & API REPORT")
        report.append(f"   Target Domain: {self.domain}")
        report.append(f"   Target URL   : {self.base_url}")
        report.append("=" * 65)
        report.append("")

        report.append("--- [1] RELATIVE API ROUTES & ENDPOINTS ---")
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

        report.append("--- [3] WEBSOCKET & REALTIME CHANNELS ---")
        if self.websockets:
            for ws in sorted(self.websockets):
                report.append(f"  • {ws}")
        else:
            report.append("  (No websocket endpoints detected)")
        report.append("")

        report.append("--- [4] GRAPHQL ENDPOINTS ---")
        if self.graphql_endpoints:
            for g in sorted(self.graphql_endpoints):
                report.append(f"  • {g}")
        else:
            report.append("  (No GraphQL endpoints detected)")
        report.append("")

        report.append("--- [5] DETECTED CONFIGS, TOKENS & PUBLIC KEYS ---")
        found_any = False
        for k, v in self.detected_keys.items():
            if v:
                found_any = True
                report.append(f"  [{k}] ({len(v)} detected):")
                for item in sorted(v):
                    report.append(f"    - {item}")
        if not found_any:
            report.append("  (No hardcoded public keys or configs detected)")
        report.append("")

        report.append("=" * 65)
        report.append("   Generated by Advance WebSource & Intel Bot")
        report.append("=" * 65)
        return "\n".join(report)
