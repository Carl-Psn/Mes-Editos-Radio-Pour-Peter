"""Éditos France Inter · Préparation INSP — interface Streamlit.

Onglets : suivi mensuel, atelier de fichage, bilan du mois & exports, paramètres.
Lancement : streamlit run app.py
"""

from __future__ import annotations

import base64
import calendar
import dataclasses
import html
import io
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image, UnidentifiedImageError

import ai_engine
import database as db
import episode_fetcher
import exporter
import fiche_import
import richtext_md as rt
from streamlit_quill import st_quill
import persistence
import rss_fetcher
import transcript_fetcher

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
STYLES_PATH = BASE_DIR / "styles.css"

AUTO_SYNC_MAX_AGE = timedelta(hours=1)
MAX_COLUMNS = 4

TAB_SUIVI = ":material/calendar_month: Suivi mensuel"
TAB_ATELIER = ":material/edit_note: Atelier de fichage"
TAB_BILAN = ":material/insights: Bilan du mois & Exports"
TAB_PARAMS = ":material/tune: Paramètres"

CATEGORY_LABELS = {
    "politique": "Politique",
    "eco": "Économie",
    "geopolitique": "Géopolitique",
    "invite": "Invité",
    "autre": "Autre",
}
CATEGORY_ICONS = {
    "politique": "landmark",
    "eco": "trend",
    "geopolitique": "globe",
    "invite": "mic",
    "autre": "rss",
}

# Couleurs de badge Streamlit (redéfinies dans .streamlit/config.toml) associées à chaque famille d'émission.
BADGE_COLORS = {"politique": "red", "eco": "green", "geopolitique": "blue", "invite": "violet", "autre": "gray"}
LIST_LIMIT = 150

EXPORT_SINGLE = "single"
EXPORT_CATEGORY = "category"
EXPORT_DOSSIER = "dossier"
EXPORT_LABELS = {
    EXPORT_SINGLE: "La fiche d'un seul édito",
    EXPORT_CATEGORY: "Les fiches prioritaires d'une émission sur le mois",
    EXPORT_DOSSIER: "Le dossier complet des éditos prioritaires du mois, synthèse mensuelle incluse",
}
MIN_PRIORITY_LABELS = {
    2: "Importants et incontournables (priorités 2 et 3)",
    3: "Incontournables uniquement (priorité 3)",
    1: "Toutes les priorités (1 à 3)",
}
FICHE_FILTERS = ("Tous", "À ficher", "Fichés")
FICHE_EDITOR_TOOLBAR = [
    ["bold", "italic", "underline"],
    [{"color": []}],
    [{"header": [1, 2, False]}],
    ["blockquote"],
    [{"list": "bullet"}, {"indent": "-1"}, {"indent": "+1"}],
    ["clean"],
]

# Valeurs de widgets à conserver quand leur onglet n'est pas affiché (les onglets sont rendus à la demande).
PERSISTENT_KEYS = (
    "suivi_month",
    "suivi_year",
    "bilan_month",
    "bilan_year",
    "suivi_newest_first",
    "suivi_hide_listened",
    "atelier_shows",
    "atelier_priorities",
    "atelier_period",
    "atelier_fiche_filter",
    "export_kind",
    "export_format",
    "export_show",
    "export_min_priority",
    "export_include_unfiched",
)

# ----------------------------------------------------------------------- pictogrammes

_ICON_PATHS = {
    "calendar": '<rect x="3" y="4.5" width="18" height="16.5" rx="3"/><path d="M8 2.5v4M16 2.5v4M3 10h18"/>',
    "headphones": '<path d="M4 14.5V12a8 8 0 0 1 16 0v2.5"/><rect x="2.5" y="14" width="4.5" height="7" rx="1.6"/>'
    '<rect x="17" y="14" width="4.5" height="7" rx="1.6"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8.2 12.4 2.6 2.6 5-5.4"/>',
    "star": '<path d="m12 3.2 2.7 5.5 6 .9-4.4 4.2 1.1 6-5.4-2.9-5.4 2.9 1.1-6L3.3 9.6l6-.9Z"/>',
    "pen": '<path d="M4 20h4L19.4 8.6a2.1 2.1 0 0 0-3-3L5 17v3Z"/><path d="m14.5 7.5 3 3"/>',
    "sparkles": '<path d="m11 4 1.7 4.6L17.5 10l-4.8 1.4L11 16l-1.7-4.6L4.5 10l4.8-1.4Z"/>'
    '<path d="M18.5 14.5v4M16.5 16.5h4M18 3.5v3M16.5 5h3"/>',
    "chart": '<path d="M3 20.5h18M6.5 17v-6M12 17V5.5M17.5 17v-9"/>',
    "download": '<path d="M12 3.5v11.5m0 0-4.5-4.5M12 15l4.5-4.5M4.5 20h15"/>',
    "sliders": '<path d="M4 7h9M19 7h1M4 17h1M11 17h9"/><circle cx="16" cy="7" r="2.2"/><circle cx="8" cy="17" r="2.2"/>',
    "rss": '<path d="M5 11a8 8 0 0 1 8 8M5 4.5A14.5 14.5 0 0 1 19.5 19"/><circle cx="6" cy="18" r="1.4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.2 2"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="m10.2 8.4 5.4 3.6-5.4 3.6Z"/>',
    "external": '<path d="M14 4h6v6M20 4l-9.5 9.5M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "file": '<path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "layers": '<path d="m12 3.5 9 4.8-9 4.8-9-4.8Z"/><path d="m3 13 9 4.8 9-4.8"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11.5a7 7 0 0 0 14 0M12 18.5V21"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3.2 3.4 3.2 14.6 0 18M12 3c-3.2 3.4-3.2 14.6 0 18"/>',
    "trend": '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "landmark": '<path d="M3 20.5h18M5.5 20V10.5M10 20v-9.5M14 20v-9.5M18.5 20v-9.5M12 3.5 3.5 8.5h17Z"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="m4 18 5.5-5 4 3.5 2.5-2 4 3.5"/>',
}

_LOGO_SVG = (
    '<svg class="brand-mark" viewBox="0 0 48 48" width="46" height="46" aria-hidden="true">'
    '<rect width="48" height="48" rx="14" fill="#E2001A"/>'
    '<g stroke="#fff" stroke-width="3.2" stroke-linecap="round">'
    '<path d="M13 21v6M19 16v16M25 12v24M31 17v14M37 21v6"/></g></svg>'
)

_EMPTY_SVG = (
    '<svg viewBox="0 0 200 130" width="190" height="124" fill="none" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<rect x="42" y="46" width="116" height="66" rx="14" stroke="#CBD5E1" stroke-width="2.5" fill="#fff"/>'
    '<circle cx="76" cy="79" r="17" stroke="#CBD5E1" stroke-width="2.5"/>'
    '<circle cx="76" cy="79" r="5" fill="#E2001A"/>'
    '<path d="M108 68h34M108 80h34M108 92h20" stroke="#CBD5E1" stroke-width="2.5"/>'
    '<path d="M62 46 104 18" stroke="#CBD5E1" stroke-width="2.5"/><circle cx="106" cy="17" r="3.5" fill="#E2001A"/>'
    '<path d="M124 22c6 3 10 8 12 14M134 12c9 5 15 13 18 22" stroke="#E2001A" stroke-width="2.5" opacity=".55"/>'
    "</svg>"
)


def icon(name: str, size: int = 16) -> str:
    return (
        f'<svg class="ico" viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_ICON_PATHS[name]}</svg>'
    )


# ---------------------------------------------------------------------- petits outils


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def md_escape(text: str) -> str:
    """Neutralise la syntaxe Markdown d'un texte issu du RSS avant de l'insérer dans un libellé de widget."""
    return re.sub(r"([\\*_\[\]`$~<>#|])", r"\\\1", text)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return f"{count} {singular if count <= 1 else plural_form or singular + 's'}"


# Sur téléphone, la liste de l'atelier et l'espace de fichage sont empilés : amène l'épisode choisi à l'écran.
_SCROLL_TO_WORKSPACE_JS = """
let tries = 0;
const go = () => {
  const target = document.querySelector('[class*="st-key-workspace_"]');
  if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  else if (tries++ < 20) setTimeout(go, 100);
};
go();
"""

# À l'arrivée depuis un autre onglet : remonte en haut de page et amène l'épisode choisi en tête de liste.
_REVEAL_SELECTED_JS = """
let tries = 0;
const go = () => {
  const item = document.querySelector('[class*="st-key-picksel_"]');
  if (!item) { if (tries++ < 20) setTimeout(go, 100); return; }
  let box = item.parentElement;
  while (box && !(box.scrollHeight > box.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(box).overflowY))) {
    box = box.parentElement;
  }
  if (box && box.closest('[class*="st-key-main_tabs"]')) {
    box.scrollTop += item.getBoundingClientRect().top - box.getBoundingClientRect().top - 8;
  }
  const main = document.querySelector('[data-testid="stMain"]');
  if (main && !window.matchMedia("(max-width: 640px)").matches) main.scrollTo({ top: 0 });
};
go();
"""


def page_script(body: str, phone_only: bool = False) -> None:
    """Exécute un court script dans la page, au besoin sur écran de téléphone seulement (seuil de styles.css)."""
    # Le compteur rend chaque balise unique : un script identique au précédent ne serait pas rejoué.
    count = st.session_state["page_script_count"] = st.session_state.get("page_script_count", 0) + 1
    guard = 'if (!window.matchMedia("(max-width: 640px)").matches) return; ' if phone_only else ""
    st.html(f"<script>(() => {{ /* {count} */ {guard}{body} }})();</script>", unsafe_allow_javascript=True)


