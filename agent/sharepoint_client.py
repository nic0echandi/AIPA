"""
sharepoint_client.py — Cliente Graph API para descargar archivos .txt desde SharePoint
Autenticación via Client Credentials (Azure App Registration)
"""

import os
import time
import logging
import requests
from pathlib import Path
from typing import List, Optional, Dict

log = logging.getLogger("phishing_analyzer.sharepoint")


class SharePointClient:
    """
    Descarga archivos .txt desde una biblioteca de SharePoint usando Microsoft Graph API.
    Requiere un Azure App Registration con permisos:
      - Sites.Read.All (o Sites.ReadWrite.All si se quiere mover/eliminar)
      - Files.Read.All
    """

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    TOKEN_URL  = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    def __init__(self, config: Dict):
        self.tenant_id     = config["azure"]["tenant_id"]
        self.client_id     = config["azure"]["client_id"]
        self.client_secret = config["azure"]["client_secret"]
        self.site_id       = config["sharepoint"]["site_id"]
        self.drive_id      = config["sharepoint"].get("drive_id", "")
        self.folder_path   = config["sharepoint"].get("folder_path", "/phishing-reports")
        self.ingress_dir   = Path(config.get("ingress_dir", "ingress"))

        self._token: Optional[str]    = None
        self._token_expiry: float     = 0.0

        self.ingress_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Obtiene (o renueva) el access token via client_credentials."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        url  = self.TOKEN_URL.format(tenant_id=self.tenant_id)
        data = {
            "grant_type":    "client_credentials",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "scope":         "https://graph.microsoft.com/.default",
        }

        resp = requests.post(url, data=data, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        self._token        = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600))
        log.debug("Token Graph API renovado (expira en %ds)", payload.get("expires_in", 3600))
        return self._token

    def _headers(self) -> Dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    # ------------------------------------------------------------------
    # Listado de archivos
    # ------------------------------------------------------------------

    def _drive_root(self) -> str:
        """Construye la URL base del drive."""
        if self.drive_id:
            return f"{self.GRAPH_BASE}/drives/{self.drive_id}"
        return f"{self.GRAPH_BASE}/sites/{self.site_id}/drive"

    def list_txt_files(self) -> List[Dict]:
        """
        Lista archivos .txt dentro de la carpeta configurada en SharePoint.
        Retorna lista de dicts con 'id', 'name', 'size', 'lastModifiedDateTime'.
        """
        folder = self.folder_path.lstrip("/")
        url    = f"{self._drive_root()}/root:/{folder}:/children"
        params = {"$select": "id,name,size,lastModifiedDateTime,file"}

        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            items = resp.json().get("value", [])
            txt_files = [
                item for item in items
                if item.get("name", "").lower().endswith(".txt") and "file" in item
            ]
            log.debug("SharePoint: %d archivos .txt encontrados en '%s'", len(txt_files), self.folder_path)
            return txt_files
        except requests.HTTPError as exc:
            log.error("Error listando SharePoint (%s): %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            log.error("Error inesperado listando SharePoint: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Descarga
    # ------------------------------------------------------------------

    def download_file(self, item: Dict) -> Optional[Path]:
        """
        Descarga un archivo individual a la carpeta ingress/.
        Retorna el Path local del archivo descargado, o None si falla.
        """
        file_id   = item["id"]
        file_name = item["name"]
        dest_path = self.ingress_dir / file_name

        # Evitar re-descargar si ya existe (el watcher lo procesará)
        if dest_path.exists():
            log.debug("Ya existe localmente, omitiendo: %s", file_name)
            return None

        url = f"{self._drive_root()}/items/{file_id}/content"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=60, stream=True)
            resp.raise_for_status()

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            log.info("Descargado: %s → %s", file_name, dest_path)
            return dest_path

        except requests.HTTPError as exc:
            log.error("Error descargando '%s' (%s): %s", file_name, exc.response.status_code, exc)
        except Exception as exc:
            log.error("Error inesperado descargando '%s': %s", file_name, exc)

        return None

    def poll_and_download(self) -> List[Path]:
        """
        Ejecuta un ciclo completo: listar → descargar nuevos.
        Retorna lista de archivos recién descargados.
        """
        items     = self.list_txt_files()
        downloaded = []
        for item in items:
            path = self.download_file(item)
            if path:
                downloaded.append(path)
        if downloaded:
            log.info("SharePoint poll: %d archivo(s) nuevo(s) descargados", len(downloaded))
        return downloaded
