"""
AlphaFold structure download and cache management.
"""

from pathlib import Path
import requests

STRUCTURES_DIR = Path(__file__).parent / "structures"
STRUCTURES_DIR.mkdir(exist_ok=True)
ALPHAFOLD_API = "https://alphafold.ebi.ac.uk/api/prediction/{}"


def check_structure(uniprot_id: str) -> bool:
    """Check if an AlphaFold CIF file is cached locally."""
    matches = list(STRUCTURES_DIR.glob(f"AF-{uniprot_id}-F1-model_v*.cif"))
    return len(matches) > 0


def download_structure(uniprot_id: str) -> tuple:
    """Download AlphaFold structure from EBI API. Returns (success, message)."""
    if check_structure(uniprot_id):
        return True, "Already downloaded"

    try:
        api_resp = requests.get(ALPHAFOLD_API.format(uniprot_id), timeout=15)
        if api_resp.status_code != 200:
            return False, "No AlphaFold prediction available"

        prediction = api_resp.json()[0]
        cif_url = prediction.get("cifUrl")
        if not cif_url:
            return False, "No CIF URL in AlphaFold response"

        cif_resp = requests.get(cif_url, timeout=60)
        if cif_resp.status_code == 200:
            filename = cif_url.split("/")[-1]
            cif_path = STRUCTURES_DIR / filename
            cif_path.write_bytes(cif_resp.content)
            return True, "Downloaded"
        else:
            return False, f"Download failed (HTTP {cif_resp.status_code})"

    except requests.RequestException as e:
        return False, str(e)


def get_structure_path(uniprot_id: str):
    """Return path to cached CIF file, or None."""
    matches = list(STRUCTURES_DIR.glob(f"AF-{uniprot_id}-F1-model_v*.cif"))
    if not matches:
        return None
    return sorted(matches)[-1]
