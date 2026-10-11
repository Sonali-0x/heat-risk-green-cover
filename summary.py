"""Generate a deterministic, offline action report from scored cell outputs."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence


REPORT_TEXT = {
    "english": {
        "title": "Urban heat and green-cover action summary",
        "overview": "Analysis overview",
        "cells": "Cells processed",
        "eligible": "Priority-eligible cells",
        "top": "Cells in the highest-priority 10%",
        "actions": "Recommended actions by cell",
        "top_cells": "Highest-priority cells (up to five)",
        "no_top_cells": "No cells met the priority-ranking criteria.",
        "cell": "Cell",
        "priority": "Priority",
        "action": "Action",
        "cooling": "NDVI/LST association",
        "no_association": "An association could not be estimated from these data.",
        "correlation": "Pearson correlation",
        "associated_change": "Associated LST change per +0.1 NDVI",
        "caveat": (
            "This is an observational correlation, not proof of causation and not "
            "a guaranteed cooling effect of planting or another intervention."
        ),
        "method": "Method and assumptions",
        "formula": (
            "Exposure = 0.5 × normalized LST + 0.5 × (1 − normalized NDVI). "
            "Priority = exposure × (0.5 + 0.5 × normalized population)."
        ),
        "normalization": (
            "Normalization uses complete, non-water, non-bare cells eligible for "
            "ranking. Bare-land cells are flagged and excluded from the ranked list."
        ),
        "sources": "Data sources",
        "source_landsat": "Landsat 8/9 Collection 2 Level 2: NDVI and land-surface temperature.",
        "source_dynamic_world": "Google Dynamic World: tree, built-up, and bare-land probabilities.",
        "source_worldpop": "WorldPop: modelled population estimates (reference year 2020).",
        "limitations": "Limitations",
        "lst": "Land-surface temperature (LST) is not air temperature.",
        "grid": "Grid cells are neighborhood-scale, not street- or building-level.",
        "availability": (
            "A high score does not establish land ownership, availability, or "
            "site suitability. Field verification is required."
        ),
        "worldpop": "WorldPop values are modelled population estimates.",
        "license": "Source-specific licensing and attribution must be verified before publication.",
        "generated": "Generated deterministically from scored cells; no AI service was used.",
    },
    "hindi": {
        "title": "शहरी गर्मी और हरित क्षेत्र: कार्रवाई सारांश",
        "overview": "विश्लेषण का सार",
        "cells": "विश्लेषित सेल",
        "eligible": "प्राथमिकता के योग्य सेल",
        "top": "शीर्ष 10% प्राथमिकता वाले सेल",
        "actions": "सेल के अनुसार सुझाई गई कार्रवाई",
        "top_cells": "सबसे अधिक प्राथमिकता वाले सेल (अधिकतम पाँच)",
        "no_top_cells": "प्राथमिकता क्रम के मानदंड पूरे करने वाला कोई सेल नहीं है।",
        "cell": "सेल",
        "priority": "प्राथमिकता",
        "action": "कार्रवाई",
        "cooling": "NDVI/LST संबंध",
        "no_association": "इन आंकड़ों से संबंध का अनुमान नहीं लगाया जा सका।",
        "correlation": "पीयरसन सहसंबंध",
        "associated_change": "+0.1 NDVI के साथ संबंधित LST परिवर्तन",
        "caveat": (
            "यह अवलोकन-आधारित सहसंबंध है, कारण का प्रमाण नहीं और किसी हस्तक्षेप "
            "से निश्चित ठंडक की गारंटी नहीं।"
        ),
        "method": "विधि और मान्यताएँ",
        "formula": (
            "एक्सपोज़र = 0.5 × सामान्यीकृत LST + 0.5 × (1 − सामान्यीकृत NDVI)। "
            "प्राथमिकता = एक्सपोज़र × (0.5 + 0.5 × सामान्यीकृत जनसंख्या)।"
        ),
        "normalization": (
            "सामान्यीकरण पूर्ण, गैर-जल और गैर-बंजर योग्य सेल के आधार पर है। "
            "बंजर भूमि चिह्नित है और रैंक सूची से बाहर है।"
        ),
        "sources": "डेटा स्रोत",
        "source_landsat": "Landsat 8/9 Collection 2 Level 2: NDVI और भूमि-सतह तापमान।",
        "source_dynamic_world": "Google Dynamic World: वृक्ष, निर्मित क्षेत्र और बंजर भूमि की संभावनाएँ।",
        "source_worldpop": "WorldPop: मॉडल-आधारित जनसंख्या अनुमान (संदर्भ वर्ष 2020)।",
        "limitations": "सीमाएँ",
        "lst": "भूमि-सतह तापमान (LST), वायु तापमान नहीं है।",
        "grid": "ग्रिड पड़ोस-स्तर का है, सड़क या इमारत-स्तर का नहीं।",
        "availability": (
            "ऊँचा स्कोर भूमि की उपलब्धता या उपयुक्तता सिद्ध नहीं करता। स्थल पर "
            "सत्यापन आवश्यक है।"
        ),
        "worldpop": "WorldPop मॉडल-आधारित जनसंख्या अनुमान देता है।",
        "license": "प्रकाशन से पहले स्रोत-विशिष्ट लाइसेंस और श्रेय सत्यापित करें।",
        "generated": "स्कोर किए गए सेल से नियतात्मक रूप से बनाया गया; AI सेवा का उपयोग नहीं हुआ।",
    },
    "marathi": {
        "title": "शहरी उष्णता आणि हरित क्षेत्र: कृतीचा सारांश",
        "overview": "विश्लेषणाचा आढावा",
        "cells": "विश्लेषित सेल",
        "eligible": "प्राधान्यास पात्र सेल",
        "top": "सर्वाधिक प्राधान्याचे 10% सेल",
        "actions": "सेलनुसार शिफारस केलेल्या कृती",
        "top_cells": "सर्वाधिक प्राधान्याचे सेल (कमाल पाच)",
        "no_top_cells": "प्राधान्य क्रमाचे निकष पूर्ण करणारा कोणताही सेल नाही.",
        "cell": "सेल",
        "priority": "प्राधान्य",
        "action": "कृती",
        "cooling": "NDVI/LST संबंध",
        "no_association": "या डेटावरून संबंधाचा अंदाज काढता आला नाही.",
        "correlation": "पीअर्सन सहसंबंध",
        "associated_change": "+0.1 NDVI शी संबंधित LST बदल",
        "caveat": (
            "हा निरीक्षणाधारित सहसंबंध आहे; कारणाचा पुरावा नाही आणि कोणत्याही "
            "हस्तक्षेपामुळे निश्चित थंडावा मिळेल याची हमी नाही."
        ),
        "method": "पद्धत आणि गृहीतके",
        "formula": (
            "एक्सपोजर = 0.5 × सामान्यीकृत LST + 0.5 × (1 − सामान्यीकृत NDVI). "
            "प्राधान्य = एक्सपोजर × (0.5 + 0.5 × सामान्यीकृत लोकसंख्या)."
        ),
        "normalization": (
            "सामान्यीकरण पूर्ण, जलरहित आणि बंजर नसलेल्या पात्र सेलवर आधारित आहे. "
            "बंजर जमीन दर्शवली आहे आणि क्रमवारीतून वगळली आहे."
        ),
        "sources": "डेटा स्रोत",
        "source_landsat": "Landsat 8/9 Collection 2 Level 2: NDVI आणि भूमी-पृष्ठभाग तापमान.",
        "source_dynamic_world": "Google Dynamic World: झाडे, बांधकाम क्षेत्र आणि मोकळ्या जमिनीची संभाव्यता.",
        "source_worldpop": "WorldPop: मॉडेलवर आधारित लोकसंख्या अंदाज (संदर्भ वर्ष 2020).",
        "limitations": "मर्यादा",
        "lst": "भूमी-पृष्ठभाग तापमान (LST) हे हवेचे तापमान नाही.",
        "grid": "ग्रिड शेजार-पातळीचा आहे; रस्ता किंवा इमारत-पातळीचा नाही.",
        "availability": (
            "उच्च गुणांमुळे जमीन उपलब्ध किंवा योग्य असल्याचे सिद्ध होत नाही. "
            "प्रत्यक्ष स्थळ पडताळणी आवश्यक आहे."
        ),
        "worldpop": "WorldPop हे मॉडेलवर आधारित लोकसंख्या अंदाज देते.",
        "license": "प्रकाशनापूर्वी स्रोत-विशिष्ट परवाने आणि श्रेय पडताळा.",
        "generated": "स्कोअर केलेल्या सेलमधून नियतात्मकरीत्या तयार केले; AI सेवा वापरली नाही.",
    },
}

ACTION_TRANSLATIONS = {
    "hindi": {
        "Check site: bare land": "स्थल जाँचें: बंजर भूमि",
        "Cool roof / shade": "ठंडी छत / छाया",
        "Protect existing green": "मौजूदा हरियाली सुरक्षित रखें",
        "Plant trees": "पेड़ लगाएँ",
        "Unavailable": "उपलब्ध नहीं",
    },
    "marathi": {
        "Check site: bare land": "स्थळ तपासा: मोकळी जमीन",
        "Cool roof / shade": "थंड छत / सावली",
        "Protect existing green": "सध्याची हिरवळ जतन करा",
        "Plant trees": "झाडे लावा",
        "Unavailable": "उपलब्ध नाही",
    },
}


def _format_number(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def build_action_report(
    cells: Sequence[Mapping[str, str]],
    top_cells: Sequence[Mapping[str, str]],
    metadata: Mapping[str, object],
    *,
    language: str,
    grid_size_m: int,
) -> str:
    """Return a translated Markdown report based only on computed values."""
    text = REPORT_TEXT[language]
    city = str(metadata["city"])
    start_date = str(metadata["analysis_start_inclusive"])
    end_date = str(metadata["analysis_end_inclusive"])
    eligible_count = int(metadata["priority_eligible_cell_count"])
    action_labels = ACTION_TRANSLATIONS.get(language, {})

    def translate_action(value: str) -> str:
        return action_labels.get(value, value)

    action_counts = Counter(
        translate_action(cell.get("recommended_action", "Unavailable"))
        for cell in cells
    )

    lines = [
        f"# {text['title']}",
        "",
        f"**{city}** · {start_date} to {end_date} · {grid_size_m} m grid",
        "",
        f"## {text['overview']}",
        "",
        f"- {text['cells']}: {len(cells):,}",
        f"- {text['eligible']}: {eligible_count:,}",
        f"- {text['top']}: {len(top_cells):,}",
        "",
        f"## {text['actions']}",
        "",
    ]
    for action, count in sorted(action_counts.items()):
        lines.append(f"- {action}: {count:,}")

    lines.extend(["", f"## {text['top_cells']}", ""])
    if top_cells:
        lines.append(f"| {text['cell']} | {text['priority']} | {text['action']} |")
        lines.append("|---|---:|---|")
        for cell in top_cells[:5]:
            lines.append(
                f"| {cell.get('cell_id', '')} | "
                f"{_format_number(cell.get('priority_score'))} | "
                f"{translate_action(cell.get('recommended_action', ''))} |"
            )
    else:
        lines.append(text["no_top_cells"])

    cooling = metadata.get("cooling_estimate")
    if not isinstance(cooling, Mapping):
        cooling = {}
    correlation = cooling.get("correlation")
    associated_change = cooling.get("associated_lst_change_c_per_0_1_ndvi")
    lines.extend(["", f"## {text['cooling']}", ""])
    if correlation is None:
        lines.append(text["no_association"])
    else:
        lines.append(f"- {text['correlation']}: {_format_number(correlation)}")
        lines.append(
            f"- {text['associated_change']}: "
            f"{_format_number(associated_change)} °C"
        )
    lines.extend(["", f"> **{text['caveat']}**", "", f"## {text['method']}", ""])
    lines.extend(
        [
            f"- {text['formula']}",
            f"- {text['normalization']}",
            "",
            f"## {text['sources']}",
            "",
            f"- {text['source_landsat']}",
            f"- {text['source_dynamic_world']}",
            f"- {text['source_worldpop']}",
            f"- {text['license']}",
            "",
            f"## {text['limitations']}",
            "",
            f"- {text['lst']}",
            f"- {text['grid']}",
            f"- {text['worldpop']}",
            f"- {text['availability']}",
            "",
            f"*{text['generated']}*",
            "",
        ]
    )
    return "\n".join(lines)
