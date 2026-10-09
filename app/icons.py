"""The site's icons: one set of simple line drawings (24 by 24, drawn in the text's own
color, so they follow light and dark mode), instead of emoji, which every device draws its
own way. The teacher chose these over emoji on 2026-10-09.

In a template: {{ icon('folder') }}. The heading macro box_label takes a name too. Scripts
that build icons themselves get them from window.qgenIcon(name) (icon_script() in base.html).
Places that can't hold a drawing (a menu's choices, a tooltip, the tab's title) use words.
"""
import json

from markupsafe import Markup, escape

PATHS = {
    'folder': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'tray': '<path d="M3 13h5l2 3h4l2-3h5"/><path d="M5.5 5h13l2.5 8v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5z"/>',
    'folders': '<path d="M6 6V5a1 1 0 0 1 1-1h3l2 2h6a2 2 0 0 1 2 2v1"/>'
               '<path d="M3 11a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'sparkle': '<path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/>'
               '<path d="M18.5 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
    'pencil': '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4"/>',
    'note': '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h5"/>',
    'file': '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4"/>',
    'pin': '<path d="M9 3h6l-1 6 3 3H7l3-3z"/><path d="M12 15v6"/>',
    'printer': '<path d="M7 9V3h10v6"/><path d="M7 18H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
               '<path d="M7 14h10v7H7z"/>',
    'user': '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    'users': '<circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0 1 14 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 13.5a7 7 0 0 1 4 6.5"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    'bell': '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    'lock': '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    'stopwatch': '<circle cx="12" cy="13" r="8"/><path d="M12 13V9M10 2h4M12 2v3"/>',
    'calculator': '<rect x="5" y="3" width="14" height="18" rx="2"/>'
                  '<path d="M8 7h8v3H8zM8.5 14h.01M12 14h.01M15.5 14h.01M8.5 17.5h.01M12 17.5h.01M15.5 17.5h.01"/>',
    'alarm': '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M4 5l3-2.5M20 5l-3-2.5"/>',
    'chat': '<path d="M4 5h16v11H9l-5 4z"/>',
    'warning': '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    'hourglass': '<path d="M6 3h12M6 21h12M7 3v3l5 6 5-6V3M7 21v-3l5-6 5 6v3"/>',
    'chart': '<path d="M4 20V10M10 20V4M16 20v-7M2 20h20"/>',
    'bulb': '<path d="M9 18h6M10 21h4"/>'
            '<path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
    'checkbox': '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 12l3 3 5-6"/>',
    'picture': '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
    'camera': '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/>'
              '<circle cx="12" cy="13" r="3.5"/>',
    'books': '<path d="M4 4h4v16H4zM10 4h4v16h-4zM15.5 5.2l3.4-.9 3.6 14.6-3.4.9z"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
    'archive': '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4"/>',
    'outbox': '<path d="M3 14h5l2 3h4l2-3h5v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 3v9M8 7l4-4 4 4"/>',
    'save': '<path d="M5 3h11l4 4v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M8 3v5h7V3M8 21v-7h8v7"/>',
    'key': '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>',
    'gear': '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="7"/>'
            '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    'online': '<circle cx="12" cy="12" r="5" class="ico-fill-ok"/>',
    'party': '<path d="M4 20l4-11 7 7z"/><path d="M14 4v2M19 6l-1.5 1.5M20 11h-2M15 9l2-2"/>',
    'trophy': '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/>'
              '<path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 21h8M9.5 21l1-4h3l1 4"/>',
    'star': '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    'flag': '<path d="M5 21V4h12l-2 4 2 4H5"/>',
    'flame': '<path d="M12 3c1 4 6 6 6 11a6 6 0 0 1-12 0c0-3 2-4 2-7 2 1 3 3 3 4 1-2 1-5 1-8z"/>',
    'rocket': '<path d="M5 15c-1 2-1 4-1 5 1 0 3 0 5-1"/><path d="M9 15l-1-1c1-5 5-10 12-11-1 7-6 11-11 12z"/>'
              '<circle cx="15" cy="9" r="1.5"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
}


def svg(name, cls=None):
    """The drawing named name, as markup (decorative: screen readers skip it)."""
    return Markup('<svg class="ico{}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{}</svg>'.format(
        ' ' + escape(cls) if cls else '', PATHS[name]))


def icon(name, cls=None):
    """{{ icon('folder') }}. An unknown name is an error (tests check every one used)."""
    if name not in PATHS:
        raise KeyError('no icon named {!r}'.format(name))
    return svg(name, cls)


def icon_or(value):
    """For a macro that takes an icon or other markup (box_label: an icon's name, or a
    person's picture): the drawing when it's an icon's name, else value as it is."""
    if isinstance(value, str) and not isinstance(value, Markup) and value in PATHS:
        return svg(value)
    return value


#the ones page scripts draw themselves (calendar.js, folders.js, helper.js, scan_review.js)
FOR_SCRIPTS = ('calendar', 'folder', 'bulb', 'picture')


def icon_script():
    """<script> giving page scripts window.qgenIcon(name), for the icons in FOR_SCRIPTS."""
    data = json.dumps({k: str(svg(k)) for k in FOR_SCRIPTS}).replace('</', '<\\/')
    return Markup('<script>window.qgenIcon = (function (all) { return function (name) { return all[name] || \'\'; }; })('
                  + data + ');</script>')
