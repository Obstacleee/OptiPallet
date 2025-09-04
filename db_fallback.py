# Fichier: db_fallback.py
import json
import os

FALLBACK_DIR = "json_fallback"

def _get_filename(dims):
    """Crée un nom de fichier unique pour une configuration de dimensions."""
    p = dims['pallet_dims']
    b = dims['box_dims']
    return f"{FALLBACK_DIR}/fallback_{p['L']}x{p['W']}_{b['l']}x{b['w']}.json"

def save_templates(dims, templates_data):
    """Sauvegarde les templates dans un fichier JSON de secours."""
    if not os.path.exists(FALLBACK_DIR):
        os.makedirs(FALLBACK_DIR)
    filename = _get_filename(dims)
    with open(filename, 'w') as f:
        json.dump(templates_data, f, indent=4)
    print(f"DB FALLBACK: Sauvegarde dans {filename}")

def load_templates(dims):
    """Charge les templates depuis un fichier JSON de secours."""
    filename = _get_filename(dims)
    if os.path.exists(filename):
        print(f"DB FALLBACK: Chargement depuis {filename}")
        with open(filename, 'r') as f:
            return json.load(f)
    return None