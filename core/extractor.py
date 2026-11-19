import re
from typing import Dict, List, Set, Any
from urllib.parse import urlparse

# Accurate API endpoint discovery pattern
REAL_API_REGEX = re.compile(
    r"""(?:"|'|`)(/(?:api|webapi|v[0-9]|wallet|game|pay|user|auth|admin|member|lottery|order|trans|record|activity|wash|bet|points)[a-zA-Z0-9_\-/.?=&%#]*)(?:"|'|`)""",
    re.IGNORECASE
)

# General LinkFinder pattern for deep exploration
LINKFINDER_REGEX = re.compile(
    r"""(?:"|'|`)"""
    r"""("""
    r"""(?:[a-zA-Z]{1,10}://|//)[^"'/\s]{1,}\.[a-zA-Z]{2,}(?::[0-9]{1,5})?[^"'\s]{0,}"""
    r"""|"""
    r"""/(?:api|webapi|v[0-9]|wallet|game|pay|user|auth|admin|member|lottery|order|trans|record)[a-zA-Z0-9_\-/.?=&%#]*"""
    r""")"""
    r"""(?:"|'|`)""",
    re.IGNORECASE
)

# SPA Router Regex (React Router, Vue Router, HashRouter paths like /#/main, /#/wallet)
HASH_ROUTE_REGEX = re.compile(r"""/#/[a-zA-Z0-9_\-/?=&]+""", re.IGNORECASE)
SPA_PATH_REGEX = re.compile(r"""(?:path\s*:\s*|to\s*=\s*|push\s*\(\s*)["'`]((?:/#/|/)[a-zA-Z0-9_\-/:?=&]+)["'`]""", re.IGNORECASE)

WEBSOCKET_REGEX = re.compile(r"""wss?://[^\s"'`<>()\\]+""", re.IGNORECASE)
GRAPHQL_REGEX = re.compile(r"""(?:mutation|query)\s+[a-zA-Z0-9_]+\s*(?:\([^)]*\))?\s*\{""", re.IGNORECASE)

