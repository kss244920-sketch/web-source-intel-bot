import io
import json
import zipfile
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

from core.extractor import IntelExtractor


class ZipPackager:
    """Creates structured ZIP archives and specific category exports."""

    @staticmethod
    def build_zip(
        domain: str,
        files_map: Dict[str, bytes],
        intel: IntelExtractor,
        category: str = "all"
    ) -> Tuple[io.BytesIO, str, Dict[str, Any]]:
        """
        Packs website source code, assets, and INTEL_REPORT.
        Categories supported: 'all', 'js', 'css', 'images'
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
            elif category == "js" and ("assets/js" in rel_path or rel_path == "index.html"):
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

            # Always include INTEL_REPORT in full and JS packages
            if category in ["all", "js"]:
                text_report = intel.generate_text_report()
                zf.writestr("INTEL_REPORT/all_apis_and_secrets.txt", text_report.encode("utf-8"))
                json_report = json.dumps(intel.get_summary_report(), indent=2)
                zf.writestr("INTEL_REPORT/intel_summary.json", json_report.encode("utf-8"))

        zip_buffer.seek(0)
        zip_bytes_len = len(zip_buffer.getvalue())
        size_mb = round(zip_bytes_len / (1024 * 1024), 2)
        size_str = f"{size_mb} MB" if size_mb >= 0.01 else f"{round(zip_bytes_len / 1024, 1)} KB"

        summary = intel.get_summary_report()
        stats = {
            "zip_filename": zip_filename,
            "total_files": len(filtered_files),
            "size_str": size_str,
            "size_bytes": zip_bytes_len,
            "relative_apis_count": summary["statistics"]["total_relative_apis"],
            "external_apis_count": summary["statistics"]["total_external_apis"],
            "total_apis": summary["statistics"]["total_relative_apis"] + summary["statistics"]["total_external_apis"],
            "websockets_count": summary["statistics"]["total_websockets"],
            "keys_count": summary["statistics"].get("total_secrets_detected", 0),
            "title": intel.metadata.get("title", domain)
        }

        return zip_buffer, zip_filename, stats