def safe_url(url: str | None) -> str | None:
    return url if url and url.startswith(("http://", "https://")) else None


def flash(message: str, icon_name: str = ":material/check_circle:") -> None:
    st.session_state.setdefault("flash", []).append((message, icon_name))


def show_flashes() -> None:
    for message, icon_name in st.session_state.pop("flash", []):
        st.toast(message, icon=icon_name)


def keep_widget_state() -> None:
    for key in PERSISTENT_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def sanitize_choice(key: str, options: list[Any]) -> None:
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def sanitize_multi(key: str, options: list[Any]) -> None:
    if key in st.session_state:
        st.session_state[key] = [value for value in st.session_state[key] if value in options]


def show_name(show: dict[str, Any]) -> str:
    return show.get("title") or "Émission à synchroniser"


def category_of(item: dict[str, Any]) -> str:
    category = item.get("show_category") or item.get("category") or "autre"
    return category if category in db.CATEGORIES else "autre"


def badge(label: str, category: str) -> str:
    return (f'<span class="badge badge-{category}">{icon(CATEGORY_ICONS[category], 13)}'
            f'<span class="badge-text">{esc(label)}</span></span>')


def time_label(published_at: str | None) -> str:
    # Un épisode ajouté à l'unité peut n'avoir qu'une date, sans heure de diffusion.
    if len(published_at or "") <= 10:
        return ""
    try:
        moment = datetime.fromisoformat(published_at or "")
    except ValueError:
        return ""
    return f"{moment.hour:02d}h{moment.minute:02d}"


def duration_label(duration: str | None) -> str:
    if not duration:
        return ""
    try:
        parts = [int(part) for part in str(duration).split(":")]
    except ValueError:
        return ""
    if len(parts) == 1:
        parts = [0, *divmod(parts[0], 60)]
    while len(parts) < 3:
        parts.insert(0, 0)
    hours, minutes, seconds = parts[-3:]
    total_minutes = hours * 60 + minutes + (1 if seconds >= 30 else 0)
    if total_minutes == 0:
        return f"{seconds} s"
    return f"{total_minutes} min"


def current_model() -> str:
    return db.get_setting("gemini_model") or ai_engine.DEFAULT_MODEL


def fiche_source_audio() -> bool:
    return (db.get_setting("fiche_source") or "transcript").strip().lower() == "audio"


@st.cache_data(show_spinner=False, max_entries=64)
def _logo_data_uri(path: str, mtime: float, size: int) -> str | None:
    """Miniature d'un logo local, encodée pour être intégrée au HTML des cartes."""
    try:
        with Image.open(path) as image:
            image = image.convert("RGBA")
            image.thumbnail((size, size))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
    except (OSError, UnidentifiedImageError):
        return None
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def custom_logo_src(filename: str | None, size: int = 160) -> str | None:
    if not filename:
        return None
    path = ASSETS_DIR / filename
    if not path.is_file():
        return None
    return _logo_data_uri(str(path), path.stat().st_mtime, size)


def thumb_html(item: dict[str, Any], css_class: str = "ep-thumb") -> str:
    """Logo personnalisé de l'émission, à défaut vignette RSS de l'épisode, à défaut pictogramme."""
    source = (
        custom_logo_src(item.get("show_custom_logo") or item.get("custom_logo"))
        or safe_url(item.get("image_url"))
        or safe_url(item.get("show_image_url"))
    )
    if source:
        return f'<img class="{css_class}" src="{esc(source)}" alt="" loading="lazy">'
    category = category_of(item)
    return f'<span class="{css_class} thumb-placeholder thumb-{category}">{icon(CATEGORY_ICONS[category], 22)}</span>'


def render_html(markup: str, target: Any = st) -> None:
    """Affiche du HTML maison. st.html supprime les SVG en ligne ; st.markdown les conserve.

    Le balisage est ramené sur une seule ligne pour que Markdown le traite comme un bloc HTML brut.
    """
    flat = " ".join(line.strip() for line in markup.splitlines() if line.strip())
    target.markdown(f'<div class="ui">{flat}</div>', unsafe_allow_html=True)


def empty_state(title: str, text: str) -> None:
    render_html(
        f'<div class="empty-state">{_EMPTY_SVG}<div class="empty-title">{esc(title)}</div>'
        f'<div class="empty-text">{esc(text)}</div></div>'
    )


def section_title(icon_name: str, title: str, hint: str = "") -> None:
    hint_html = f'<span class="section-hint">{esc(hint)}</span>' if hint else ""
    render_html(f'<div class="section-title"><span class="section-ico">{icon(icon_name, 18)}</span>'
            f'<div class="section-name" role="heading" aria-level="2">{esc(title)}</div>{hint_html}</div>')


# ------------------------------------------------------------------- synchronisation


def run_sync(shows: list[dict[str, Any]] | None = None, announce: bool = True) -> list[rss_fetcher.SyncReport]:
    with st.spinner("Synchronisation des flux RSS…"):
        reports = [rss_fetcher.sync_show(show) for show in shows] if shows is not None else rss_fetcher.sync_all()
    st.session_state["sync_reports"] = [dataclasses.asdict(report) for report in reports]
    st.session_state["sync_time"] = datetime.now().strftime("%d/%m/%Y à %Hh%M")
    failures = [report for report in reports if not report.ok]
    added = sum(report.added for report in reports)
    if failures:
        names = ", ".join(report.label for report in failures)
        flash(f"Synchronisation impossible pour : {names}. Les données locales restent affichées.",
              ":material/cloud_off:")
    if announce and len(failures) < len(reports):
        news = "aucun nouvel épisode" if not added else "1 nouvel épisode" if added == 1 else f"{added} nouveaux épisodes"
        flash(f"Flux synchronisés : {news}.", ":material/sync:")
    return reports


def auto_sync() -> None:
    """Une synchronisation automatique par session, si les flux n'ont pas été relevés récemment."""
    if st.session_state.get("auto_sync_done"):
        return
    st.session_state["auto_sync_done"] = True
    shows = db.list_shows(only_enabled=True, feeds_only=True)
    if not shows:
        return

    def is_stale(show: dict[str, Any]) -> bool:
        if not show["last_synced_at"]:
            return True
        return datetime.now() - datetime.fromisoformat(show["last_synced_at"]) > AUTO_SYNC_MAX_AGE

    if any(is_stale(show) for show in shows):
        run_sync(announce=False)


# ------------------------------------------------------------------ sélecteur de mois


def month_selector(scope: str) -> str:
    """Sélecteur mois/année, partagé entre l'onglet de suivi et celui du bilan."""
    today = date.today()
    years = sorted({today.year, *(int(month[:4]) for month in db.available_months())}, reverse=True)
    month_key, year_key = f"{scope}_month", f"{scope}_year"
    other = "bilan" if scope == "suivi" else "suivi"
    for prefix in (scope, other):
        st.session_state.setdefault(f"{prefix}_month", today.month)
        st.session_state.setdefault(f"{prefix}_year", today.year)
    if st.session_state[year_key] not in years:
        st.session_state[year_key] = today.year

    def mirror() -> None:
        st.session_state[f"{other}_month"] = st.session_state[month_key]
        st.session_state[f"{other}_year"] = st.session_state[year_key]

    with st.container(key=f"{scope}_monthpick"):
        month_col, year_col, _spacer = st.columns([1.6, 1.1, 6], wrap=False)
    month_col.selectbox(
        "Mois",
        list(range(1, 13)),
        format_func=lambda number: exporter.month_label(f"2000-{number:02d}").split()[0].capitalize(),
        key=month_key,
        on_change=mirror,
    )
    year_col.selectbox("Année", years, key=year_key, on_change=mirror)
    return f"{st.session_state[year_key]:04d}-{st.session_state[month_key]:02d}"


def month_days(month: str) -> list[date]:
    """Jours du lundi au samedi du mois, jusqu'à aujourd'hui inclus."""
    year, number = (int(part) for part in month.split("-"))
    last_day = calendar.monthrange(year, number)[1]
    days = (date(year, number, day) for day in range(1, last_day + 1))
    return [day for day in days if day.weekday() != rss_fetcher.SUNDAY and day <= date.today()]


# ------------------------------------------------------------------------ en-tête


def render_masthead() -> None:
    month = date.today().strftime("%Y-%m")
    episodes = db.list_episodes(month=month)
    listened = sum(1 for ep in episodes if ep["listened"])
    fiches = sum(1 for ep in episodes if (ep["fiche"] or "").strip())
    label = exporter.month_label(month)
    render_html(
        f"""
        <header class="masthead">
          <div class="brand">{_LOGO_SVG}
            <div>
              <div class="brand-kicker">France Inter · Peter LAURENSON</div>
              <div class="brand-title" role="heading" aria-level="1">Mes éditos du matin</div>
              <div class="brand-sub">Suivre, hiérarchiser et ficher les chroniques quotidiennes, du lundi au samedi.</div>
            </div>
          </div>
          <div class="masthead-stats">
            <div class="stat-pill">{icon("calendar")}<span><b>{len(episodes)}</b> épisode{"s" if len(episodes) > 1 else ""}<span class="pill-extra"> en {esc(label)}</span></span></div>
            <div class="stat-pill">{icon("headphones")}<span><b>{listened}</b> écouté{"s" if listened > 1 else ""}</span></div>
            <div class="stat-pill">{icon("file")}<span><b>{fiches}</b> fiche{"s" if fiches > 1 else ""}</span></div>
          </div>
        </header>
        """
    )


