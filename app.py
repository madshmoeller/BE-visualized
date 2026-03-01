"""
CRISPR Base Editing Library Viewer — Dash Application.

Run with: python app.py
Then open http://localhost:5002 in your browser.
"""

import dash
from dash import html, dcc, callback, Input, Output, State, no_update, ctx
import dash_molstar
from dash_molstar.utils import molstar_helper
from dash_molstar.utils.molstar_helper import Representation

from data_loader import load_all_data
from structure import check_structure, download_structure, get_structure_path
from components import (
    build_sequence_viewer,
    build_legend,
    build_search_results,
    build_protein_header,
)

# ---------------------------------------------------------------------------
# Load data at startup
# ---------------------------------------------------------------------------

search_index, protein_data, app_config = load_all_data()

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    title="CRISPR Library Viewer",
)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

app.layout = html.Div([
    dcc.Location(id="url", refresh=False),

    # Navbar
    html.Nav(
        html.A("CRISPR Library Viewer", href="/", className="nav-brand"),
        className="navbar",
    ),

    # Page content (swapped by routing callback)
    html.Div(id="page-content", className="container"),

    # Hidden stores for inter-component communication
    dcc.Store(id="current-protein"),
    dcc.Store(id="clicked-residue"),
    dcc.Store(id="structure-status"),
])


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

@callback(
    Output("page-content", "children"),
    Output("current-protein", "data"),
    Input("url", "pathname"),
)
def route(pathname):
    if pathname and pathname.startswith("/protein/"):
        uid = pathname.split("/protein/", 1)[1].split("/")[0]
        if uid in protein_data:
            return _build_protein_page(uid), uid
        return html.Div([
            html.P(f"Protein {uid} not found.", className="error-box"),
            html.A("Back to search", href="/", className="back-link"),
        ]), None
    return _build_search_page(), None


# =========================================================================
# Search Page
# =========================================================================

def _build_search_page():
    # Screen filter options
    screen_options = [{"label": "All Screens", "value": ""}]
    for screen in app_config["screens"]:
        screen_options.append({"label": screen, "value": screen})

    return html.Div([
        html.H1("CRISPR Base Editing Library Viewer"),
        html.P(
            "Search for a protein to view its target residues, guide designs, "
            "and AlphaFold 3D structure.",
            className="subtitle",
        ),

        # Screen filter
        html.Div([
            html.Label("Screen", htmlFor="screen-filter"),
            dcc.Dropdown(
                id="screen-filter",
                options=screen_options,
                value="",
                clearable=False,
                style={"width": "200px"},
            ),
        ], style={"display": "flex", "justifyContent": "center",
                   "alignItems": "center", "gap": "8px", "marginBottom": "20px"}),

        # Search input
        html.Div([
            html.Div([
                html.Label("Gene name or UniProt accession"),
                dcc.Input(
                    id="search-input",
                    type="text",
                    placeholder="e.g. CAD, SGK1, P27708...",
                    debounce=False,
                    style={"width": "100%", "padding": "12px 16px",
                           "border": "2px solid #ddd", "borderRadius": "8px",
                           "fontSize": "16px", "lineHeight": "1.4",
                           "height": "auto"},
                ),
            ], style={"width": "500px", "textAlign": "left"}),
        ], style={"display": "flex", "justifyContent": "center", "marginBottom": "16px"}),

        # Search results
        html.Div(id="search-results", style={"maxWidth": "700px", "margin": "0 auto"}),

    ], className="search-page")


@callback(
    Output("search-results", "children"),
    Input("search-input", "value"),
    Input("screen-filter", "value"),
)
def do_search(query, screen_filter):
    if not query or len(query.strip()) < 2:
        return []

    query = query.strip().lower()
    screen_filter = screen_filter or ""
    matches = []

    for entry in search_index:
        if screen_filter and screen_filter not in entry["screens"]:
            continue

        gene_lower = entry["gene_name"].lower()

        if gene_lower == query:
            priority = 0
        elif gene_lower.startswith(query) or any(
            a.lower().startswith(query) for a in entry["gene_aliases"]
        ):
            priority = 1
        elif entry["uniprot_id"].lower().startswith(query):
            priority = 2
        elif query in entry.get("protein_name", "").lower():
            priority = 3
        else:
            continue

        matches.append((priority, entry))

    matches.sort(key=lambda x: (x[0], not x[1]["has_guides"], x[1]["gene_name"].lower()))

    targeted = []
    not_targeted = []
    for _, entry in matches[:50]:
        item = {
            "uniprot_id": entry["uniprot_id"],
            "gene_name": entry["gene_name"],
            "screens": entry["screens"],
            "has_guides": entry["has_guides"],
            "n_targets": entry["n_targets"],
            "n_guides": entry["n_guides"],
        }
        if entry["has_guides"]:
            targeted.append(item)
        else:
            not_targeted.append(item)

    return build_search_results(targeted, not_targeted, app_config["screen_badges"])


