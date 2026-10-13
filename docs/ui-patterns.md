# UI patterns

This is the one design pattern for the whole site, agreed with the site owner in October 2026. Every page follows it. When a page doesn't, change the page, not the pattern.

"Bringing pages in line" at the end lists the places that don't follow it yet.

---

## 1. Principles

1. **Compact first.**
   - A page uses no more room than it needs.
   - Before adding a row, put the control on a line that's already there, usually the heading.
   - A long name wraps or is cut short with "…" (full name in the tooltip). It never pushes a button onto a line of its own.
2. **One pattern everywhere.** The same thing has the same name, look and place on every page.
3. **Gray out, never hide.**
   - A control that doesn't apply stays in its place, disabled, with the reason as its tooltip.
   - Use the `slot(label, why)` macro for it.
4. **Things fold.** Lists of things are folded boxes or rows that open to show the rest.
5. **Line things up.**
   - Boxes at one level share column widths.
   - Buttons that take turns in one place have one width.
6. **Say what changed.** Whenever a change removes, hides or moves a control or behavior, tell the site owner: what, where, and what replaces it.

## 2. Page anatomy

### Page head
- Markup: `.page-head` holds the `h1`, an optional `.seg-switch` (People: Accounts | Results), and `.actions` at the right.
- **Order of `.actions`:**
  1. Back (`back_button`, "← Place")
  2. secondary buttons
  3. **one** primary button, last ("+ New quiz", "Assign a quiz")
  4. the page's Expand all / Collapse all, when it has one
- Only one primary (`.btn`) per area.

### Widths
- `container-narrow` (1080px): forms and reading.
- `container` (1600px): most pages.
- `container-wide` (no limit): folder pages.

### Pages with a single card
- Login, register, change password, quiz start and error pages are a `.card.card-narrow` with the `h1` inside, and no page head.

## 3. Folder pages: one pattern for all of them

**These pages use it:**
- Problems
- Quizzes
- People (Accounts and Results)
- Results by quiz
- the Archive
- one student's page
- My quizzes
- Messages
- Assign's Students picker

**Server side:**
- The page uses `folder_tree.kit(...)` and the `_folders.html` macros (`folders_page`, `all_boxes`, `folder_items`).
- The folder tabs are drawn by `static/js/folderfilter.js`.

### Left: the folder list (`details.folder-side`)
- Expand all / Collapse all at the top: they show or hide the folders inside folders. They're always shown, and grayed when no folder has folders inside it.
- **Order, the same on every page:**
  1. **All …**
  2. the automatic folders
  3. the folders
  4. **Uncategorized**
- Each row has a count, shown even when it's 0. An empty folder is faded but still clickable.
- Dots after a folder say what needs attention inside it (`flag_badges`):
  - unread (red)
  - due (red)
  - in progress (blue)
  - new (amber)
- At the bottom: "+ New folder" (where you can make folders) and a one-line hint.
- On an All view, a click in the list chooses that folder in place, without loading a new page.
- On a phone, the list folds away above the contents.

### Top: the heading row (`.folder-title-row`)
- The heading names what's shown.
- On a folder's own page, the heading shows the path: Math › Algebra.
- At the right (`.title-actions`): the page's Expand all / Collapse all, the folder's actions, then **Folder options**. Folder options is a pop-over that closes on a click elsewhere or Esc.
- The page's own Expand all / Collapse all steps aside while a folder tab shows its own pair.