# ----------------------------------------------------------- onglet 1 : suivi mensuel


def _on_listened(episode_id: int, key: str) -> None:
    db.set_listened(episode_id, bool(st.session_state[key]))


def tracking_controls(ep: dict[str, Any], scope: str) -> None:
    """Case « Écouté » et étoiles de priorité, enregistrées dès qu'elles changent."""
    listened_key = f"{scope}_listened_{ep['id']}"
    # Côte à côte quand la carte est assez large, l'un sous l'autre sinon.
    with st.container(key=f"track_{scope}_{ep['id']}", horizontal=True, vertical_alignment="center"):
        st.checkbox(
            "Écouté",
            value=bool(ep["listened"]),
            key=listened_key,
            on_change=_on_listened,
            args=(ep["id"], listened_key),
        )
        with st.container(key=f"stars_{scope}_{ep['id']}", horizontal=True, wrap=False, width="content",
                          vertical_alignment="center", gap=None):
            st.markdown("Priorité :", width="content")
            for level, name in db.PRIORITY_LABELS.items():
                # L'état figure dans la clé pour que la feuille de style colore les étoiles allumées.
                state = "on" if level <= ep["priority"] else "off"
                st.button(
                    "★",
                    key=f"star_{state}_n{level}_{scope}_{ep['id']}",
                    type="tertiary",
                    help=f"Priorité {name.replace(' - ', ' · ')}",
                    on_click=db.set_priority,
                    args=(ep["id"], level),
                )


def episode_links_html(ep: dict[str, Any]) -> str:
    links = []
    if safe_url(ep.get("audio_url")):
        links.append(f'<a class="ep-link" href="{esc(ep["audio_url"])}" target="_blank" rel="noopener">'
                     f'{icon("play", 14)}Écouter</a>')
    if safe_url(ep.get("link")):
        links.append(f'<a class="ep-link" href="{esc(ep["link"])}" target="_blank" rel="noopener">'
                     f'{icon("external", 14)}Page de l\'épisode</a>')
    return f'<div class="ep-links">{"".join(links)}</div>' if links else ""


def open_in_atelier(episode_id: int) -> None:
    """Bascule sur l'atelier de fichage, centré sur cet épisode (rappel de bouton, exécuté avant le rendu)."""
    ep = db.get_episode(episode_id)
    if not ep:
        return
    # Seuls les filtres qui masqueraient l'épisode sont relâchés.
    st.session_state["atelier_period"] = ep["pub_date"][:7]
    if ep["show_id"] not in st.session_state.get("atelier_shows", [ep["show_id"]]):
        st.session_state["atelier_shows"] = []
    if ep["priority"] not in st.session_state.get("atelier_priorities", [ep["priority"]]):
        st.session_state["atelier_priorities"] = []
    has_fiche = bool((ep["fiche"] or "").strip())
    if st.session_state.get("atelier_fiche_filter") == ("À ficher" if has_fiche else "Fichés"):
        st.session_state["atelier_fiche_filter"] = FICHE_FILTERS[0]
    st.session_state["atelier_episode_id"] = episode_id
    st.session_state["atelier_scroll"] = True
    st.session_state["atelier_reveal"] = True
    st.session_state["main_tabs"] = TAB_ATELIER


def episode_card(ep: dict[str, Any]) -> None:
    category = category_of(ep)
    state = "done" if ep["listened"] else "todo"
    meta = " · ".join(part for part in (time_label(ep["published_at"]), duration_label(ep["duration"])) if part)
    fiche_chip = f'<span class="chip chip-fiche">{icon("file", 12)}Fiche</span>' if (ep["fiche"] or "").strip() else ""
    summary = f'<div class="ep-summary">{esc(ep["summary"])}</div>' if ep["summary"] else ""
    with st.container(key=f"card_{category}_{state}_{ep['id']}"):
        render_html(
            f"""
            <div class="ep-head">
              {thumb_html(ep)}
              <div class="ep-headtext">
                <div class="ep-badges">{badge(ep["show_title"] or "Émission", category)}{fiche_chip}</div>
                {f'<div class="ep-meta">{icon("clock", 12)}{esc(meta)}</div>' if meta else ""}
              </div>
            </div>
            <div class="ep-title">{esc(ep["title"])}</div>
            {summary}
            {episode_links_html(ep)}
            """
        )
        # Bouton transparent que la feuille de style superpose à la vignette de l'épisode.
        st.button(
            "Ouvrir dans l'atelier de fichage",
            key=f"openfiche_{ep['id']}",
            icon=":material/edit_note:",
            help="Ouvrir cet épisode dans l'atelier de fichage",
            on_click=open_in_atelier,
            args=(ep["id"],),
        )
        tracking_controls(ep, "suivi")


def render_suivi() -> None:
    shows = db.list_shows(only_enabled=True)
    if not shows:
        empty_state("Aucune émission active", "Activez ou ajoutez un flux RSS dans l'onglet Paramètres.")
        return

    month = month_selector("suivi")
    label = exporter.month_label(month)
    episodes = db.list_episodes(month=month)
    if not episodes:
        empty_state(
            f"Aucun épisode enregistré pour {label}",
            "Les flux Radio France ne remontent que quelques semaines en arrière : les épisodes "
            "s'accumulent dans la base locale au fil des synchronisations.",
        )
        if st.button("Synchroniser les flux maintenant", icon=":material/sync:", key="suivi_sync"):
            run_sync()
            st.rerun()
        return

    listened = sum(1 for ep in episodes if ep["listened"])
    top = sum(1 for ep in episodes if ep["priority"] == 3)
    percent = round(100 * listened / len(episodes))
    with st.container(key="suivi_toolbar"):
        summary_col, order_col, hide_col = st.columns([5, 1.7, 1.7], vertical_alignment="center")
    render_html(
        f"""
        <div class="month-strip">
          <div class="month-strip-text"><b>{esc(label.capitalize())}</b>
            <span>{plural(len(episodes), "épisode")} · {plural(listened, "écouté")} · {plural(top, "incontournable")}</span></div>
          <div class="progress"><div class="progress-bar" style="width:{percent}%"></div></div>
          <div class="progress-value">{percent} %</div>
        </div>
        """,
        summary_col,
    )
    st.session_state.setdefault("suivi_newest_first", True)
    newest_first = order_col.toggle("Plus récents en premier", key="suivi_newest_first")
    hide_listened = hide_col.toggle("Masquer les écoutés", key="suivi_hide_listened")

    by_day: dict[str, list[dict[str, Any]]] = {}
    for ep in episodes:
        by_day.setdefault(ep["pub_date"], []).append(ep)
    days = sorted({*month_days(month), *(date.fromisoformat(day) for day in by_day)}, reverse=newest_first)

    shown = 0
    for day in days:
        day_episodes = by_day.get(day.isoformat(), [])
        done = sum(1 for ep in day_episodes if ep["listened"])
        visible = [ep for ep in day_episodes if not (hide_listened and ep["listened"])]
        if hide_listened and not visible:
            continue
        shown += 1
        counter = f'<span class="day-count">{done}/{len(day_episodes)} écouté{"s" if done > 1 else ""}</span>' if day_episodes else ""
        weekday, rest = exporter.format_date_fr(day).split(" ", 1)
        render_html(
            f'<div class="day-header"><span class="day-name">{esc(weekday.capitalize())}</span>'
            f'<span class="day-date">{esc(rest)}</span>{counter}</div>'
        )
        if not day_episodes:
            render_html('<div class="day-empty">Aucun épisode synchronisé pour cette journée.</div>')
            continue
        # Les épisodes ajoutés à l'unité n'occupent une colonne que les jours où il y en a.
        day_shows = [
            show for show in shows
            if not db.is_manual_show(show) or any(ep["show_id"] == show["id"] for ep in day_episodes)
        ]
        for start in range(0, len(day_shows), MAX_COLUMNS):
            row = day_shows[start : start + MAX_COLUMNS]
            with st.container(key=f"dayrow_{day.isoformat()}_{start}"):
                columns = st.columns(max(len(row), 3))
            for column, show in zip(columns, row):
                show_episodes = [ep for ep in visible if ep["show_id"] == show["id"]]
                with column:
                    if not show_episodes:
                        has_hidden = any(ep["show_id"] == show["id"] for ep in day_episodes)
                        text = "Déjà écouté" if has_hidden else "Pas d'épisode ce jour-là"
                        render_html(f'<div class="slot-empty"><b>{esc(show_name(show))}</b><span>{text}</span></div>')
                    for ep in show_episodes:
                        episode_card(ep)
    if shown == 0:
        empty_state("Tout est écouté", "Aucun épisode en attente d'écoute sur ce mois.")


# ------------------------------------------------------ onglet 2 : atelier de fichage


def _select_episode(episode_id: int) -> None:
    st.session_state["atelier_episode_id"] = episode_id
    st.session_state["atelier_scroll"] = True


