"""
UI component builders for the Dash Library Viewer.
Pure functions that return Dash component trees — no callbacks.
"""

import math
from dash import html
import dash_svg as svg

# Layout constants (must match style.css)
RESIDUES_PER_ROW = 60
CELL_WIDTH = 14       # px per residue
GROUP_GAP = 7         # extra px every 10 residues
LEFT_OFFSET = 55      # px for residue number label
ANNOTATION_RADIUS = 9
ANNOTATION_TRACK_HEIGHT = 24
GUIDE_LINE_HEIGHT = 6
GUIDE_LANE_GAP = 2

# Fallback palette for unknown sources
FALLBACK_PALETTE = [
    "#E74C3C", "#3498DB", "#1ABC9C", "#E67E22", "#F1C40F",
    "#9B59B6", "#27AE60", "#E91E63",
]


# =========================================================================
# Coordinate helpers
# =========================================================================

def _residue_to_x_local(idx):
    """Convert a 0-based index within a row to a pixel X position."""
    groups = idx // 10
    return LEFT_OFFSET + idx * CELL_WIDTH + groups * GROUP_GAP + CELL_WIDTH // 2


def _residue_to_x(resnum, row_start):
    """Convert an absolute residue number to pixel X within a row."""
    idx = resnum - row_start
    groups = idx // 10
    return LEFT_OFFSET + idx * CELL_WIDTH + groups * GROUP_GAP


def _get_color(source, source_colors):
    """Get color for an annotation source from config or fallback."""
    if source in source_colors:
        return source_colors[source]
    h = 0
    for c in source:
        h = ((h << 5) - h + ord(c)) & 0xFFFFFFFF
    return FALLBACK_PALETTE[h % len(FALLBACK_PALETTE)]


# =========================================================================
# SVG annotation circles (pizza-slice)
# =========================================================================

def _pizza_slice_path(cx, cy, r, start_angle, end_angle):
    """Generate an SVG path for a pizza slice (arc segment)."""
    x1 = cx + r * math.cos(start_angle)
    y1 = cy + r * math.sin(start_angle)
    x2 = cx + r * math.cos(end_angle)
    y2 = cy + r * math.sin(end_angle)
    large_arc = 1 if (end_angle - start_angle > math.pi) else 0
    return f"M {cx} {cy} L {x1:.2f} {y1:.2f} A {r} {r} 0 {large_arc} 1 {x2:.2f} {y2:.2f} Z"


def _build_annotation_circle(cx, cy, annotations, source_colors, resname, resnum, role, radius=9):
    """Build a pizza-slice SVG group for one annotated residue."""
    n = len(annotations)
    children = []

    if n == 1:
        color = _get_color(annotations[0], source_colors)
        children.append(svg.Circle(
            cx=cx, cy=cy, r=radius, fill=color,
            stroke="#fff", strokeWidth="1",
        ))
    else:
        slice_angle = (2 * math.pi) / n
        for i, ann in enumerate(annotations):
            start = i * slice_angle - math.pi / 2
            end = start + slice_angle
            color = _get_color(ann, source_colors)
            children.append(svg.Path(
                d=_pizza_slice_path(cx, cy, radius, start, end),
                fill=color, stroke="#fff", strokeWidth="0.5",
            ))

    # White residue letter on top
    children.append(svg.Text(
        resname, x=cx, y=cy + 3.5, textAnchor="middle",
        fill="white", fontSize="10px", fontWeight="bold",
        fontFamily="monospace", pointerEvents="none",
    ))

    return svg.G(children=children, style={"cursor": "pointer"})


# =========================================================================
# Annotation track (one per sequence row)
# =========================================================================

def _build_annotation_track(row_start, row_end, target_map, source_colors):
    """Build the annotation SVG track for one sequence row."""
    num_residues = row_end - row_start + 1
    num_groups = (num_residues - 1) // 10
    total_width = LEFT_OFFSET + num_residues * CELL_WIDTH + num_groups * GROUP_GAP

    cy = ANNOTATION_TRACK_HEIGHT / 2
    children = []

    for i in range(num_residues):
        resnum = row_start + i
        target = target_map.get(resnum)
        if not target or not target["annotations"]:
            continue
        cx = _residue_to_x_local(i)
        children.append(_build_annotation_circle(
            cx, cy, target["annotations"], source_colors,
            target["resname"], target["resnum"], target["role"],
            ANNOTATION_RADIUS,
        ))

    return svg.Svg(
        children=children,
        className="annotation-track",
        width=total_width,
        height=ANNOTATION_TRACK_HEIGHT,
    )