# =========================================================================
# Protein Page
# =========================================================================

def _build_protein_page(uid):
    data = protein_data[uid]
    meta = data["meta"]
    sequence = data["sequence"]
    targets = data["targets"]
    guides = data["guides"]

    # Collect unique annotation types
    annotation_types = set()
    for t in targets:
        annotation_types.update(t["annotations"])

    return html.Div([
        html.A("\u2190 Back to search", href="/", className="back-link"),

        build_protein_header(meta),
        build_legend(annotation_types, app_config["source_colors"], app_config["guide_color"]),
        build_sequence_viewer(sequence, targets, guides, app_config),

        # 3D Structure section
        html.Div([
            html.H2("3D Structure (AlphaFold)", className="structure-heading"),
            html.Div(id="structure-status-text", className="structure-status",
                     children="Checking structure availability..."),
            html.Div(
                dash_molstar.MolstarViewer(
                    id="molstar-viewer",
                    style={"width": "100%", "height": "600px"},
                ),
                id="structure-container",
                style={"display": "none", "border": "1px solid #e0e0e0",
                       "borderRadius": "8px", "overflow": "hidden"},
            ),
        ], className="structure-section"),

    ], className="protein-page")


# =========================================================================
# Structure loading callbacks
# =========================================================================

@callback(
    Output("molstar-viewer", "data"),
    Output("structure-container", "style"),
    Output("structure-status-text", "children"),
    Input("current-protein", "data"),
    prevent_initial_call=True,
)
def load_structure(uniprot_id):
    if not uniprot_id:
        return no_update, no_update, no_update

    hidden = {"display": "none", "border": "1px solid #e0e0e0",
              "borderRadius": "8px", "overflow": "hidden"}
    visible = {"display": "block", "border": "1px solid #e0e0e0",
               "borderRadius": "8px", "overflow": "hidden"}

    # Check / download structure
    if not check_structure(uniprot_id):
        success, msg = download_structure(uniprot_id)
        if not success:
            return no_update, hidden, "No AlphaFold structure available for this protein."

    path = get_structure_path(uniprot_id)
    if not path:
        return no_update, hidden, "Structure file not found."

    # Collect target residues for this protein
    targets = protein_data.get(uniprot_id, {}).get("targets", [])
    residues = [t["resnum"] for t in targets if t["annotations"]]

    if residues:
        target_sel = molstar_helper.get_targets(chain="A", residue=residues)

        # Ball-and-stick sidechains: element coloring with pink carbons
        r_sticks = Representation(type="ball-and-stick", color="element-symbol")
        r_sticks.set_color_params({"carbonColor": Representation.np("custom", 0xFF1493)})
        comp_sticks = molstar_helper.create_component("Target Sidechains", target_sel, r_sticks)

        # Preset: color target residues pink in the default cartoon representation
        preset = {
            "kind": "standard",
            "colors": [{"targets": [target_sel], "value": 0xFF1493}],
        }

        mol_data = molstar_helper.parse_molecule(str(path), component=[comp_sticks], preset=preset)
    else:
        mol_data = molstar_helper.parse_molecule(str(path))

    return mol_data, visible, ""


# =========================================================================
# Bidirectional linking: Sequence -> Structure
# =========================================================================

# Clientside callback: capture click on a residue-char span,
# read its data-resnum, and store it
app.clientside_callback(
    """
    function(n_clicks) {
        // Use the last click event's target to find the residue
        var el = document.querySelector('.residue-char:hover');
        if (!el) {
            // Fallback: look for recently clicked element
            var all = document.querySelectorAll('.residue-char');
            // No reliable way to determine clicked element from n_clicks alone,
            // so we rely on the :hover pseudoclass above
            return window.dash_clientside.no_update;
        }
        var resnum = parseInt(el.getAttribute('data-resnum'));
        if (isNaN(resnum)) return window.dash_clientside.no_update;
        return resnum;
    }
    """,
    Output("clicked-residue", "data"),
    Input("sequence-viewer", "n_clicks"),
    prevent_initial_call=True,
)


@callback(
    Output("molstar-viewer", "selection"),
    Output("molstar-viewer", "focus"),
    Input("clicked-residue", "data"),
    prevent_initial_call=True,
)
def select_clicked_residue(resnum):
    if resnum is None:
        return no_update, no_update
    target = molstar_helper.get_targets(chain="A", residue=[resnum])
    selection = molstar_helper.get_selection(target, add=False)
    focus = molstar_helper.get_focus(target, analyse=False)
    return selection, focus


# =========================================================================
# Entry point
# =========================================================================

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=False)