def episode_button_label(ep: dict[str, Any]) -> str:
    """Libellé Markdown d'une ligne de la liste : badge de l'émission, date, priorité, état de la fiche, titre."""
    color = BADGE_COLORS[category_of(ep)]
    day = date.fromisoformat(ep["pub_date"])
    stars = "★" * ep["priority"] + "☆" * (3 - ep["priority"])
    if (ep["fiche_draft"] or "").strip():
        status = " :orange-badge[:material/edit_note: Brouillon]"
    elif (ep["fiche"] or "").strip():
        status = " :gray-badge[:material/description: Fiche]"
    else:
        status = ""
    listened = " :gray[:material/headphones:]" if ep["listened"] else ""
    return (
        f":{color}-badge[{md_escape(ep['show_title'] or 'Émission')}] "
        f":gray[{day.strftime('%d/%m/%y')}] :red[{stars}]{listened}{status}  \n"
        f"**{md_escape(ep['title'])}**"
    )


def render_atelier() -> None:
    shows = db.list_shows(only_enabled=True)
    if not shows:
        empty_state("Aucune émission active", "Activez ou ajoutez un flux RSS dans l'onglet Paramètres.")
        return
    show_ids = [show["id"] for show in shows]
    titles = {show["id"]: show_name(show) for show in shows}
    months = db.available_months()
    periods = ["all", *months]
    current = date.today().strftime("%Y-%m")

    sanitize_multi("atelier_shows", show_ids)
    sanitize_choice("atelier_period", periods)
    st.session_state.setdefault("atelier_period", current if current in months else "all")

    section_title("pen", "Atelier de fichage", "Choisissez un épisode, générez sa fiche puis relisez-la avant de l'enregistrer.")
    with st.container(key="atelier_filters"):
        show_col, priority_col, period_col, fiche_col = st.columns([2.2, 2.2, 1.5, 1.8])
    selected_shows = show_col.multiselect(
        "Émission", show_ids, format_func=titles.get, key="atelier_shows", placeholder="Toutes les émissions"
    )
    selected_priorities = priority_col.multiselect(
        "Niveau de priorité",
        [3, 2, 1],
        format_func=db.PRIORITY_LABELS.get,
        key="atelier_priorities",
        placeholder="Toutes les priorités",
    )
    period = period_col.selectbox(
        "Période",
        periods,
        format_func=lambda value: "Tous les mois" if value == "all" else exporter.month_label(value).capitalize(),
        key="atelier_period",
    )
    st.session_state.setdefault("atelier_fiche_filter", FICHE_FILTERS[0])
    fiche_filter = fiche_col.segmented_control("Fiche", FICHE_FILTERS, key="atelier_fiche_filter", required=True)

    episodes = db.list_episodes(
        month=None if period == "all" else period,
        show_ids=selected_shows or None,
        priorities=selected_priorities or None,
        with_fiche={"À ficher": False, "Fichés": True}.get(fiche_filter),
        newest_first=True,
    )

    ids = [ep["id"] for ep in episodes]
    remembered = st.session_state.get("atelier_episode_id")
    selected_id = remembered if remembered in ids else None

    list_col, work_col = st.columns([5, 7], gap="large")
    with list_col:
        render_html(f'<div class="list-caption">{plural(len(episodes), "épisode")} correspondant aux filtres</div>')
        if not episodes:
            empty_state("Aucun épisode", "Élargissez les filtres pour retrouver des épisodes à ficher.")
        else:
            with st.container(height=660, border=False, key="atelier_list"):
                for ep in episodes[:LIST_LIMIT]:
                    prefix = "picksel" if ep["id"] == selected_id else "pick"
                    st.button(
                        episode_button_label(ep),
                        key=f"{prefix}_{ep['id']}",
                        on_click=_select_episode,
                        args=(ep["id"],),
                        width="stretch",
                    )
            if len(episodes) > LIST_LIMIT:
                st.caption(f"Seuls les {LIST_LIMIT} épisodes les plus récents sont listés : affinez les filtres pour voir les autres.")

    with work_col:
        episode = db.get_episode(selected_id) if selected_id else None
        if not episode:
            empty_state("Sélectionnez un épisode", "Cliquez sur un épisode de la liste pour ouvrir son espace de fichage.")
        else:
            render_workspace(episode)
    if st.session_state.pop("atelier_reveal", False) and episode:
        page_script(_REVEAL_SELECTED_JS)
    if st.session_state.pop("atelier_scroll", False) and episode:
        page_script(_SCROLL_TO_WORKSPACE_JS, phone_only=True)


def fiche_export_buttons(ep: dict[str, Any], text: str) -> None:
    """Export direct de la fiche affichée, en Word ou en PDF : même document que « La fiche d'un seul édito » du bilan."""
    document = exporter.single_fiche_document({**ep, "fiche": text})
    formats = (
        ("docx", "Word", "Word (.docx)", exporter.DOCX_MIME, exporter.build_docx),
        ("pdf", "PDF", "PDF (.pdf)", exporter.PDF_MIME, exporter.build_pdf),
    )
    for file_format, label, long_label, mime, build in formats:
        st.download_button(
            label,
            # Le fichier n'est fabriqué qu'au clic, pas à chaque affichage de l'atelier.
            data=lambda build=build: build(document),
            file_name=f"{document.filename_stem}.{file_format}",
            mime=mime,
            icon=":material/download:",
            key=f"fiche_export_{file_format}_{ep['id']}",
            on_click="ignore",
            disabled=not text.strip(),
            help=(
                f"Exporter la fiche affichée au format {long_label}."
                if text.strip()
                else "Rédigez, générez ou importez d'abord la fiche pour pouvoir l'exporter."
            ),
        )


