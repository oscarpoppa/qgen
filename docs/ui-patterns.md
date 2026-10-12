# UI patterns

These are the look-and-feel rules the site follows, agreed with the site owner in 2026. They apply to every page: when a page doesn't follow one, change the page.

## 1. Compact first
- A page uses no more space than it needs.
- Before adding a row, put the control on a line that's already there, usually the heading.
- Long names wrap or are cut short with "…", with the full name in the tooltip. They never push a button onto a line of its own.

## 2. Folder pages
This covers Problems, Quizzes, People (Accounts and Results), Results by quiz, the Archive, one student's page and My quizzes.

- **Left:** the folder list.
  - Its own Expand all / Collapse all at the top shows or hides the folders inside folders.
  - New folder, and a short help line.
  - On All views, a click in the folder list chooses that folder in place.
- **Top:** the page title, with the page's Expand all / Collapse all at the right.
- **Folder buttons:** a row on a dashed band.
  - The order is always: **All** (chosen to begin with), the automatic ones (New, In progress), the folders, then **Uncategorized**.
  - A folder with folders inside it adds a second row for them.
  - The chosen folder's own buttons sit right after its button: Expand all / Collapse all, then Open this folder, then any folder action such as "Assign a quiz to this folder".
- **One list:** each thing appears once, and the folder buttons narrow it.
- **Empty folders:** faded but still clickable. A folder with nothing in it says "Nothing in “X” yet."
- **Folder options:** a pop-over that floats over the page and closes on a click elsewhere or Esc.

## 3. Things that live in folders fold
- Problems, quizzes, people, students' results, quiz results and archived attempts all fold.
- Folded, a thing is one line: its name, key status, folders and buttons.
- Open, it shows the rest.
- Things start folded. Their open or folded state is remembered.

## 4. Expand all / Collapse all
- Every set of things that fold has one pair:
  - the page's;
  - the folder list's;
  - the chosen folder's;
  - a box's own, on its heading line.
- Never two pairs for the same set. The chosen folder's pair wins over the page's.
- It is **always shown**. When nothing in the set folds, it's grayed out with the reason in its tooltip.
- A pair on a heading line never folds that heading's box. Expand all also opens the box itself.

## 5. Gray out, never hide
- A button that doesn't apply stays where it is, disabled, with the reason as its tooltip.

## 6. Controls for a whole set
- They go on the set's heading line (Archive all, a quiz's View / Edit / Print, a student's Message / Assign).
- They look different from an item's own buttons.
  - "Archive all (n)" uses the tinted, dashed `.btn-all` style.

## 7. Line things up
- Boxes at one level share column widths, so their buttons sit under one another.
  - This covers the quiz boxes on a student page, Grading's tables and the Dashboard's rows.
- Buttons that take turns in one place (Results / Assigned) have one width.

## 8. Names are links
- A student's name opens their student page.
- A quiz's name opens its history.
- On Messages, a student's name opens the conversation.
- Links have a dotted underline, the accent color on hover, and a small tooltip above.
- They replace a "Student page" or "History" button.
- Never on a folder's heading, which becomes a folder button, and never in a checkbox label.
  - People cards keep their "Student page" button, because their heading is a drag handle.
- Students never get links to teacher pages.

## 9. States and words
- **Not started:** an amber outline badge.
- **In progress:** a blue outline badge.
  - It covers started attempts and attempts waiting for grading.
  - Only Grading and the Dashboard's "Waiting for grading" box use that phrase.
- **Scores:** green, amber or red, from the Score colors setting.
- **Box borders:** a new quiz's box has an amber border, and an in-progress one has a blue border.
- **Words:**
  - "attempt" (never "try");
  - "Restore" (never "Bring back");
  - "check" (never "tick");
  - "Uncategorized";
  - "Assigned";
  - American spelling and US units.

## 10. Bars and pop-ups
- **Filter bars** are one line: [Filter by name…] [Clear], then [Show ▾] with its word beside it, then the count.
- **Pop-overs** float over the page and close on a click elsewhere or Esc. This covers Folder options, the side panels when not pinned, and menus.

## 11. Phones (375px) and narrow windows
- No page scrolls sideways.
- Button groups make even grids, never one button alone on a line.
- Labels wrap instead of being cut off.
- Words that matter only on wide screens can drop off (`.wide-only`).

## 12. Changes
- Whenever a change removes or hides a control or behavior, say so to the site owner: what, where, and what replaces it.
