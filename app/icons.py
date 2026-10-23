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
    #icon buttons (row and card buttons, the folder tools: the owner, 2026-10-14): Lucide's
    #drawings, lucide.dev, ISC license; each button keeps its words for screen readers and in its
    #tooltip (icon_label below)
    #View (named lc-eye from when it was an eye): a magnifier everywhere, the owner 2026-10-15
    'lc-eye': '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'lc-pencil': '<path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/><path d="m15 5 4 4"/>',
    'lc-history': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    'lc-trash': '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    'lc-list-plus': '<path d="M11 12H3"/><path d="M16 6H3"/><path d="M16 18H3"/><path d="M18 9v6"/><path d="M21 12h-6"/>',
    'lc-arrow-left': '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    'lc-arrow-right': '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    'lc-copy': '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    'lc-folder-plus': '<path d="M12 10v6"/><path d="M9 13h6"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    'lc-folder-minus': '<path d="M9 13h6"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    'lc-folder-check': '<path d="m9 13 2 2 4-4"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',  # the Checked folder (the owner, 2026-10-21)
    'lc-folder-input': '<path d="M2 9V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-1.73"/><path d="M2 13h10"/><path d="m9 16 3-3-3-3"/>',
    'lc-send': '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    'lc-expand': '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
    'lc-collapse': '<path d="m7 20 5-5 5 5"/><path d="m7 4 5 5 5-5"/>',
    'lc-folder-up': '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/><path d="M12 10v6"/><path d="m9 13 3-3 3 3"/>',
    'lc-pin-off': '<path d="M12 17v5"/><path d="M15 9.34V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H7.89"/><path d="m2 2 20 20"/><path d="M9 9v1.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h11"/>',
    'lc-message': '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    'lc-play': '<path d="M6 3l14 9-14 9z"/>',
    #(scans: Pause and Resume, and a scan that stopped on a page that couldn't be read: the owner, 2026-10-19)
    'lc-clipboard-check': '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    'lc-pause': '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    'lc-resume': '<circle cx="12" cy="12" r="10"/><path d="M10 8l6 4-6 4z"/>',
    'lc-alert': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    'lc-grade': '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    'lc-answer-key': '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/><path d="m9 9.5 2 2 4-4"/>',
    'lc-archive': '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
    'lc-archive-all': '<rect width="16" height="3" x="4" y="1.5" rx="1"/><rect width="20" height="5" x="2" y="6" rx="1"/><path d="M4 11v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9"/><path d="M10 15h4"/>',
    'lc-retake': '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    'lc-activity': '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    'lc-user': '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    #(who gets a problem in a quiz: everyone or a group's random pick; the owner, 2026-10-22)
    'lc-users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    'lc-key': '<path d="M2.59 17.41A2 2 0 0 0 2 18.83V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.17a2 2 0 0 0 1.42-.59l.81-.81a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5"/>',
    'lc-image-minus': '<path d="M21 9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"/><path d="M16 5h6"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    'lc-restore': '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    'lc-check': '<path d="M20 6 9 17l-5-5"/>',
    #(Check all shown / Uncheck all as a pair of bare icons, a checked box and an empty one: the owner, 2026-10-22)
    'lc-check-all': '<path d="M21 10.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12.5"/><path d="m9 11 3 3L22 4"/>',
    'lc-check-none': '<rect width="18" height="18" x="3" y="3" rx="2"/>',
    'lc-x': '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    'lc-eraser': '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
    'lc-printer': '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
    'lc-folder-open': '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    'lc-folder-cog': '<path d="M10.3 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.98a2 2 0 0 1 1.69.9l.66 1.2A2 2 0 0 0 12 6h8a2 2 0 0 1 2 2v3.3"/><circle cx="18" cy="18" r="3"/><path d="M18 14v1"/><path d="M18 21v1"/><path d="M22 18h-1"/><path d="M15 18h-1"/><path d="m21 15-.88.88"/><path d="M15.88 20.12 15 21"/><path d="m21 21-.88-.88"/><path d="M15.88 15.88 15 15"/>',
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