def render_workspace(ep: dict[str, Any]) -> None:
    category = category_of(ep)
    meta = " · ".join(
        part
        for part in (
            exporter.format_date_fr(ep["pub_date"]),
            time_label(ep["published_at"]),
            duration_label(ep["duration"]),
            ep["author"],
        )
        if part
    )
    summary = f'<div class="ep-summary full">{esc(ep["summary"])}</div>' if ep["summary"] else ""
    with st.container(key=f"workspace_{category}_{ep['id']}"):
        render_html(
            f"""
            <div class="ep-head">
              {thumb_html(ep, "ep-thumb large")}
              <div class="ep-headtext">
                <div class="ep-badges">{badge(ep["show_title"] or "Émission", category)}</div>
                <div class="ws-title">{esc(ep["title"])}</div>
                <div class="ep-meta">{esc(meta)}</div>
              </div>
            </div>
            {summary}
            {episode_links_html(ep)}
            """
        )
        if safe_url(ep["audio_url"]):
            st.audio(ep["audio_url"])
        tracking_controls(ep, "atelier")

    saved = (ep["fiche"] or "").strip()
    draft = (ep["fiche_draft"] or "").strip()
    version = st.session_state.get(f"fiche_version_{ep['id']}", 0)
    body_key = f"fiche_body_{ep['id']}_{version}"
    widget_key = f"fiche_editor_widget_{ep['id']}_{version}"
    reset_editor = body_key not in st.session_state
    if reset_editor:
        st.session_state[body_key] = rt.markdown_to_html(draft or saved)

    if draft:
        render_html(f'<div class="callout callout-draft">{icon("sparkles")}<span><b>Brouillon généré par l\'IA, non enregistré.</b> '
                "Relisez-le, corrigez-le si besoin, puis enregistrez la fiche.</span></div>")
    elif saved and ep["fiche_updated_at"]:
        when = datetime.fromisoformat(ep["fiche_updated_at"]).strftime("%d/%m/%Y à %Hh%M")
        render_html(f'<div class="callout callout-saved">{icon("check")}<span>Fiche enregistrée le {esc(when)}.</span></div>')

    configured = ai_engine.is_configured()
    has_audio = bool(safe_url(ep["audio_url"]))
    has_page = bool(safe_url(ep.get("link")))
    # Hors radiofrance.fr, il n'y a pas de retranscription à lire : l'audio est alors la seule source possible.
    use_audio = fiche_source_audio() or (has_audio and not transcript_fetcher.is_radiofrance_url(ep.get("link")))
    can_generate = configured and (has_audio if use_audio else has_page)
    generate_label = (
        "Générer la fiche IA (depuis l'audio intégral)"
        if use_audio
        else "Générer la fiche IA (depuis la retranscription)"
    )
    generate_help = (
        "Télécharge l'audio, l'envoie à Gemini puis le supprime — mode lent, utile si la page n'a pas de retranscription."
        if use_audio
        else "Lit la retranscription publiée sur la page Radio France de l'épisode, puis rédige la fiche (beaucoup plus rapide)."
    )
    # Les boutons d'export rejoignent cette rangée plus bas, une fois lu le texte présent dans l'éditeur.
    actions = st.container(key=f"fiche_actions_{ep['id']}", horizontal=True, vertical_alignment="center")
    generate = actions.button(
        generate_label,
        type="primary",
        icon=":material/auto_awesome:",
        key=f"generate_{ep['id']}",
        disabled=not can_generate,
        help=generate_help,
    )
    if not configured:
        st.caption("Clé Gemini absente : ajoutez `GEMINI_API_KEY` dans `.streamlit/secrets.toml` pour activer la génération.")
    elif use_audio and not has_audio:
        st.caption("Mode audio activé dans Paramètres, mais cet épisode n'a pas de fichier audio dans le RSS.")
    elif not use_audio and not has_page:
        st.caption("Pas de lien vers la page de l'épisode dans le flux : forcez une synchronisation ou passez en mode audio dans Paramètres.")
    elif not use_audio:
        st.caption(
            "Par défaut, la retranscription de la page d'épisode suffit. En cas d'erreur 503 durable sur Gemini, "
            "l'app réessaie automatiquement et peut basculer sur un modèle de secours ; changez aussi le modèle dans Paramètres."
        )

    with st.expander("Importer une fiche rédigée à la main", icon=":material/upload_file:", expanded=False):
        st.caption(
            "Fichiers acceptés : Markdown (`.md`) ou PDF. Le texte est extrait du PDF pour être stocké en Markdown "
            "dans l'application (les exports restent Word et PDF)."
        )
        uploaded = st.file_uploader(
            "Choisir un fichier",
            type=["pdf", "md", "markdown", "txt"],
            key=f"fiche_upload_{ep['id']}",
            label_visibility="collapsed",
            max_upload_size=15,
        )
        if uploaded:
            st.caption(f"{uploaded.name} · {uploaded.size / 1024:.1f} Ko")
        draft_col, save_col, _ = st.columns([1.4, 1.4, 1.2])
        open_draft = draft_col.button(
            "Ouvrir en brouillon",
            icon=":material/draft:",
            key=f"import_draft_{ep['id']}",
            disabled=uploaded is None,
            help="Charge le fichier dans l'éditeur pour relecture avant enregistrement.",
        )
        import_save = save_col.button(
            "Importer et enregistrer",
            icon=":material/save:",
            key=f"import_save_{ep['id']}",
            disabled=uploaded is None,
            help="Enregistre directement la fiche sur cet épisode (remplace la fiche existante).",
        )
        if uploaded and (open_draft or import_save):
            try:
                imported = fiche_import.text_from_upload(uploaded.name, uploaded.getvalue())
            except fiche_import.FicheImportError as exc:
                st.error(str(exc))
            else:
                if import_save:
                    db.save_fiche(ep["id"], imported)
                    flash("Fiche importée et enregistrée.")
                else:
                    db.save_fiche_draft(ep["id"], imported)
                    flash("Fiche importée : relisez le brouillon puis enregistrez si besoin.", ":material/upload_file:")
                st.session_state[f"fiche_version_{ep['id']}"] = version + 1
                st.rerun()

    if generate:
        status_label = "Génération de la fiche à partir de l'audio…" if use_audio else "Génération de la fiche…"
        with st.status(status_label, expanded=True) as status:
            try:
                generated = ai_engine.generate_fiche(
                    ep, model=current_model(), on_step=status.write, use_audio=use_audio
                )
            except ai_engine.AIEngineError as exc:
                status.update(label="La fiche n'a pas pu être générée", state="error")
                st.error(str(exc))
            else:
                db.save_fiche_draft(ep["id"], generated)
                st.session_state[f"fiche_version_{ep['id']}"] = version + 1
                flash("Fiche générée. Relisez-la puis enregistrez-la.", ":material/auto_awesome:")
                st.rerun()

    preview_tab, edit_tab = st.tabs(["Fiche", "Modifier le texte"])
    with edit_tab:
        st.caption(
            "Éditeur visuel : **gras** · *italique* · souligné · couleur · style (Normal / Titre 1 / Titre 2 / "
            "citation) · listes à puces sur trois niveaux (●, ○, ■ via les boutons retrait / avancée). "
            "Pas besoin de connaître le Markdown."
        )
        html_value = st_quill(
            value=st.session_state[body_key],
            html=True,
            toolbar=FICHE_EDITOR_TOOLBAR,
            key=widget_key,
        )
        if html_value is not None:
            st.session_state[body_key] = html_value
    text = rt.html_to_markdown(st.session_state.get(body_key, ""))
    with actions:
        fiche_export_buttons(ep, text)
    with preview_tab:
        if text.strip():
            with st.container(key=f"fiche_preview_{ep['id']}"):
                st.markdown(text)
        else:
            sections = "".join(f'<div class="plan-item">{esc(section)}</div>' for section in ai_engine.FICHE_SECTIONS)
            render_html(f'<div class="fiche-plan"><div class="fiche-plan-title">{icon("layers")}Plan de la fiche</div>'
                    f'{sections}<div class="fiche-plan-note">Générez la fiche depuis la retranscription, importez un '
                    f'fichier PDF/Markdown, ou rédigez avec l\'éditeur visuel dans l\'onglet « Modifier le texte ».</div></div>')

    dirty = text.strip() != saved
    save_col, discard_col, delete_col = st.columns([1.5, 1.5, 1.2])
    if save_col.button("Enregistrer la fiche", icon=":material/save:", key=f"save_{ep['id']}",
                       disabled=not text.strip() or not (dirty or draft), width="stretch"):
        db.save_fiche(ep["id"], text)
        st.session_state[f"fiche_version_{ep['id']}"] = version + 1
        flash("Fiche enregistrée.")
        st.rerun()
    if draft and discard_col.button("Abandonner le brouillon", icon=":material/undo:", key=f"discard_{ep['id']}", width="stretch"):
        db.discard_fiche_draft(ep["id"])
        st.session_state[f"fiche_version_{ep['id']}"] = version + 1
        st.rerun()
    if saved:
        with delete_col.popover("Supprimer", icon=":material/delete:", width="stretch"):
            st.write("Supprimer définitivement la fiche enregistrée de cet épisode ?")
            if st.button("Oui, supprimer la fiche", key=f"delete_{ep['id']}", type="primary"):
                db.delete_fiche(ep["id"])
                st.session_state[f"fiche_version_{ep['id']}"] = version + 1
                flash("Fiche supprimée.", ":material/delete:")
                st.rerun()
    if dirty and text.strip() and not draft:
        st.caption("Modifications non enregistrées.")


# ------------------------------------------------ onglet 3 : bilan du mois et exports


def kpi(icon_name: str, value: str, label: str, tone: str = "") -> str:
    return (f'<div class="kpi {tone}"><span class="kpi-ico">{icon(icon_name, 20)}</span>'
            f'<div><div class="kpi-value">{esc(value)}</div><div class="kpi-label">{esc(label)}</div></div></div>')


@st.cache_data(show_spinner=False, max_entries=12)
def _build_export(file_format: str, payload: str) -> bytes:
    data = json.loads(payload)
    data["entries"] = [exporter.FicheEntry(**entry) for entry in data["entries"]]
    document = exporter.ExportDocument(**data)
    return exporter.build_docx(document) if file_format == "docx" else exporter.build_pdf(document)


def render_bilan() -> None:
    month = month_selector("bilan")
    label = exporter.month_label(month)
    episodes = db.list_episodes(month=month)
    shows = db.list_shows(only_enabled=True)
    synthesis = db.get_synthesis(month)

    if not episodes:
        empty_state(f"Aucun épisode enregistré pour {label}", "Choisissez un autre mois ou synchronisez les flux dans l'onglet Paramètres.")
        return

    listened = sum(1 for ep in episodes if ep["listened"])
    fiches = [ep for ep in episodes if (ep["fiche"] or "").strip()]
    top = sum(1 for ep in episodes if ep["priority"] == 3)
    important = sum(1 for ep in episodes if ep["priority"] == 2)
    render_html(
        '<div class="kpi-grid">'
        + kpi("calendar", str(len(episodes)), f"épisode{'s' if len(episodes) > 1 else ''} en {label}")
        + kpi("headphones", f"{listened} / {len(episodes)}", "épisodes écoutés")
        + kpi("file", str(len(fiches)), "fiches rédigées" if len(fiches) > 1 else "fiche rédigée")
        + kpi("star", str(top), f"incontournable{'s' if top > 1 else ''} · {plural(important, 'important')}", "kpi-accent")
        + "</div>"
    )

    rows = []
    for show in shows:
        show_episodes = [ep for ep in episodes if ep["show_id"] == show["id"]]
        if not show_episodes:
            continue
        done = sum(1 for ep in show_episodes if ep["listened"])
        written = sum(1 for ep in show_episodes if (ep["fiche"] or "").strip())
        percent = round(100 * done / len(show_episodes))
        category = category_of(show)
        rows.append(
            f'<div class="show-row">{badge(show_name(show), category)}'
            f'<div class="progress"><div class="progress-bar bar-{category}" style="width:{percent}%"></div></div>'
            f'<span class="show-row-text">{done}/{len(show_episodes)} écoutés · {written} fiche{"s" if written > 1 else ""}</span></div>'
        )
    render_html(f'<div class="show-rows">{"".join(rows)}</div>')

    # ---- synthèse des tendances
    section_title("chart", f"Grandes tendances de {label}", "Synthèse transversale politique, économique et géopolitique.")
    configured = ai_engine.is_configured()
    button_label = "Régénérer la synthèse (remplace le texte actuel)" if synthesis else "Générer la synthèse des tendances du mois"
    generate = st.button(button_label, type="secondary" if synthesis else "primary", icon=":material/auto_awesome:",
                         key="generate_synthesis", disabled=not configured)
    if not configured:
        st.caption("Clé Gemini absente : ajoutez `GEMINI_API_KEY` dans `.streamlit/secrets.toml` pour activer la synthèse.")
    else:
        st.caption(f"La synthèse s'appuie sur les {len(episodes)} épisodes du mois : résumés RSS et, quand elles existent, "
                   f"fiches détaillées ({len(fiches)} disponibles).")
    if generate:
        with st.spinner("Analyse des épisodes du mois par Gemini…"):
            try:
                content = ai_engine.generate_monthly_synthesis(label, episodes, model=current_model())
            except ai_engine.AIEngineError as exc:
                st.error(str(exc))
            else:
                db.save_synthesis(month, content)
                st.session_state["synthesis_version"] = st.session_state.get("synthesis_version", 0) + 1
                flash("Synthèse du mois générée.", ":material/auto_awesome:")
                st.rerun()

    if synthesis:
        when = datetime.fromisoformat(synthesis["updated_at"]).strftime("%d/%m/%Y à %Hh%M")
        with st.container(key="synthesis_card"):
            render_html(f'<div class="card-kicker">{icon("sparkles", 14)}Synthèse du mois · mise à jour le {esc(when)}</div>')
            st.markdown(synthesis["content"])
        with st.expander("Modifier le texte de la synthèse", icon=":material/edit:"):
            editor_key = f"synthesis_editor_{month}_{st.session_state.get('synthesis_version', 0)}"
            edited = st.text_area("Synthèse (Markdown)", value=synthesis["content"], height=360, key=editor_key,
                                  label_visibility="collapsed")
            if st.button("Enregistrer la synthèse", icon=":material/save:", key="save_synthesis",
                         disabled=not edited.strip() or edited.strip() == synthesis["content"]):
                db.save_synthesis(month, edited)
                flash("Synthèse enregistrée.")
                st.rerun()
    else:
        render_html('<div class="callout">Aucune synthèse pour ce mois pour l\'instant.</div>')

    render_exports(month, episodes, shows, synthesis)