### Folder tabs (file-folder tabs over one list)
- **One list.** Everything is listed once. The tabs narrow the list; they never copy it.
- **Top row:**
  1. **All …** (chosen to begin with)
  2. the automatic folders
  3. the folders
  4. **Uncategorized** (what's in no folder; grayed when everything is in a folder)
- **Every level is laid out the same.** Choosing a folder adds a row under it:
  1. **All in “X”**: chosen while the list shows everything in X.
  2. the folders inside X
  3. **Uncategorized**: what's in X but in none of its folders. It's grayed, with the reason in its tooltip, when X has no folders inside.
- This repeats at every depth. A folder's own page (`?folder=N`) uses the same rows, starting from "All in “X”".
- **Automatic folders appear at the top level only.**
- **The chosen tab's buttons sit at the end of its row, at every level, All included:**
  1. Expand all / Collapse all (grayed when nothing folds)
  2. Open this folder (real folders only)
  3. any folder action, e.g. "Assign a quiz to this folder"
- **How tabs look:**
  - The open tab and its panel share a light accent tint and outline, and the tab has a thick top edge.
  - Closed tabs are dimmed.
  - The open tab in a lower row is filled solid.
  - An empty tab is faded.
  - Counts read "N people" / "N quizzes".
- **Empty tab:** "Nothing in “X” yet." A tab can bring its own words, e.g. "No new quizzes right now."
- **Starting tab:**
  - Every folder page starts on **All** when you come to it.
  - It keeps the chosen tab only when a button on the page reloads it (a move or a drop).
  - An address can ask for a tab, e.g. `My quizzes?folder=new` from Home.
- **Phones:** the tabs scroll sideways inside their strip, whose right edge fades out.
- **Drag and drop:** a tab takes a drop like the folder list does (`data-drop`).

### Names of the "All" tab: "All" plus the things
| Page | All | Automatic folders |
|---|---|---|
| Problems | All problems | none |
| Quizzes, Results by quiz | All quizzes | none |
| People | All people | none |
| Archive | All attempts | the student folders (one per student, made automatically) |
| Messages | All students | none |
| Assign: Students | All people | none |
| My quizzes, one student's page | All quizzes | New, In progress |

- Folder menus (`<select>`) use the same words: "All quizzes", the folders indented, then "Uncategorized".
- "Due within N days" is **not** a folder. Home's counter opens the list of quizzes due soon (`?show=soon`). N is set in **Settings › Technical settings › "Due soon" on the Dashboard** (`due_soon_days`, 1–14).

## 4. Boxes and rows

### Boxes (`details.box`)
- Variants: `.card`, `.sub-box`, `.result-box`, `.quiz-card`, `.person-card`, `.dash-card`, `.row-fold`.
- **Summary order:**
  1. fold arrow
  2. icon
  3. title
  4. count badge (`box_label`)
  5. status badges
  6. the box's own actions, pushed right
- A folded box is **one line**. A long title wraps beside its badges, or is cut short with "…". Badges and buttons never drop to a line by themselves.
- Things start folded. Open or folded is remembered (`data-box`, `boxes.js`).
- **Rows** in tables fold too: the first cell is a `details.row-fold`, and `td.row-more` hides while the row is folded.
- **Box borders:** a new quiz's box has an amber border; an in-progress one has a blue border.

### Expand all / Collapse all
- Every set of things that fold has exactly **one** pair, placed on the set's heading line: the page's, the folder list's, the chosen tab's, or a box's own.
- Never two pairs for the same set. The more specific one wins.
- **Always shown.** When nothing in the set folds, the pair is grayed with the tooltip "Nothing here opens or folds".
- A pair on a box's heading line never folds that box. Expand all also opens the box itself.

### Tables as cards
- Markup: `.table-wrap.stack`, each cell with `data-label`.
- On phones, and in narrow list areas, each row becomes a card.
- A folded row's name needs no caption.
- The row's buttons form an even grid of two, and a lone last button spans both.

## 5. Controls

### Buttons
| Class | Use |
|---|---|
| `.btn` (accent fill) | the **one** main action of an area: + New…, Assign, Grade, Start / Continue, Restore, Send |
| `.btn-secondary` | everything else (the default) |
| `.btn-danger` | removes or deletes; red text, red fill on hover |
| `.btn-all` (dashed, tinted) | actions on a whole set ("Archive all (n)") |
| `.btn-link` | text-only small actions (Clear all) |

- **Sizes:**
  - default for page heads
  - `btn-sm` for rows, box headings and the Dashboard
  - `btn-xs` inside folder tabs, the folder list and Folder options
- **Prefixes:**
  - "+ " for New…
  - "← " for Back
  - " →" on links that go somewhere
  - "↺ " for Start over / Undo changes
- **Actions on a whole set** go on the set's heading line: Archive all, a quiz's View / Edit / Print, a student's Message / Assign.

### Bars
- **Filter bar** (`filter_bar`), all on one line:
  1. [Filter by name…]
  2. [Clear]
  3. [Show ▾] with its word beside it, when the page has one
  4. the count, e.g. "3 people"
- Folder pages always have the filter bar.
- **Move bar** ("Check … to …"): its menu and buttons are grayed until something is checked, with the tooltip "Check something below first".

### Pop-overs and dialogs
- **Pop-overs** float over the page and close on a click elsewhere or Esc: Folder options, menus (`details.menu`), and the side panels when they're not pinned.
- **The only dialog** is `confirm.js`'s `dialog.ask` (see §7).

### Forms
- **Fields:** use the `field(...)` and `check(...)` macros. Each gives a label, `.help` under the field, and `.error` under it on a mistake.
- **Errors after sending:** `errors()` shows "Please fix this:" with a list.
- **Buttons:** the main button comes first, then Cancel (`btn-secondary`).
- **Dates:** date and time fields use the site calendar (`calendar.js`). Under the field it writes the date out in words.

## 6. Names and states

### Names are links
- A student's name opens their student page (`person_link`, `student_link`). On Messages, it opens the conversation instead.
- A quiz's name opens its history (`quiz_link`).
- **Link style:** dotted underline, accent color on hover, and a small tooltip above (`data-tip`).
- A name link replaces a "Student page" or "History" button.
- **Exceptions:** a name that is a drag handle (Problems and Quizzes rows, People cards) keeps its History or Student page button. A name in a checkbox label is never a link.
- Students never get links to teacher pages.

### States
| State | Teacher sees | Student sees |
|---|---|---|
| assigned, not opened | **Not started**: amber outline badge (`badge-warn badge-status`) | **New**: amber badge |
| started, or handed in and waiting for grading | **In progress**: blue outline badge (`badge-accent badge-status`) | **In progress** |
| graded | the score: green, amber or red by `score_class()` | the same |

- **"Waiting for grading" is a teacher-only phrase for the grading queue:**
  - Grading
  - the Dashboard box
  - the Results "Show" filter
  - tooltips on In progress badges ("Handed in and waiting for grading")
- Everywhere else the state is **In progress**.

### Badge colors
| Class | Meaning |
|---|---|
| `badge` (gray) | neutral facts: Removed, Teacher-graded, counts (`box-count`) |
| `badge-ok` (green) | good score, on or open |
| `badge-warn` (amber) | New / Not started, "N students differ", "Just for X" |
| `badge-bad` (red) | low score, Due soon |
| `badge-accent` (blue) | In progress, Teacher, question type |
| `.count` | the red pill for unread messages, the grading queue, quizzes to do |

### Words
| Use | Not |
|---|---|
| attempt | try |
| Restore | Bring back |
| check / checked | tick |
| Uncategorized | the top, the top level, main list |
| Assigned | |
| hand in | submit (on screen) |
| teacher | administrator |
| Folder options | |
| Open this folder | |
| Expand all / Collapse all | |
| All … | |
| Results by student / Results by quiz | |
| quiz history (the History button) | |

- American spelling, and US units (mph, miles, pounds, °F).
- **Removing things:**
  - **Remove**: can be undone (a quiz goes to Removed quizzes; a folder's contents stay).
  - **Archive**: an attempt goes to the Archive, where it can be Restored.
  - **Delete for good**: can't be undone.
  - **Clear all**: notices.
- **Recent lists:**
  - Dashboard: "Recent hand-ins"
  - Home: "Recently completed"
  - My quizzes: "Just finished"

### Icons
Icons are line icons from `app/icons.py`, in the accent color in headings, tabs and the folder list.

| Icon | Means |
|---|---|
| note | a problem or quiz |
| folders | All |
| folder | a folder |
| tray | Uncategorized |
| sparkle | New |
| pencil | In progress / grading |
| users | people |
| archive | Archive |
| printer | Print |
| calendar | dates |

## 7. Messages people see

### Flash messages (`flash(msg, 'success' | 'error' | 'warning')`)
- **Always give a category.** Without one, the message shows as plain blue info.
- **Success:** a past-tense verb, the thing in curly quotes, and a period, often followed by where it went or what to do next. Example: "Assigned “Week 1” to 3 students. View the quiz · See its history →".
- **Error:** what went wrong and what to do. Example: "That didn't go through (the page was out of date). Please try again."
- After a reload the message floats, and the page keeps your place (`place.js`).

### Confirm dialogs (`data-confirm` / `data-confirm-ok`)
- **Question:** "Verb the thing “X”? Consequence."
- **OK button:** repeats the verb ("Delete for good", "Remove folder", "Archive all (3)"). Cancel has focus.
- The OK button is red for Delete, Remove and Clear.
- **Example:** "Delete ben’s attempt at “Quiz” for good? This can’t be undone." with OK "Delete for good".

### Empty states
- **Page level:** `div.card.empty`, with a big icon, "No X yet." and a link to make one ("No problems yet. Create your first one.").
- **In a list or tab:** `p.card.empty.small`: "Nothing in “X” yet." Uncategorized, when empty: "Everything is in a folder."
- **Inside a box:** `p.muted.small`, a short sentence.
- **Cheerful empties for students:** "No new quizzes right now.", "Nothing in progress right now.", "You're all caught up."

### Tooltips (`title=`)
- Sentence case, no final period.
- An action's tooltip starts with a verb ("Open…", "See…", "Give…").
- A badge's tooltip is a noun phrase ("The score that counts").
- Names of things go in curly quotes; apostrophes are curly (’).
- A disabled control's tooltip is the reason ("Nobody in “X” yet").

### Toasts (`messages.js`)
- New message or notice: "New message from X" / "New notice", with buttons "Open messages" / "Open notices" and "Dismiss".
- Page changed: "This page has changed since you opened it.", with "Refresh" and "Not now".

### Script errors
- "That didn't work. Please try again."
- "Couldn't reach the server. Please try again."

## 8. Phones and narrow windows

- **Main breakpoint 640px:**
  - tables become cards
  - `.wide-only` words drop off
  - page-head and `.title-actions` buttons make an even grid of two; a lone last button spans both, and Expand all / Collapse all take a row of their own
  - the folder tabs scroll inside their strip
- **480px:** a row of three or more buttons stacks one per line, and the dock panels take the full width.
- **1000px:** the menu becomes a Menu button.
- **Container queries:**
  - `page` (`main.container`)
  - `listarea` (`.folder-main`): at 860px it switches to cards like a phone
  - `editform`
- **No page ever scrolls sideways.** Inner scroll areas grow to full height on phones.

## 9. Reusable pieces (where to find them)

- **`_macros.html`:**
  - `field`, `check`, `errors`
  - `tip` (the "?" help)
  - `image_drop`, `avatar`
  - `back_button`, `back_home`
  - `slot` (grayed button with reason)
  - `person_link`, `student_link`, `quiz_link`
  - `expand_collapse`
  - `filter_bar`
  - `post_button` (form + confirm)
  - `box_label`, `count_of`
- **`_folders.html`:**
  - `folders_page`, `all_boxes`, `folder_items`
  - `side_folder`, `new_folder`, `level_buttons`
  - `in_folders` (folder chips + "+"), `move_menu`, `move_mini`
  - `empty_note`, `flag_badges`
- **Other partials:**
  - `_results.html`: `result_cells`, `archive_all_button`
  - `_results_filter.html`
  - `_people.html`: `people_switch`
  - `_awards.html`: `award_list`
- **Scripts and the switches that turn them on:**
  - `boxes.js`: `details.box`, `data-box`, `data-level*`
  - `folderfilter.js`: `data-folder-filter`, `data-start`, `data-no-main`
  - `filter.js`: `data-filter-bar`, `qgenHideRow`
  - `folders.js`: drag and drop, `data-drop`
  - `confirm.js`: `data-confirm`
  - `place.js` and `keep.js`: your place after a reload or Back
  - `trail.js`: `data-back`
  - `tips.js`: `data-tip`
  - `calendar.js`
  - `messages.js`: toasts, live pages via `data-watch`

---

## Bringing pages in line (known gaps, October 2026)

These break the rules above. Fix them as pages are touched, and say so.

- **Flash messages without a category, or in old-style wording:**
  - `user/routes.py` 20, 40, 294, 347, 383, 398, 409, 434, 438
  - `upload/routes.py` 38–127
  - `error/handlers.py`
  - Old-style examples: "I can't let you do that", "Updated user: (id) name".
- **Straight "quotes" in flash messages** (`qgen/routes.py`, many lines; "Moved …" messages) where the rule is curly “quotes”.
- **"submit" on screen:**
  - `qgen/routes.py` 585, 660
  - `api/student.py` 129
  - the upload form's Submit button
- **"administrator":**
  - `user/routes.py` 30
  - `eduser.html` 16
  - `500.html` 10
- **"Moved to …" names the destination three ways:** "the top", "the top level", "Uncategorized". Use "Uncategorized".
- **Two folder-name-length messages:** `folder_tree.py` 24 and `services.py` 67, 340.
- **Confirm questions off the pattern:**
  - "Are you sure you want to send this to all N students?" (`inbox.html`, `_teacher_messages.html`)
  - "Put … back?" with OK "Restore" (`archive.html`, `archived.html`)
  - "Delete “x”?" with no consequence (`nonimages.html`)
- **Empty-state wording varies:** "Empty.", "Nothing here yet.", "No students in this folder.".
- **Disabled reasons say the same thing in different words:**
  - "No one has taken this quiz yet" vs "No one has this quiz yet"
  - "No one is in this folder yet" vs "Nobody in “X” yet"
- **Score badges that don't use `score_class()`:** `mypage.html` combined and counted scores, `_results.html` counted, the `results_by_quiz.html` average.
- **Hidden instead of grayed:**
  - "Scan workbook pages" without an AI key
  - "Remove picture" when there's no picture
  - a removed quiz's Remove/Delete slot (`vqlist.html` 52)
- **Name links using `title=` instead of `data-tip`:** `review.html`, `quiz_form.html`, `quiz_take.html`.
- **Stale comments that say the Expand all / Collapse all pair is "shown only when…":** `_macros.html` 126, `_folders.html` 78, `boxes.js` 18.
- **Vocabulary drift:**
  - "View quiz" / "Edit quiz" (Results by quiz) vs "View" / "Edit" (Quizzes)
  - "Edit user" vs "Edit"
  - "Teachers’ messages" vs "Messages between teachers"
  - the Dashboard says "Open Users…"
  - "Assign it"
- **Archive's move bar** reads "Move them to … Move", while Problems and Quizzes read "Put in folder / Take out of folder". Pick one.
- **Phone button grids:** 3-button rows may get both the 3-column rule (`app.css` ~1859/1882) and the 2-up rule (~2115). Check at 481–640px.
