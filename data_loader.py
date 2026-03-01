"""
Data loader for Dash Library Viewer.
Reads standardized TSV files (targets, guides, proteins) and optional colors.json.
"""

import json
import pandas as pd
from pathlib import Path

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"

# Auto-assign palette for sources/screens not in colors.json
DEFAULT_PALETTE = [
    "#E74C3C", "#3498DB", "#1ABC9C", "#E67E22", "#F1C40F",
    "#9B59B6", "#27AE60", "#E91E63", "#00BCD4", "#FF9800",
    "#795548", "#607D8B", "#8BC34A", "#CDDC39",
]

# Screen badge colors: light background + dark text
SCREEN_BADGE_DEFAULTS = [
    {"bg": "#fde8e8", "fg": "#c62828"},
    {"bg": "#e8f0fd", "fg": "#1565c0"},
    {"bg": "#e8fde8", "fg": "#2e7d32"},
    {"bg": "#fff3e0", "fg": "#e65100"},
    {"bg": "#f3e5f5", "fg": "#6a1b9a"},
    {"bg": "#e0f7fa", "fg": "#00695c"},
]


def load_all_data():
    """Load and preprocess all data. Returns (search_index, protein_data, config)."""
    print("Loading data files...")

    # --- Load standard format files ---
    targets_df = pd.read_csv(DATA_DIR / "targets.tsv", sep="\t", dtype={"resnum": int})
    targets_df["sources"] = targets_df["sources"].fillna("")
    targets_df["role"] = targets_df["role"].fillna("")
    targets_df["resname"] = targets_df["resname"].fillna("")
    print(f"  Loaded {len(targets_df)} target residues")

    guides_df = pd.read_csv(DATA_DIR / "guides.tsv", sep="\t")
    guides_df["mutations"] = guides_df["mutations"].fillna("")
    guides_df["guide_seq"] = guides_df["guide_seq"].fillna("")
    print(f"  Loaded {len(guides_df)} guides")

    proteins_df = pd.read_csv(DATA_DIR / "proteins.tsv", sep="\t")
    proteins_df = proteins_df.fillna("")
    print(f"  Loaded {len(proteins_df)} proteins")

    # --- Load colors (optional) ---
    colors = _load_colors()

    # --- Auto-detect screens and sources ---
    screens = sorted(targets_df["screen"].unique())
    all_sources = set()
    for sources_str in targets_df["sources"]:
        if sources_str:
            all_sources.update(sources_str.split("|"))
    all_sources = sorted(all_sources)

    # Assign colors to sources
    source_colors = {}
    palette_idx = 0
    for source in all_sources:
        if source in colors.get("sources", {}):
            source_colors[source] = colors["sources"][source]
        else:
            source_colors[source] = DEFAULT_PALETTE[palette_idx % len(DEFAULT_PALETTE)]
            palette_idx += 1

    # Assign badge styles to screens
    screen_badges = {}
    for i, screen in enumerate(screens):
        if screen in colors.get("screens", {}):
            c = colors["screens"][screen]
            screen_badges[screen] = {"bg": c + "20", "fg": c}
        else:
            badge = SCREEN_BADGE_DEFAULTS[i % len(SCREEN_BADGE_DEFAULTS)]
            screen_badges[screen] = badge

    guide_color = colors.get("guides", "#6366F1")
    structure_colors = colors.get("structure", {
        "target_3d": "#FF1493",
        "selection_3d": "#39FF14",
    })

    # --- Build protein lookup ---
    protein_meta = {}
    for _, row in proteins_df.iterrows():
        uid = row["uniprot_id"]
        protein_meta[uid] = {
            "gene_name": row["gene_name"],
            "gene_aliases": row["gene_aliases"],
            "protein_name": row["protein_name"],
            "ec_number": row["ec_number"],
            "length": int(row["length"]) if row["length"] else 0,
            "sequence": row["sequence"],
        }

    # --- Build protein_targets: uniprot_id -> [residue dicts] ---
    protein_targets = {}
    for _, row in targets_df.iterrows():
        uid = row["uniprot_id"]
        annotations = [s for s in row["sources"].split("|") if s] if row["sources"] else []
        if uid not in protein_targets:
            protein_targets[uid] = []
        protein_targets[uid].append({
            "resnum": int(row["resnum"]),
            "resname": row["resname"],
            "annotations": annotations,
            "role": row["role"],
        })

    # --- Build protein_guides: uniprot_id -> [guide dicts] ---
    protein_guides = {}
    guided_accessions = set()
    for _, row in guides_df.iterrows():
        uid = row["uniprot_id"]
        guided_accessions.add(uid)
        if uid not in protein_guides:
            protein_guides[uid] = []
        protein_guides[uid].append({
            "start": int(row["start"]),
            "end": int(row["end"]),
            "dual_mutations": row["mutations"],
            "guide_seq": row["guide_seq"],
        })

    # --- Build protein_screens: uniprot_id -> list of screen names ---
    protein_screens = {}
    for _, row in targets_df.drop_duplicates(["uniprot_id", "screen"]).iterrows():
        uid = row["uniprot_id"]
        if uid not in protein_screens:
            protein_screens[uid] = []
        protein_screens[uid].append(row["screen"])
    for _, row in guides_df.drop_duplicates(["uniprot_id", "screen"]).iterrows():
        uid = row["uniprot_id"]
        if uid not in protein_screens:
            protein_screens[uid] = []
        if row["screen"] not in protein_screens[uid]:
            protein_screens[uid].append(row["screen"])

    # --- Build search index ---
    search_index = []
    all_uids = set(protein_targets.keys()) | set(protein_guides.keys())

    for uid in all_uids:
        meta = protein_meta.get(uid, {})
        gene_name = meta.get("gene_name", "")
        gene_aliases_str = meta.get("gene_aliases", "")
        aliases = [a.strip() for a in gene_aliases_str.split() if a.strip()] if gene_aliases_str else []
        if not gene_name and aliases:
            gene_name = aliases[0]

        search_index.append({
            "uniprot_id": uid,
            "gene_name": gene_name,
            "gene_aliases": aliases,
            "protein_name": meta.get("protein_name", ""),
            "ec_number": meta.get("ec_number", ""),
            "screens": sorted(protein_screens.get(uid, [])),
            "has_guides": uid in guided_accessions,
            "n_targets": len(protein_targets.get(uid, [])),
            "n_guides": len(protein_guides.get(uid, [])),
        })

    search_index.sort(key=lambda x: (not x["has_guides"], x["gene_name"].lower()))
    print(f"  Built search index with {len(search_index)} proteins")

    # --- Combine into protein_data ---
    protein_data = {}
    for uid in all_uids:
        meta = protein_meta.get(uid, {})
        gene_name = meta.get("gene_name", "")
        if not gene_name:
            aliases_str = meta.get("gene_aliases", "")
            if aliases_str:
                gene_name = aliases_str.split()[0]

        protein_data[uid] = {
            "meta": {
                "uniprot_id": uid,
                "gene_name": gene_name,
                "protein_name": meta.get("protein_name", ""),
                "ec_number": meta.get("ec_number", ""),
                "length": meta.get("length", 0),
                "screens": sorted(protein_screens.get(uid, [])),
                "n_targets": len(protein_targets.get(uid, [])),
                "n_guides": len(protein_guides.get(uid, [])),
            },
            "sequence": meta.get("sequence", ""),
            "targets": protein_targets.get(uid, []),
            "guides": protein_guides.get(uid, []),
        }

    # --- Build config for frontend ---
    config = {
        "screens": screens,
        "source_colors": source_colors,
        "screen_badges": screen_badges,
        "guide_color": guide_color,
        "structure": structure_colors,
    }

    print(f"Data loading complete. {len(protein_data)} proteins available.\n")
    return search_index, protein_data, config


def _load_colors():
    """Load optional colors.json, return empty dict if not found."""
    colors_path = DATA_DIR / "colors.json"
    if colors_path.exists():
        with open(colors_path) as f:
            return json.load(f)
    return {}