def render_exports(month: str, episodes: list[dict[str, Any]], shows: list[dict[str, Any]],
                   synthesis: dict[str, Any] | None) -> None:
    label = exporter.month_label(month)
    section_title("download", "Exports", "Documents Word ou PDF mis en page, prêts à imprimer ou à annoter.")
    with st.container(key="export_card"):
        options_col, format_col = st.columns([3, 1], gap="large")
        kind = options_col.radio("Contenu du document", list(EXPORT_LABELS), format_func=EXPORT_LABELS.get, key="export_kind")
        file_format = format_col.radio("Format", ["docx", "pdf"], key="export_format",
                                       format_func={"docx": "Word (.docx)", "pdf": "PDF (.pdf)"}.get)

        document: exporter.ExportDocument | None = None
        if kind == EXPORT_SINGLE:
            with_fiche = [ep for ep in reversed(episodes) if (ep["fiche"] or "").strip()]
            if not with_fiche:
                st.info(f"Aucune fiche enregistrée en {label}. Rédigez-en une dans l'atelier de fichage.")
            else:
                by_id = {ep["id"]: ep for ep in with_fiche}
                sanitize_choice("export_episode", list(by_id))
                chosen = st.selectbox(
                    "Édito à exporter",
                    list(by_id),
                    format_func=lambda episode_id: (
                        f"{date.fromisoformat(by_id[episode_id]['pub_date']).strftime('%d/%m')} · "
                        f"{by_id[episode_id]['show_title']} · {by_id[episode_id]['title']}"
                    ),
                    key="export_episode",
                )
                document = exporter.single_fiche_document(by_id[chosen])
        else:
            show_ids = [show["id"] for show in shows if any(ep["show_id"] == show["id"] for ep in episodes)]
            titles = {show["id"]: show_name(show) for show in shows}
            choice_col, priority_col = st.columns(2)
            show_id = None
            if kind == EXPORT_CATEGORY:
                sanitize_choice("export_show", show_ids)
                show_id = choice_col.selectbox("Émission", show_ids, format_func=titles.get, key="export_show")
            minimum = (priority_col if kind == EXPORT_CATEGORY else choice_col).selectbox("Épisodes retenus", list(MIN_PRIORITY_LABELS),
                                             format_func=MIN_PRIORITY_LABELS.get, key="export_min_priority")
            include_unfiched = st.checkbox(
                "Inclure aussi les épisodes prioritaires sans fiche (résumé RSS seul)", key="export_include_unfiched"
            )
            pool = [ep for ep in episodes if ep["priority"] >= minimum and (show_id is None or ep["show_id"] == show_id)]
            fiched = [ep for ep in pool if (ep["fiche"] or "").strip()]
            selection = pool if include_unfiched else fiched
            missing = len(pool) - len(fiched)
            if kind == EXPORT_DOSSIER and not synthesis:
                st.warning("La synthèse mensuelle n'a pas encore été générée : le dossier sera produit sans elle. "
                           "Générez-la ci-dessus pour l'inclure.")
            if not selection:
                st.info(
                    f"Aucune fiche à exporter : {len(pool)} épisode{'s' if len(pool) > 1 else ''} "
                    f"correspond{'ent' if len(pool) > 1 else ''} à ce niveau de priorité en {label}, "
                    f"dont {len(fiched)} avec une fiche enregistrée."
                )
            else:
                details = f"{len(fiched)} fiche{'s' if len(fiched) > 1 else ''}"
                if include_unfiched and missing:
                    details += f" et {plural(missing, 'épisode')} sans fiche"
                elif missing:
                    details += f" ({plural(missing, 'épisode')} sans fiche non inclus)"
                st.caption(f"Le document contiendra {details}.")
                if kind == EXPORT_CATEGORY:
                    document = exporter.category_document(titles[show_id], month, selection)
                else:
                    document = exporter.dossier_document(month, selection, synthesis["content"] if synthesis else None)

        if document is not None:
            payload = json.dumps(dataclasses.asdict(document), ensure_ascii=False, sort_keys=True)
            data = _build_export(file_format, payload)
            st.download_button(
                f"Télécharger le {'document Word' if file_format == 'docx' else 'PDF'}",
                data=data,
                file_name=f"{document.filename_stem}.{file_format}",
                mime=exporter.DOCX_MIME if file_format == "docx" else exporter.PDF_MIME,
                type="primary",
                icon=":material/download:",
                key="export_download",
            )


# -------------------------------------------------------------- onglet 4 : paramètres


def _save_logo(show: dict[str, Any], uploaded: Any) -> None:
    try:
        with Image.open(uploaded) as image:
            image = image.convert("RGBA")
            image.thumbnail((600, 600))
            ASSETS_DIR.mkdir(exist_ok=True)
            filename = f"show_{show['id']}.png"
            image.save(ASSETS_DIR / filename, format="PNG")
    except (OSError, UnidentifiedImageError):
        flash("Image illisible : utilisez un fichier PNG, JPEG ou WebP.", ":material/error:")
        return
    db.update_show(show["id"], custom_logo=filename)
    flash(f"Image de couverture mise à jour pour « {show_name(show)} ».", ":material/image:")


def _remove_logo(show: dict[str, Any]) -> None:
    if show["custom_logo"]:
        (ASSETS_DIR / show["custom_logo"]).unlink(missing_ok=True)
    db.update_show(show["id"], custom_logo=None)


def _on_toggle_show(show_id: int, key: str) -> None:
    enabled = bool(st.session_state[key])
    db.update_show(show_id, enabled=int(enabled))
    if enabled:
        st.session_state["pending_sync"] = show_id


def render_show_settings(show: dict[str, Any]) -> None:
    category = category_of(show)
    counts = db.show_counts(show["id"])
    if show["last_error"]:
        status = f'<span class="status status-error">Dernière synchronisation en échec : {esc(show["last_error"])}</span>'
    elif show["last_synced_at"]:
        when = datetime.fromisoformat(show["last_synced_at"]).strftime("%d/%m/%Y à %Hh%M")
        status = f'<span class="status">Synchronisée le {esc(when)} · {plural(counts["episodes"], "épisode")} · {plural(counts["fiches"], "fiche")}</span>'
    else:
        status = '<span class="status">Jamais synchronisée</span>'

    with st.container(key=f"settings_{category}_{show['id']}"):
        head_col, toggle_col = st.columns([4, 1.4], vertical_alignment="center")
        render_html(
            f"""
            <div class="ep-head">
              {thumb_html(show, "ep-thumb large")}
              <div class="ep-headtext">
                <div class="ep-badges">{badge(CATEGORY_LABELS[category], category)}</div>
                <div class="ws-title">{esc(show_name(show))}</div>
                {status}
              </div>
            </div>
            """,
            head_col,
        )
        toggle_key = f"enabled_{show['id']}"
        toggle_col.toggle("Suivre", value=bool(show["enabled"]), key=toggle_key, on_change=_on_toggle_show,
                          args=(show["id"], toggle_key))

        with st.form(f"show_form_{show['id']}", border=False):
            url_col, category_col = st.columns([3, 1.2])
            url = url_col.text_input("URL du flux RSS", value=show["rss_url"], key=f"url_{show['id']}")
            options = list(db.CATEGORIES)
            new_category = category_col.selectbox("Badge", options, index=options.index(category),
                                                  format_func=CATEGORY_LABELS.get, key=f"category_{show['id']}")
            submitted = st.form_submit_button("Enregistrer", icon=":material/save:")
        if submitted:
            _update_show(show, url.strip(), new_category)

        nonce = st.session_state.get(f"logo_nonce_{show['id']}", 0)
        upload_col, remove_col = st.columns([3, 1.2], vertical_alignment="bottom")
        uploaded = upload_col.file_uploader("Image de couverture personnalisée", type=["png", "jpg", "jpeg", "webp"],
                                            key=f"logo_{show['id']}_{nonce}", max_upload_size=5)
        if uploaded is not None:
            _save_logo(show, uploaded)
            st.session_state[f"logo_nonce_{show['id']}"] = nonce + 1
            st.rerun()
        if show["custom_logo"] and remove_col.button("Retirer l'image", icon=":material/hide_image:",
                                                     key=f"remove_logo_{show['id']}", width="stretch"):
            _remove_logo(show)
            st.rerun()

        with st.popover("Supprimer cette émission", icon=":material/delete:"):
            st.write(
                f"La suppression efface aussi les épisodes de cette émission ({counts['episodes']}) "
                f"et ses fiches ({counts['fiches']}). "
                "Pour la masquer sans rien perdre, désactivez simplement « Suivre »."
            )
            if st.button("Supprimer définitivement", type="primary", key=f"delete_show_{show['id']}"):
                _remove_logo(show)
                db.delete_show(show["id"])
                flash(f"Émission « {show_name(show)} » supprimée.", ":material/delete:")
                st.rerun()


