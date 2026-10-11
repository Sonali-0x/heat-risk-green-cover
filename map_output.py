"""Render scored cells as a toggleable Folium map."""

from __future__ import annotations

import html
import json
import math
from typing import Mapping, Optional, Sequence, Tuple

import folium
from branca.element import Element


COLOR_STOPS: Tuple[Tuple[float, Tuple[int, int, int]], ...] = (
    (0.0, (44, 123, 182)),
    (0.5, (255, 255, 191)),
    (1.0, (215, 25, 28)),
)


def _number(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _color(value: float, *, green_scale: bool = False) -> str:
    bounded = min(1.0, max(0.0, value))
    if green_scale:
        low, high = (215, 180, 110), (24, 115, 65)
        rgb = tuple(round(a + (b - a) * bounded) for a, b in zip(low, high))
    else:
        lower, middle, upper = COLOR_STOPS
        if bounded <= middle[0]:
            fraction = bounded / middle[0]
            start, end = lower[1], middle[1]
        else:
            fraction = (bounded - middle[0]) / (upper[0] - middle[0])
            start, end = middle[1], upper[1]
        rgb = tuple(round(a + (b - a) * fraction) for a, b in zip(start, end))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _display(value: object, digits: int = 3) -> str:
    number = _number(value)
    return "Not available" if number is None else f"{number:.{digits}f}"


def _popup(cell: Mapping[str, str]) -> str:
    details = (
        ("Cell ID", cell.get("cell_id", "")),
        ("NDVI", _display(cell.get("ndvi"))),
        ("LST (°C)", _display(cell.get("lst_c"))),
        ("Estimated population", _display(cell.get("population_estimate"), 0)),
        ("Priority score", _display(cell.get("priority_score"))),
        ("Recommended action", cell.get("recommended_action", "Unavailable")),
        ("Eligibility", "Eligible" if cell.get("priority_eligible") == "True" else "Not eligible"),
        ("Exclusion reason", cell.get("exclusion_reason") or "—"),
    )
    rows = "".join(
        "<tr><th>{}</th><td>{}</td></tr>".format(
            html.escape(label, quote=True), html.escape(str(value), quote=True)
        )
        for label, value in details
    )
    return f"<table>{rows}</table>"


def _legend() -> str:
    return """
    <div style="position:fixed;bottom:24px;left:12px;z-index:9999;
                background:#fff;padding:10px 12px;border:1px solid #777;
                border-radius:4px;font:12px/1.5 Arial,sans-serif">
      <strong>Map layer color scales</strong>
      <div>NDVI: lower vegetation
        <span style="display:inline-block;width:65px;height:10px;
          background:linear-gradient(to right,#d7b46e,#187341)"></span>
        higher vegetation
      </div>
      <div>LST and priority: lower
        <span style="display:inline-block;width:65px;height:10px;
          background:linear-gradient(to right,#2c7bb6,#ffffbf,#d7191c)"></span>
        higher
      </div>
      <div>LST colors show relative values; popup values are in °C.</div>
    </div>
    """


def _header(title: str, metadata: Mapping[str, object]) -> str:
    city = html.escape(str(metadata["city"]), quote=True)
    start = html.escape(str(metadata["analysis_start_inclusive"]), quote=True)
    end = html.escape(str(metadata["analysis_end_inclusive"]), quote=True)
    safe_title = html.escape(title, quote=True)
    return f"""
    <div style="position:fixed;top:10px;left:50px;z-index:9999;
                max-width:520px;background:#fff;padding:10px 14px;
                border:1px solid #777;border-radius:4px;
                font:13px/1.45 Arial,sans-serif">
      <strong>{safe_title}</strong><br>
      {city} · {start} to {end}<br>
      Surface temperature is not air temperature. Grid cells are not
      street/building-level; verify candidate sites in the field.<br>
      Sources: Landsat 8/9, Dynamic World, and WorldPop. Dataset licensing and
      attribution verification is pending.
    </div>
    """


def render_priority_map(
    cells: Sequence[Mapping[str, str]],
    metadata: Mapping[str, object],
    *,
    title: str,
) -> str:
    """Return standalone HTML for the three independently toggleable layers."""
    points = []
    for cell in cells:
        latitude = _number(cell.get("latitude"))
        longitude = _number(cell.get("longitude"))
        if latitude is None or longitude is None:
            continue
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue
        points.append((latitude, longitude, cell))
    if not points:
        raise ValueError("Scored cells contain no valid map coordinates.")

    center = (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )
    map_view = folium.Map(
        location=center,
        zoom_start=12,
        control_scale=True,
        tiles="OpenStreetMap",
        prefer_canvas=True,
    )

    ndvi_values = [_number(c.get("ndvi")) for _, _, c in points if _number(c.get("ndvi")) is not None]
    lst_values = [_number(c.get("lst_c")) for _, _, c in points if _number(c.get("lst_c")) is not None]
    ndvi_min, ndvi_span = (min(ndvi_values), max(ndvi_values) - min(ndvi_values)) if ndvi_values else (0.0, 0.0)
    lst_min, lst_span = (min(lst_values), max(lst_values) - min(lst_values)) if lst_values else (0.0, 0.0)

    cell_records = []
    for latitude, longitude, cell in points:
        raw_ndvi = _number(cell.get("ndvi"))
        raw_lst = _number(cell.get("lst_c"))
        raw_score = _number(cell.get("priority_score"))

        norm_ndvi = _number(cell.get("normalized_ndvi"))
        if norm_ndvi is None and raw_ndvi is not None:
            norm_ndvi = (raw_ndvi - ndvi_min) / ndvi_span if ndvi_span > 1e-12 else 0.5

        norm_lst = _number(cell.get("normalized_lst"))
        if norm_lst is None and raw_lst is not None:
            norm_lst = (raw_lst - lst_min) / lst_span if lst_span > 1e-12 else 0.5

        c_ndvi = _color(norm_ndvi, green_scale=True) if norm_ndvi is not None else "#999999"
        c_lst = _color(norm_lst, green_scale=False) if norm_lst is not None else "#999999"
        c_score = _color(raw_score, green_scale=False) if raw_score is not None else "#999999"

        cell_records.append([
            round(latitude, 6),
            round(longitude, 6),
            c_score,
            c_ndvi,
            c_lst,
            _display(raw_score),
            _display(raw_ndvi),
            _display(raw_lst),
            _popup(cell),
        ])

    data_json = json.dumps(cell_records, separators=(",", ":"))

    client_script = f"""
    <script>
    document.addEventListener("DOMContentLoaded", function() {{
      var mapObj = null;
      for (var k in window) {{
        if (window[k] && window[k]._leaflet_id && window[k].options && window[k].options.preferCanvas !== undefined) {{
          mapObj = window[k];
          break;
        }}
      }}
      if (!mapObj) return;

      var cellsData = {data_json};
      var priorityLayer = L.featureGroup();
      var ndviLayer = L.featureGroup();
      var lstLayer = L.featureGroup();

      cellsData.forEach(function(d) {{
        var lat = d[0], lon = d[1], cScore = d[2], cNdvi = d[3], cLst = d[4];
        var txtScore = d[5], txtNdvi = d[6], txtLst = d[7], popupHtml = d[8];

        var mPriority = L.circleMarker([lat, lon], {{
          radius: 4, color: "#333333", weight: 0.7, fill: true, fillColor: cScore, fillOpacity: 0.8
        }}).bindPopup(popupHtml, {{maxWidth: 360}}).bindTooltip("Priority: " + txtScore);
        priorityLayer.addLayer(mPriority);

        var mNdvi = L.circleMarker([lat, lon], {{
          radius: 4, color: "#333333", weight: 0.7, fill: true, fillColor: cNdvi, fillOpacity: 0.8
        }}).bindPopup(popupHtml, {{maxWidth: 360}}).bindTooltip("NDVI: " + txtNdvi);
        ndviLayer.addLayer(mNdvi);

        var mLst = L.circleMarker([lat, lon], {{
          radius: 4, color: "#333333", weight: 0.7, fill: true, fillColor: cLst, fillOpacity: 0.8
        }}).bindPopup(popupHtml, {{maxWidth: 360}}).bindTooltip("LST (°C): " + txtLst);
        lstLayer.addLayer(mLst);
      }});

      priorityLayer.addTo(mapObj);
      var overlays = {{
        "Priority": priorityLayer,
        "NDVI": ndviLayer,
        "LST (°C)": lstLayer
      }};
      L.control.layers(null, overlays, {{collapsed: false}}).addTo(mapObj);
    }});
    </script>
    """
    map_view.get_root().html.add_child(Element(_header(title, metadata)))
    map_view.get_root().html.add_child(Element(_legend()))
    map_view.get_root().html.add_child(Element(client_script))
    return map_view.get_root().render()