# Comprehensive secret & token signatures
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
    """True Deep Reverse-Engineering & API Intelligence Engine."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        parts = self.domain.split(".")
        self.root_domain = ".".join(parts[-2:]) if len(parts) >= 2 else self.domain

        self.relative_apis: Set[str] = set()
        self.external_apis: Set[str] = set()
        self.websockets: Set[str] = set()
        self.graphql_endpoints: Set[str] = set()
        self.spa_routes: Set[str] = set()
        self.subdomains: Set[str] = set()
        self.detected_keys: Dict[str, Set[str]] = {key: set() for key in PATTERNS_SECRETS}
        self.metadata: Dict[str, Any] = {}
        self.sourcemaps_found: List[str] = []

    def is_valid_endpoint(self, path: str) -> bool:
        """Filters out non-API assets and garbage strings."""
        lower = path.lower()
        if lower.endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif', '.ico', '.css', '.woff', '.woff2', '.ttf', '.js', '.map', '.html')):
            return False
        if len(path) < 3 or len(path) > 120:
            return False
        # Avoid random long hash strings without slashes
        if "/" not in path.strip("/"):
            return False
        return True

    def analyze_text(self, content: str, source_label: str = "source"):
        """Scans JS, HTML, or JSON content for deep routes, APIs, subdomains, and secrets."""
        if not content or not isinstance(content, str):
            return

        # 1. Real API Endpoints extraction
        for ep in REAL_API_REGEX.findall(content):
            clean = ep.strip()
            if self.is_valid_endpoint(clean):
                self.relative_apis.add(clean)

        # 2. General LinkFinder extraction
        for match in LINKFINDER_REGEX.findall(content):
            item = match.strip()
            if not item:
                continue

            if item.startswith(('http://', 'https://', '//')):
                full = "https:" + item if item.startswith("//") else item
                parsed = urlparse(full)
                if parsed.netloc:
                    if self.root_domain in parsed.netloc:
                        self.subdomains.add(parsed.netloc)

                    if any(x in full.lower() for x in ['/api', '/webapi', '/v1', '/v2', '/auth', '/user', '/socket', '/ws', '/graphql', 'backend', 'gateway']):
                        self.external_apis.add(full)
                    elif parsed.netloc != self.domain:
                        self.external_apis.add(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
            elif item.startswith('/'):
                if self.is_valid_endpoint(item):
                    self.relative_apis.add(item)

        # 3. SPA Hidden Routes (React/Vue/HashRouter)
        for hr in HASH_ROUTE_REGEX.findall(content):
            self.spa_routes.add(hr.strip())

        for r in SPA_PATH_REGEX.findall(content):
            clean_r = r.strip()
            if not clean_r.endswith(('.js', '.css', '.png', '.jpg')):
                self.spa_routes.add(clean_r)

        # 4. WebSockets & Realtime Channels
        for match in WEBSOCKET_REGEX.findall(content):
            self.websockets.add(match.strip())

        # 5. GraphQL Queries
        if "/graphql" in content.lower():
            self.graphql_endpoints.add("/graphql")
        for match in GRAPHQL_REGEX.findall(content):
            self.graphql_endpoints.add(match.strip())

        # 6. Secret & Config Detection
        for key_type, pattern in PATTERNS_SECRETS.items():
            for m in pattern.findall(content):
                self.detected_keys[key_type].add(m)

        # 7. Firebase Config
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

    def generate_api_client_py(self) -> str:
        """Auto-generates a ready-to-run Python API Client (Reverse-API-Engineer style)."""
        endpoints = sorted(list(self.relative_apis))[:35]
        methods_code = []

        for i, ep in enumerate(endpoints):
            # Clean pythonic function name
            func_name = re.sub(r'[^a-zA-Z0-9_]', '_', ep.strip('/')).lower()
            func_name = re.sub(r'_+', '_', func_name).strip('_')
            if not func_name or func_name[0].isdigit():
                func_name = f"api_{func_name}"

            methods_code.append(
                f"    def {func_name}(self, payload: dict = None, headers: dict = None):\n"
                f"        \"\"\"Endpoint: {ep}\"\"\"\n"
                f"        url = f\"{{self.base_url}}{ep}\"\n"
                f"        if payload:\n"
                f"            return self.session.post(url, json=payload, headers=headers)\n"
                f"        return self.session.get(url, headers=headers)\n"
            )

        methods_str = "\n".join(methods_code) if methods_code else "    pass\n"

        code = f"""# ==========================================================
# 🤖 Auto-Generated Python API Client for {self.domain}
# Generated by Advance WebSource & Intel Bot
# ==========================================================

import requests