def _update_show(show: dict[str, Any], url: str, category: str) -> None:
    if not safe_url(url):
        st.error("L'URL doit commencer par http:// ou https://.")
        return
    if url == show["rss_url"]:
        db.update_show(show["id"], category=category)
        flash("Émission mise à jour.")
        st.rerun()
    try:
        with st.spinner("Vérification du nouveau flux…"):
            rss_fetcher.fetch_feed(url)
        db.update_show(show["id"], rss_url=url, category=category)
    except rss_fetcher.FeedError as exc:
        st.error(f"URL non enregistrée. {exc}")
        return
    except sqlite3.IntegrityError:
        st.error("Ce flux est déjà suivi par une autre émission.")
        return
    updated = db.get_show(show["id"])
    if updated and updated["enabled"]:
        run_sync([updated])
    else:
        flash("Flux mis à jour.")
    st.rerun()


def _reset_single_lookup() -> None:
    st.session_state.pop("single_lookup", None)
    st.session_state["single_url_nonce"] = st.session_state.get("single_url_nonce", 0) + 1


def _confirm_single_episode(found: dict[str, Any]) -> None:
    """Aperçu de l'épisode trouvé, champs corrigeables, puis enregistrement."""
    nonce = st.session_state.get("single_nonce", 0)
    episodes = found["episodes"]
    index = 0
    if found["from_feed"]:
        index = st.selectbox(
            f"Épisode à ajouter · {plural(len(episodes), 'épisode')} dans le flux « {found['show_title']} »",
            range(len(episodes)),
            format_func=lambda i: f"{date.fromisoformat(episodes[i]['pub_date']).strftime('%d/%m/%Y')} · {episodes[i]['title']}",
            key=f"single_pick_{nonce}",
        )
    candidate = episodes[index]

    existing = db.find_episode_by_link(candidate["guid"])
    if existing:
        st.info(
            f"Cet épisode est déjà dans votre suivi : « {existing['title']} » "
            f"({existing['show_title']}, {exporter.format_date_fr(existing['pub_date'])}).",
            icon=":material/info:",
        )
        open_col, cancel_col, _ = st.columns([1.6, 1, 2.4])
        open_col.button("Ouvrir dans l'atelier", icon=":material/edit_note:", key="single_open_existing",
                        on_click=open_in_atelier, args=(existing["id"],), width="stretch")
        cancel_col.button("Fermer", key="single_close", on_click=_reset_single_lookup, width="stretch")
        return

    category = rss_fetcher.guess_category(found["show_title"])
    preview = {**candidate, "show_category": category}
    meta = " · ".join(
        part
        for part in (
            exporter.format_date_fr(candidate["pub_date"]) if candidate["pub_date"] else "",
            time_label(candidate["published_at"]),
            duration_label(candidate["duration"]),
            candidate["author"],
        )
        if part
    )
    summary = f'<div class="ep-summary">{esc(candidate["summary"])}</div>' if candidate["summary"] else ""
    render_html(
        f"""
        <div class="single-preview">
          <div class="ep-head">
            {thumb_html(preview, "ep-thumb large")}
            <div class="ep-headtext">
              <div class="ep-badges">{badge(found["show_title"] or "Podcast", category)}</div>
              <div class="ws-title">{esc(candidate["title"])}</div>
              <div class="ep-meta">{esc(meta)}</div>
            </div>
          </div>
          {summary}
        </div>
        """
    )
    if safe_url(candidate["audio_url"]):
        st.audio(candidate["audio_url"])
    else:
        st.caption(
            "Aucun fichier audio n'a été trouvé sur cette page. Vérifiez qu'il s'agit bien de la page d'un épisode ; "
            "vous pouvez aussi coller le lien du fichier audio ci-dessous."
        )

    options = list(db.CATEGORIES)
    with st.form(f"single_form_{nonce}_{index}", border=False):
        title_col, show_col = st.columns(2)
        title = title_col.text_input("Titre", value=candidate["title"])
        show = show_col.text_input("Émission ou podcast", value=found["show_title"])
        date_col, category_col, audio_col = st.columns([1.2, 1.2, 2.6])
        day = date_col.date_input(
            "Date de diffusion",
            value=date.fromisoformat(candidate["pub_date"]) if candidate["pub_date"] else None,
            format="DD/MM/YYYY",
        )
        chosen_category = category_col.selectbox("Badge", options, index=options.index(category),
                                                 format_func=CATEGORY_LABELS.get)
        audio_url = audio_col.text_input("Lien du fichier audio (facultatif)", value=candidate["audio_url"] or "")
        add_col, cancel_col, _ = st.columns([1.6, 1, 2.4])
        add = add_col.form_submit_button("Ajouter cet épisode", type="primary", icon=":material/add:", width="stretch")
        cancel = cancel_col.form_submit_button("Annuler", width="stretch")

    if cancel:
        _reset_single_lookup()
        st.rerun()
    if not add:
        return
    title, show, audio_url = title.strip(), show.strip(), audio_url.strip()
    if not title or not show:
        st.error("Le titre et le nom de l'émission sont obligatoires.")
    elif day is None:
        st.error("Indiquez la date de diffusion : elle n'a pas été trouvée sur la page.")
    elif audio_url and not safe_url(audio_url):
        st.error("Le lien du fichier audio doit commencer par http:// ou https://.")
    else:
        same_audio = audio_url == (candidate["audio_url"] or "")
        episode = {
            **candidate,
            "title": title,
            "pub_date": day.isoformat(),
            # L'heure de diffusion ne vaut que pour la date trouvée sur la page.
            "published_at": candidate["published_at"] if day.isoformat() == candidate["pub_date"] else day.isoformat(),
            "audio_url": audio_url or None,
            "audio_type": candidate["audio_type"] if same_audio else None,
            "duration": candidate["duration"] if same_audio else None,
        }
        try:
            db.add_single_episode(episode, show, chosen_category)
        except sqlite3.IntegrityError:
            st.error("Cet épisode a déjà été ajouté.")
        else:
            _reset_single_lookup()
            flash(f"Épisode ajouté : il apparaît dans le suivi de {exporter.month_label(episode['pub_date'][:7])}.",
                  ":material/playlist_add_check:")
            st.rerun()


def render_single_episodes() -> None:
    """Ajout d'un épisode isolé d'un autre podcast, puis liste des épisodes déjà ajoutés ainsi."""
    section_title("mic", "Ajouter un seul épisode", "Un épisode d'un autre podcast, sans suivre tout son flux RSS.")
    with st.container(key="add_episode_card"):
        with st.form("lookup_episode", border=False):
            url_col, button_col = st.columns([3, 1.2], vertical_alignment="bottom")
            url = url_col.text_input(
                "Adresse de la page de l'épisode",
                placeholder="https://www.radiofrance.fr/franceculture/podcasts/…",
                key=f"single_url_{st.session_state.get('single_url_nonce', 0)}",
            )
            search = button_col.form_submit_button("Rechercher l'épisode", icon=":material/search:", width="stretch")
        st.caption(
            "Collez l'adresse de la page de l'épisode, sur radiofrance.fr ou un autre site. L'adresse d'un flux RSS "
            "convient aussi : vous y choisirez l'épisode voulu, sans que le reste du flux soit ajouté."
        )
        if search:
            try:
                with st.spinner("Lecture de la page…"):
                    found = episode_fetcher.lookup(url)
            except episode_fetcher.EpisodeError as exc:
                st.session_state.pop("single_lookup", None)
                st.error(str(exc))
            else:
                st.session_state["single_lookup"] = dataclasses.asdict(found)
                st.session_state["single_nonce"] = st.session_state.get("single_nonce", 0) + 1
        if st.session_state.get("single_lookup"):
            _confirm_single_episode(st.session_state["single_lookup"])

    singles = db.list_single_episodes()
    if not singles:
        return
    render_html(f'<div class="list-caption singles-caption">{plural(len(singles), "épisode ajouté", "épisodes ajoutés")} à l\'unité</div>')
    for ep in singles:
        category = category_of(ep)
        fiche_chip = f'<span class="chip chip-fiche">{icon("file", 12)}Fiche</span>' if (ep["fiche"] or "").strip() else ""
        with st.container(key=f"singlerow_{category}_{ep['id']}"):
            info_col, buttons_col = st.columns([5, 2.4], vertical_alignment="center")
            buttons = buttons_col.container(horizontal=True, horizontal_alignment="right")
            render_html(
                f"""
                <div class="ep-head">
                  {thumb_html(ep)}
                  <div class="ep-headtext">
                    <div class="ep-badges">{badge(ep["show_title"] or "Podcast", category)}{fiche_chip}
                      <span class="ep-meta">{esc(exporter.format_date_fr(ep["pub_date"]))}</span></div>
                    <div class="single-title">{esc(ep["title"])}</div>
                  </div>
                </div>
                """,
                info_col,
            )
            buttons.button("Ficher", icon=":material/edit_note:", key=f"single_open_{ep['id']}",
                           help="Ouvrir cet épisode dans l'atelier de fichage",
                           on_click=open_in_atelier, args=(ep["id"],))
            with buttons.popover("Retirer", icon=":material/delete:"):
                st.write(
                    "Retirer cet épisode du suivi ?"
                    + (" Sa fiche sera supprimée avec lui." if (ep["fiche"] or ep["fiche_draft"] or "").strip() else "")
                )
                if st.button("Oui, retirer l'épisode", type="primary", key=f"single_remove_{ep['id']}"):
                    db.delete_single_episode(ep["id"])
                    flash("Épisode retiré du suivi.", ":material/delete:")
                    st.rerun()


