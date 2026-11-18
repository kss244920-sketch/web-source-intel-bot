import io
import json
import zipfile
from datetime import datetime
from typing import Dict, Any, Tuple

from core.extractor import IntelExtractor


class ZipPackager:
    """Creates a structured, in-memory ZIP archive containing the website and intel reports."""

    @staticmethod
    def build_zip(
        domain: str,
        files_map: Dict[str, bytes],
        intel: IntelExtractor
    ) -> Tuple[io.BytesIO, str, Dict[str, Any]]:
        """
        Packs website source code, assets, and INTEL_REPORT into an in-memory ZIP.
        Returns:
            - zip_buffer: io.BytesIO
            - zip_filename: str
            - stats: dict containing size, file counts, and findings
        """
        zip_buffer = io.BytesIO()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_domain = domain.replace(":", "_").replace("/", "_")
        zip_filename = f"website_{safe_domain}_{timestamp}.zip"

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Write all website source files and assets
            for rel_path, data in files_map.items():
                zf.writestr(rel_path, data)

            # 2. Generate and write INTEL_REPORT
            text_report = intel.generate_text_report()
            zf.writestr("INTEL_REPORT/all_apis_and_secrets.txt", text_report.encode("utf-8"))

            json_report = json.dumps(intel.get_summary_report(), indent=2)
            zf.writestr("INTEL_REPORT/intel_summary.json", json_report.encode("utf-8"))

            readme = (
                f"Website Source Archive for: {intel.base_url}\n"
                f"Generated at: {datetime.now().isoformat()}\n\n"
                f"Contents:\n"
                f"- index.html : Cleaned and offline-ready website frontpage.\n"
                f"- assets/ : All downloaded CSS, JS, images, and fonts.\n"
                f"- INTEL_REPORT/ : A-to-Z list of discovered API endpoints, websockets, and public keys.\n"
            )
            zf.writestr("README.txt", readme.encode("utf-8"))

        zip_buffer.seek(0)
        zip_bytes_len = len(zip_buffer.getvalue())
        size_mb = round(zip_bytes_len / (1024 * 1024), 2)
        size_str = f"{size_mb} MB" if size_mb >= 0.01 else f"{round(zip_bytes_len / 1024, 1)} KB"

        summary = intel.get_summary_report()
        stats = {
            "zip_filename": zip_filename,
            "total_files": len(files_map),
            "size_str": size_str,
            "size_bytes": zip_bytes_len,
            "relative_apis_count": summary["statistics"]["total_relative_apis"],
            "external_apis_count": summary["statistics"]["total_external_apis"],
            "total_apis": summary["statistics"]["total_relative_apis"] + summary["statistics"]["total_external_apis"],
            "websockets_count": summary["statistics"]["total_websockets"],
            "keys_count": summary["statistics"]["total_keys_found"],
            "title": intel.metadata.get("title", domain)
        }

        return zip_buffer, zip_filename, stats