class {re.sub(r'[^a-zA-Z0-9]', '', self.domain.title())}Client:
    \"\"\"Reverse-engineered API client for {self.domain}\"\"\"

    def __init__(self, base_url: str = "{self.base_url.rstrip('/')}"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({{
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }})

{methods_str}

if __name__ == "__main__":
    client = {re.sub(r'[^a-zA-Z0-9]', '', self.domain.title())}Client()
    print("🚀 API Client initialized for: {self.domain}")
    print("Total methods generated: {len(endpoints)}")
    print("Call available endpoints using client.<method_name>()")
"""
        return code

    def generate_ai_clone_prompt(self) -> str:
        """Generates an AI Prompt Blueprint for Cursor/Claude/ChatGPT (gitreverse style)."""
        routes_list = "\n".join([f"- `{r}`" for r in sorted(list(self.spa_routes))[:20]]) or "- Default single page"
        apis_list = "\n".join([f"- `{a}`" for a in sorted(list(self.relative_apis))[:20]]) or "- Client-side only"

        prompt = f"""# 🎯 AI Recreate Prompt Blueprint for {self.domain}
*Copy-paste the prompt below into Cursor, Claude 3.5 Sonnet, or ChatGPT to recreate this web app:*

---

```text
You are a senior full-stack developer. Build a modern, pixel-perfect clone of the web application "{self.domain}" ({self.metadata.get('title', self.domain)}).

Technical Architecture:
- Framework: React with Vite and Tailwind CSS (or Next.js App Router).
- State Management: Zustand or React Context.
- Icons: Lucide React.
- Routing: Client-side routing with the following identified screens:
{routes_list}

Identified Backend API Endpoints to simulate/integrate:
{apis_list}

Key Instructions:
1. Recreate the complete UI layout with responsive mobile and desktop views.
2. Build mock API handlers with realistic sample data for all the listed endpoints.
3. Ensure smooth animations, active tab navigation, and clean component structure in src/components.
```

---
*Generated by Advance WebSource & Intel Bot (Owner: @owAtom | Channel: @OwAbyss)*
"""
        return prompt

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
                "total_spa_routes": len(self.spa_routes),
                "total_subdomains": len(self.subdomains),
                "total_secrets_detected": sum(len(v) for v in clean_keys.values()),
                "sourcemaps_unpacked": len(self.sourcemaps_found)
            },
            "apis": {
                "relative_endpoints": sorted(list(self.relative_apis)),
                "external_and_backend_apis": sorted(list(self.external_apis)),
                "websocket_endpoints": sorted(list(self.websockets)),
                "graphql_queries_or_endpoints": sorted(list(self.graphql_endpoints))
            },
            "spa_screens_and_routes": sorted(list(self.spa_routes)),
            "discovered_subdomains": sorted(list(self.subdomains)),
            "detected_configs_and_keys": clean_keys
        }

    def generate_text_report(self) -> str:
        """Generates formatted, comprehensive text intel report."""
        report = []
        report.append("=" * 65)
        report.append(f"   A-TO-Z REVERSE-ENGINEERING & INTEL REPORT")
        report.append(f"   Target Domain : {self.domain}")
        report.append(f"   Target URL    : {self.base_url}")
        report.append("=" * 65)
        report.append("")

        report.append(f"--- [1] BACKEND APIS & ENDPOINTS ({len(self.relative_apis)} Found) ---")
        if self.relative_apis:
            for api in sorted(self.relative_apis):
                report.append(f"  • {api}")
        else:
            report.append("  (No relative endpoints identified)")
        report.append("")

        report.append(f"--- [2] HIDDEN SPA PAGES & CLIENT SCREENS ({len(self.spa_routes)} Found) ---")
        if self.spa_routes:
            for r in sorted(self.spa_routes):
                report.append(f"  • {r}")
        else:
            report.append("  (No internal SPA routes detected)")
        report.append("")

        report.append(f"--- [3] DISCOVERED SUBDOMAINS & SERVERS ({len(self.subdomains)} Found) ---")
        if self.subdomains:
            for s in sorted(self.subdomains):
                report.append(f"  • {s}")
        else:
            report.append("  (No internal subdomains detected)")
        report.append("")

        report.append("--- [4] WEBSOCKET REALTIME CHANNELS ---")
        if self.websockets:
            for ws in sorted(self.websockets):
                report.append(f"  • {ws}")
        else:
            report.append("  (No websocket endpoints detected)")
        report.append("")

        report.append("--- [5] EXTERNAL BACKEND SERVICES & APIS ---")
        if self.external_apis:
            for api in sorted(self.external_apis):
                report.append(f"  • {api}")
        else:
            report.append("  (No external API endpoints identified)")
        report.append("")

        report.append("--- [6] DETECTED CONFIGS, TOKENS & PUBLIC KEYS ---")
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
        report.append("   Owner: @owAtom | Channel: @OwAbyss")
        report.append("=" * 65)
        return "\n".join(report)