# =========================================================================
# Residue row
# =========================================================================

def _build_residue_row(row_start, row_end, sequence, target_map):
    """Build the residue letter row as html.Span elements."""
    children = []

    # Residue number label
    children.append(html.Span(
        str(row_start).rjust(5),
        className="resnum-label",
    ))

    row_seq = sequence[row_start - 1 : row_end]
    for i, char in enumerate(row_seq):
        # Group spacer every 10 residues
        if i > 0 and i % 10 == 0:
            children.append(html.Span(className="group-spacer"))

        resnum = row_start + i
        target = target_map.get(resnum)
        classes = "residue-char"
        if target and target["annotations"]:
            classes += " residue-targeted"

        children.append(html.Span(
            char,
            className=classes,
            **{"data-resnum": str(resnum)},
        ))

    return html.Div(children, className="residue-row")


# =========================================================================
# Guide track (lane assignment + SVG bars)
# =========================================================================

def _assign_guide_lanes(guides, row_start, row_end):
    """Assign vertical lanes to guides to avoid overlap. Returns (lane_guides, n_lanes)."""
    relevant = []
    for g in guides:
        if g["end"] >= row_start and g["start"] <= row_end:
            relevant.append({
                **g,
                "clipped_start": max(g["start"], row_start),
                "clipped_end": min(g["end"], row_end),
            })

    relevant.sort(key=lambda g: g["clipped_start"])

    lane_ends = []
    for g in relevant:
        assigned = False
        for i in range(len(lane_ends)):
            if lane_ends[i] < g["clipped_start"]:
                lane_ends[i] = g["clipped_end"]
                g["lane"] = i
                assigned = True
                break
        if not assigned:
            g["lane"] = len(lane_ends)
            lane_ends.append(g["clipped_end"])

    return relevant, len(lane_ends)


def _build_guide_track(row_start, row_end, guides, config):
    """Build the guide track SVG for one sequence row."""
    lane_guides, n_lanes = _assign_guide_lanes(guides, row_start, row_end)
    if n_lanes == 0:
        return html.Div()  # empty placeholder

    guide_color = config.get("guide_color", "#6366F1")
    svg_height = n_lanes * (GUIDE_LINE_HEIGHT + GUIDE_LANE_GAP) + 2
    num_residues = row_end - row_start + 1
    num_groups = (num_residues - 1) // 10
    total_width = LEFT_OFFSET + num_residues * CELL_WIDTH + num_groups * GROUP_GAP

    CONTINUATION_WIDTH = 8   # px length of the thin continuation line
    CONTINUATION_HEIGHT = 2  # px height (thinner than the main bar)

    children = []
    for g in lane_guides:
        x1 = _residue_to_x(g["clipped_start"], row_start)
        x2 = _residue_to_x(g["clipped_end"], row_start) + CELL_WIDTH
        y = g["lane"] * (GUIDE_LINE_HEIGHT + GUIDE_LANE_GAP) + 1

        children.append(svg.Rect(
            x=x1, y=y,
            width=max(x2 - x1, 4),
            height=GUIDE_LINE_HEIGHT,
            rx=2,
            fill=guide_color,
            opacity="0.7",
        ))

        # Thin continuation indicator: guide continues from previous row
        cont_y = y + (GUIDE_LINE_HEIGHT - CONTINUATION_HEIGHT) / 2
        if g["start"] < row_start:
            children.append(svg.Rect(
                x=x1 - CONTINUATION_WIDTH, y=cont_y,
                width=CONTINUATION_WIDTH,
                height=CONTINUATION_HEIGHT,
                rx=1,
                fill=guide_color,
                opacity="0.5",
            ))

        # Thin continuation indicator: guide continues to next row
        if g["end"] > row_end:
            children.append(svg.Rect(
                x=x2, y=cont_y,
                width=CONTINUATION_WIDTH,
                height=CONTINUATION_HEIGHT,
                rx=1,
                fill=guide_color,
                opacity="0.5",
            ))

    return svg.Svg(
        children=children,
        className="guide-track",
        width=total_width,
        height=svg_height,
    )


# =========================================================================
# Full sequence viewer
# =========================================================================