def _render_persistence_status() -> None:
    message = persistence.status_message()
    if not message:
        return
    text, tone = message
    if tone == "error":
        st.error(text, icon=":material/cloud_off:")
    elif tone == "warning":
        st.warning(text, icon=":material/warning:")
    else:
        render_html(f'<div class="callout callout-saved">{icon("check")}<span>{esc(text)}</span></div>')


def render_manual_backup() -> None:
    """Export / import d'une archive pour Streamlit Cloud ou copie ponctuelle."""
    cloud = persistence.running_on_streamlit_cloud()
    hint = (
        "Avant de fermer l'onglet ou après une session sur Streamlit Cloud : téléchargez l'archive et "
        "déposez-la dans Google Drive. Au réveil de l'app, réimportez le même fichier."
        if cloud
        else "Copie complète de votre base et des images de couverture (identique au fichier synchronisé sur Drive si vous l'avez configuré)."
    )
    section_title("download", "Copie de sécurité", hint)
    with st.container(key="manual_backup_card"):
        down_col, up_col = st.columns(2, gap="large")
        with down_col:
            st.caption("Téléchargement")
            if st.button("Préparer la sauvegarde", icon=":material/folder_zip:", key="prep_backup", type="primary"):
                with st.spinner("Création de l'archive…"):
                    st.session_state["manual_backup_blob"] = persistence.export_bundle_bytes()
            blob = st.session_state.get("manual_backup_blob")
            if blob:
                st.download_button(
                    "Télécharger mes_editos_backup.tar.gz",
                    data=blob,
                    file_name="mes_editos_backup.tar.gz",
                    mime="application/gzip",
                    icon=":material/download:",
                    type="primary",
                    key="download_backup",
                )
        with up_col:
            st.caption("Restauration (remplace les données actuelles de l'app)")
            uploaded = st.file_uploader(
                "Fichier .tar.gz précédemment téléchargé",
                type=["gz"],
                key="restore_backup_upload",
                label_visibility="collapsed",
                max_upload_size=50,
            )
            if uploaded is not None:
                st.caption(f"{uploaded.name} · {uploaded.size / 1024:.1f} Ko")
            if st.button(
                "Restaurer cette sauvegarde",
                icon=":material/restore:",
                key="restore_backup_btn",
                disabled=uploaded is None,
                type="secondary",
            ):
                try:
                    persistence.import_bundle_bytes(uploaded.getvalue())
                except persistence.BackupImportError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.pop("manual_backup_blob", None)
                    flash("Sauvegarde restaurée. Vos fiches et flux sont de nouveau disponibles.", ":material/restore:")
                    st.rerun()


def render_parametres() -> None:
    _render_persistence_status()
    render_manual_backup()
    pending = st.session_state.pop("pending_sync", None)
    if pending is not None:
        show = db.get_show(pending)
        if show:
            run_sync([show])

    shows = db.list_shows(feeds_only=True)
    section_title("rss", "Émissions suivies", "Le nom de chaque émission est lu dans le <title> de son flux RSS.")
    with st.container(key="shows_grid"):
        columns = st.columns(2, gap="medium")
    for index, show in enumerate(shows):
        with columns[index % 2]:
            render_show_settings(show)

    section_title("rss", "Ajouter une émission", "Collez l'adresse d'un flux RSS de podcast.")
    with st.container(key="add_show_card"):
        with st.form("add_show", border=False, clear_on_submit=True):
            url_col, category_col = st.columns([3, 1.2])
            new_url = url_col.text_input("URL du flux RSS", placeholder="https://radiofrance-podcast.net/podcast09/rss_….xml")
            options = ["auto", *db.CATEGORIES]
            new_category = category_col.selectbox(
                "Badge", options, format_func=lambda value: "Détection automatique" if value == "auto" else CATEGORY_LABELS[value]
            )
            add = st.form_submit_button("Ajouter et synchroniser", type="primary", icon=":material/add:")
        if add:
            new_url = new_url.strip()
            if not safe_url(new_url):
                st.error("L'URL doit commencer par http:// ou https://.")
            else:
                try:
                    with st.spinner("Lecture du flux…"):
                        feed = rss_fetcher.fetch_feed(new_url)
                    show_id = db.add_show(
                        new_url,
                        title=feed.title,
                        category=None if new_category == "auto" else new_category,
                    )
                except rss_fetcher.FeedError as exc:
                    st.error(str(exc))
                except sqlite3.IntegrityError:
                    st.error("Ce flux est déjà dans la liste des émissions.")
                else:
                    run_sync([db.get_show(show_id)])
                    st.rerun()

    render_single_episodes()

    section_title("rss", "Synchronisation", "Les flux sont relevés automatiquement à l'ouverture, au plus une fois par heure.")
    with st.container(key="sync_card"):
        if st.button("Forcer la synchronisation des flux", type="primary", icon=":material/sync:", key="force_sync"):
            run_sync()
            st.rerun()
        reports = st.session_state.get("sync_reports")
        if reports:
            lines = []
            for report in reports:
                if report["ok"]:
                    sundays = (f" · {report['skipped_sundays']} épisode{'s' if report['skipped_sundays'] > 1 else ''} "
                               "du dimanche écarté" + ("s" if report["skipped_sundays"] > 1 else "")) if report["skipped_sundays"] else ""
                    detail = f"{report['added']} ajouté{'s' if report['added'] > 1 else ''} · {report['known']} déjà connus{sundays}"
                    lines.append(f'<div class="sync-line"><span class="dot dot-ok"></span><b>{esc(report["label"])}</b><span>{detail}</span></div>')
                else:
                    lines.append(f'<div class="sync-line"><span class="dot dot-error"></span><b>{esc(report["label"])}</b>'
                                 f'<span>{esc(report["error"])}</span></div>')
            render_html(f'<div class="sync-report"><div class="card-kicker">Dernier relevé · {esc(st.session_state.get("sync_time"))}</div>'
                    f'{"".join(lines)}</div>')

    section_title("sparkles", "Intelligence artificielle", "Fiches et synthèses sont produites par Gemini.")
    with st.container(key="ai_card"):
        if ai_engine.is_configured():
            render_html(f'<div class="callout callout-saved">{icon("check")}<span>Clé Gemini détectée dans les secrets Streamlit.</span></div>')
        else:
            render_html(f'<div class="callout callout-draft">{icon("sparkles")}<span><b>Clé Gemini absente.</b> Créez le fichier '
                    "<code>.streamlit/secrets.toml</code> avec la ligne <code>GEMINI_API_KEY = \"votre-clé\"</code>, "
                    "puis relancez l'application.</span></div>")
        model = current_model()
        choices = list(ai_engine.MODEL_CHOICES)
        if model not in choices:
            choices.insert(0, model)
        chosen = st.selectbox("Modèle Gemini", choices, index=choices.index(model), accept_new_options=True,
                              help="Par défaut gemini-3.5-flash-lite. En cas d'erreur 503 prolongée, essayez un autre identifiant.",
                              width=420)
        if chosen and chosen != model:
            db.set_setting("gemini_model", chosen.strip())
            flash(f"Modèle Gemini : {chosen.strip()}.")
            st.rerun()
        source = (db.get_setting("fiche_source") or "transcript").strip().lower()
        source_choice = st.radio(
            "Source pour générer les fiches",
            options=("transcript", "audio"),
            index=1 if source == "audio" else 0,
            format_func=lambda value: (
                "Retranscription Radio France (recommandé, rapide)"
                if value == "transcript"
                else "Audio intégral (lent, multimodal)"
            ),
            help="La retranscription est celle affichée sur la page de l'épisode ; l'audio n'est plus nécessaire par défaut.",
        )
        if source_choice != source:
            db.set_setting("fiche_source", source_choice)
            flash("Source des fiches mise à jour.")
            st.rerun()


# ------------------------------------------------------------------------------ main


def main() -> None:
    st.set_page_config(
        page_title="Mes éditos du matin · Carl PETERSEN",
        page_icon=":material/radio:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.html(STYLES_PATH)
    persistence.restore_if_configured()
    db.init_db()
    ASSETS_DIR.mkdir(exist_ok=True)
    keep_widget_state()
    auto_sync()
    show_flashes()
    render_masthead()

    renderers = {
        TAB_SUIVI: render_suivi,
        TAB_ATELIER: render_atelier,
        TAB_BILAN: render_bilan,
        TAB_PARAMS: render_parametres,
    }
    tabs = st.tabs(list(renderers), key="main_tabs", on_change="rerun")
    for tab, render in zip(tabs, renderers.values()):
        # Seul l'onglet ouvert est calculé ; `open` vaut None si le suivi d'état est indisponible.
        if tab.open is not False:
            with tab:
                render()
    show_flashes()
    persistence.ensure_backup()
    persistence.sync_if_dirty()


if __name__ == "__main__":
    main()
