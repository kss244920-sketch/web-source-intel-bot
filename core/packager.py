import io
import json
import zipfile
from datetime import datetime
from typing import Dict, Any, Tuple

from core.extractor import IntelExtractor


class ZipPackager:
    """Creates structured ZIP archives, auto-generated API clients, and AI prompts."""

    @staticmethod
    def build_zip(
        domain: str,
        files_map: Dict[str, bytes],
        intel: IntelExtractor,
        category: str = "all"
    ) -> Tuple[io.BytesIO, str, Dict[str, Any]]:
        """
        Packs website source code, assets, INTEL_REPORT, api_client.py, and AI_CLONE_PROMPT.md.
        """
        zip_buffer = io.BytesIO()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_domain = domain.replace(":", "_").replace("/", "_")

        category_labels = {
            "all": "full",
            "js": "scripts",
            "css": "styles",
            "images": "images"
        }
        suffix = category_labels.get(category, "package")
        zip_filename = f"website_{safe_domain}_{suffix}_{timestamp}.zip"

        # Filter files if a specific category is requested
        filtered_files: Dict[str, bytes] = {}
        for rel_path, data in files_map.items():
            if category == "all":
                filtered_files[rel_path] = data
            elif category == "js" and ("assets/js" in rel_path or rel_path == "index.html" or "original_src" in rel_path):
                filtered_files[rel_path] = data
            elif category == "css" and ("assets/css" in rel_path or rel_path == "index.html"):
                filtered_files[rel_path] = data
            elif category == "images" and "assets/images" in rel_path:
                filtered_files[rel_path] = data

        if not filtered_files:
            filtered_files = files_map

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path, data in filtered_files.items():
                zf.writestr(rel_path, data)

            # 1. Add Auto-Generated Python API Client (Reverse-API-Engineer style)
            api_client_code = intel.generate_api_client_py()
            zf.writestr("api_client.py", api_client_code.encode("utf-8"))

            # 2. Add AI Recreate Prompt Blueprint (gitreverse style)
            ai_prompt = intel.generate_ai_clone_prompt()
            zf.writestr("AI_CLONE_PROMPT.md", ai_prompt.encode("utf-8"))

            # 3. Add Comprehensive INTEL_REPORT
            text_report = intel.generate_text_report()
            zf.writestr("INTEL_REPORT/all_apis_and_secrets.txt", text_report.encode("utf-8"))
            json_report = json.dumps(intel.get_summary_report(), indent=2)
            zf.writestr("INTEL_REPORT/intel_summary.json", json_report.encode("utf-8"))

            # 4. Add Project Readme
            readme = (
                f"==========================================================\n"
                f"🚀 WebSource & Intel Reverse-Engineering Package\n"
                f"Target URL: {intel.base_url}\n"
                f"Generated at: {datetime.now().isoformat()}\n"
                f"==========================================================\n\n"
                f"Contents:\n"
                f"- index.html          : Cleaned offline-ready web frontpage\n"
                f"- assets/             : Downloaded CSS, formatted JS, images, fonts\n"
                f"- original_src/       : Unpacked SourceMaps (unminified code) if available\n"
                f"- api_client.py       : Ready-to-use Python API client script\n"
                f"- AI_CLONE_PROMPT.md  : AI prompt to recreate this app in Cursor/ChatGPT\n"
                f"- INTEL_REPORT/       : Complete routes, secrets, and subdomains report\n"
            )
            zf.writestr("README.txt", readme.encode("utf-8"))

        zip_buffer.seek(0)
        zip_bytes_len = len(zip_buffer.getvalue())
        size_mb = round(zip_bytes_len / (1024 * 1024), 2)
        size_str = f"{size_mb} MB" if size_mb >= 0.01 else f"{round(zip_bytes_len / 1024, 1)} KB"

        summary = intel.get_summary_report()
        stats = {
            "zip_filename": zip_filename,
            "total_files": len(filtered_files) + 4,
            "size_str": size_str,
            "size_bytes": zip_bytes_len,
            "relative_apis_count": summary["statistics"]["total_relative_apis"],
            "external_apis_count": summary["statistics"]["total_external_apis"],
            "total_apis": summary["statistics"]["total_relative_apis"] + summary["statistics"]["total_external_apis"],
            "spa_routes_count": summary["statistics"]["total_spa_routes"],
            "subdomains_count": summary["statistics"]["total_subdomains"],
            "sourcemaps_unpacked": summary["statistics"]["sourcemaps_unpacked"],
            "websockets_count": summary["statistics"]["total_websockets"],
            "keys_count": summary["statistics"].get("total_secrets_detected", 0),
            "title": intel.metadata.get("title", domain)
        }

        return zip_buffer, zip_filename, stats