def build_sequence_viewer(sequence, targets, guides, config):
    """Build the complete sequence viewer with annotation and guide tracks."""
    if not sequence:
        return html.Div(
            html.P("Sequence not available for this protein.", className="no-sequence"),
            id="sequence-viewer",
            className="sequence-viewer",
        )

    # Build target lookup: resnum -> target data
    target_map = {t["resnum"]: t for t in targets}
    source_colors = config.get("source_colors", {})

    total_rows = math.ceil(len(sequence) / RESIDUES_PER_ROW)
    rows = []

    for row_idx in range(total_rows):
        row_start = row_idx * RESIDUES_PER_ROW + 1
        row_end = min((row_idx + 1) * RESIDUES_PER_ROW, len(sequence))

        ann_svg = _build_annotation_track(row_start, row_end, target_map, source_colors)
        residue_div = _build_residue_row(row_start, row_end, sequence, target_map)
        guide_svg = _build_guide_track(row_start, row_end, guides, config)

        rows.append(html.Div([ann_svg, residue_div, guide_svg], className="seq-row"))

    return html.Div(rows, id="sequence-viewer", className="sequence-viewer")


# =========================================================================
# Annotation legend
# =========================================================================

def build_legend(annotation_types, source_colors, guide_color):
    """Build the annotation legend with colored swatches."""
    if not annotation_types:
        return html.Div(id="annotation-legend", className="annotation-legend")

    children = [html.Strong("Annotation sources: ")]

    for ann_type in sorted(annotation_types):
        color = _get_color(ann_type, source_colors)
        children.append(html.Span([
            html.Span(className="legend-swatch", style={"background": color}),
            ann_type,
        ], className="legend-item"))

    # Guide legend item
    children.append(html.Span([
        html.Span(
            className="legend-swatch legend-swatch-guide",
            style={"background": guide_color},
        ),
        "Guide RNA",
    ], className="legend-item"))

    return html.Div(children, id="annotation-legend", className="annotation-legend")


# =========================================================================
# Search results
# =========================================================================

def build_search_results(targeted, not_targeted, screen_badges):
    """Build the search results list."""
    children = []

    if targeted:
        children.append(html.Div(
            f"Targeted (in library) — {len(targeted)} results",
            className="dropdown-header",
        ))
        for item in targeted:
            children.append(_build_result_item(item, screen_badges))

    if not_targeted:
        children.append(html.Div(
            f"Not targeted (annotations only) — {len(not_targeted)} results",
            className="dropdown-header",
        ))
        for item in not_targeted:
            children.append(_build_result_item(item, screen_badges))

    if not targeted and not not_targeted:
        children.append(html.Div("No results found", className="dropdown-empty"))

    return children


def _build_result_item(item, screen_badges):
    """Build a single search result row."""
    badges = []
    for screen in item.get("screens", []):
        badge_style = screen_badges.get(screen, {"bg": "#eee", "fg": "#333"})
        badges.append(html.Span(
            screen,
            className="badge",
            style={"background": badge_style["bg"], "color": badge_style["fg"]},
        ))

    counts = []
    if item["n_targets"]:
        counts.append(f"{item['n_targets']} targets")
    if item["n_guides"]:
        counts.append(f"{item['n_guides']} guides")

    return html.A(
        html.Div([
            html.Span(item["gene_name"] or "—", className="result-gene"),
            html.Span(item["uniprot_id"], className="result-acc"),
            *badges,
            html.Span(", ".join(counts), className="result-counts"),
        ], className="dropdown-item"),
        href=f"/protein/{item['uniprot_id']}",
        style={"textDecoration": "none", "color": "inherit"},
    )


# =========================================================================
# Protein page header
# =========================================================================

def build_protein_header(meta):
    """Build the protein page header (title + metadata)."""
    title = f"{meta['gene_name'] or meta['uniprot_id']} ({meta['uniprot_id']})"

    info_parts = []
    if meta.get("ec_number"):
        info_parts.append(f"EC: {meta['ec_number']}")
    if meta.get("screens"):
        info_parts.append(f"Screen: {', '.join(meta['screens'])}")
    info_parts.append(f"{meta['length']} residues")
    info_parts.append(f"{meta['n_targets']} target residues")
    info_parts.append(f"{meta['n_guides']} guides")

    children = [html.H1(title)]
    if meta.get("protein_name"):
        children.append(html.P(meta["protein_name"], className="protein-name-full"))
    children.append(html.P(" | ".join(info_parts), className="protein-info"))

    return html.Div(children, className="protein-header")