#drawn in full each time: the page's styles color their parts (a <use> copy can't be styled inside)
INLINE = {k for k, v in PATHS.items() if 'class=' in v}


def svg(name, cls=None):
    """The drawing named name, as markup (decorative: screen readers skip it): a small <use> of
    the page's one copy of it (icon_sprite in base.html), so a page with many icons stays light
    (the Problems page: 1,600 icons; the owner, 2026-10-20)."""
    inside = PATHS[name] if name in INLINE else '<use href="#i-{}"/>'.format(name)
    return Markup('<svg class="ico{}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{}</svg>'.format(
        ' ' + escape(cls) if cls else '', inside))


def icon_sprite():
    """Every drawing once, hidden, at the top of each page, for svg()'s <use> copies."""
    return Markup('<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
                  + ''.join('<symbol id="i-{}" viewBox="0 0 24 24">{}</symbol>'.format(k, v) for k, v in PATHS.items() if k not in INLINE)
                  + '</defs></svg>')


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
FOR_SCRIPTS = ('calendar', 'folder', 'folders', 'tray', 'sparkle', 'pencil', 'bulb', 'picture', 'user', 'pin')
#(the icon buttons' drawings: scripts build some of those buttons too)
FOR_SCRIPTS = FOR_SCRIPTS + tuple(k for k in PATHS if k.startswith('lc-'))


#which buttons are icon buttons, by their words (the owner, 2026-10-14)
BUTTON_ICONS = {'View': 'lc-eye', 'Edit': 'lc-pencil', 'History': 'lc-history', 'Remove': 'lc-trash', 'Assign': 'lc-send',
                'Expand all': 'lc-expand', 'Collapse all': 'lc-collapse', 'Open this folder': 'lc-folder-open',
                'Folder options': 'lc-folder-cog', 'Unpin': 'lc-pin-off', 'Message': 'lc-message', 'Start': 'lc-play', 'Continue': 'lc-play',
                'Grade': 'lc-grade', 'Answer key': 'lc-answer-key', 'Archive': 'lc-trash', 'Retake': 'lc-retake',
                'Student page': 'lc-user', 'Reset password': 'lc-key', 'Remove picture': 'lc-image-minus', 'Restore': 'lc-restore',
                'View quiz': 'lc-eye', 'Edit quiz': 'lc-pencil', 'View problem': 'lc-eye', 'Edit problem': 'lc-pencil', 'Add to a quiz': 'lc-list-plus'}


def icon_label(name, label):
    """An icon button's inside: the drawing, named with its words for screen readers (the button's
    tooltip starts with the same words). {{ icon_label('lc-eye', 'View') }}
    (The words on the drawing itself, not in a hidden <span> beside it: one element fewer per
    icon, 2,300 on the Problems page; the owner, 2026-10-21.)"""
    if name not in PATHS:
        raise KeyError('no icon named {!r}'.format(name))
    inside = PATHS[name] if name in INLINE else '<use href="#i-{}"/>'.format(name)
    return Markup('<svg class="ico" viewBox="0 0 24 24" role="img" aria-label="{}" focusable="false">{}</svg>').format(label, Markup(inside))


def icon_script():
    """<script> giving page scripts window.qgenIcon(name), for the icons in FOR_SCRIPTS."""
    data = json.dumps({k: str(svg(k)) for k in FOR_SCRIPTS}).replace('</', '<\\/')
    return Markup('<script>window.qgenIcon = (function (all) { return function (name) { return all[name] || \'\'; }; })('
                  + data + ');'
                  #a button a script builds as an icon button: the drawing, its words for screen
                  #readers, its tooltip starting with them (as icon_label() does in templates)
                  'window.qgenIconButton = function (b, name, words, more) {'
                  ' b.innerHTML = window.qgenIcon(name) + \'<span class="sr-only"></span>\';'
                  ' b.lastChild.textContent = words; b.classList.add(\'btn-icon\');'
                  ' b.title = more ? words + \': \' + more : words; };'
                  '</script>')
