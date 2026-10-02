# qgen: quizzes where every student gets a different version

qgen is a small, self-hosted quiz app for teachers (Flask, MySQL and MathJax).

**The problem it solves is cheating.** When everyone gets the same quiz, answers travel.
A student says "number 3 is B" to a friend, peeks at a neighbour's screen, or remembers a
quiz for a retake. In qgen, **every student gets a different version** of the same quiz.
The questions are the same kind, but they use different numbers, names and pictures, with
choices and questions in a different order. Passing answers along doesn't help.

Teachers don't need to be technical. Problems are written in plain words with
`[placeholders]`, and random values are set up in a simple table. A plain-English helper
(powered by Claude) can fill the form in for you.

---

## What it does

### For teachers
- **Six question types:** Numeric, Short text, Pick one, Pick several, True/False, and
  Long text (essays you grade).
- **Friendly problem writing.** Put random values in square brackets, like
  `A train goes [speed] mph for [hours] hours.` The answer is ordinary math: `speed * hours`.
- **A values table** instead of code. The kinds of value are:
  - whole numbers, with optional steps and "not zero"
  - decimals
  - picks from a list, including matched pairs like `country = capital`
  - calculated values
  - imaginary and complex numbers
  - "different from" rules between values
- **"Show me 3 examples"** shows sample student versions before you save.
- **A live helper** checks your work as you type. It catches typos in names and wording that
  suits another question type. It also flags problems where students would get the same
  answer, so the answer could be passed along. Many fixes take one click.
- **Plain-English helper (optional):** describe a problem and Claude fills in the form.
  "Review with AI" gives a second opinion. It needs an Anthropic API key.
- **Safe math.** Before a problem is saved, every possible set of values is tried, so
  division by zero, square roots of negatives and similar can't reach a student.
  Imaginary numbers only ever appear in problems that are about them.
- **Quizzes** are built by ticking problems. Put problems in a **group** to give each student
  "2 of these 6", shuffle question order per student, and choose how retakes count
  (best, latest, average, first, or the best two).
- **Assign** to many students at once, with optional **open/close times** and a
  **time limit**.
- **Grade essays** by highlighting right and wrong parts, giving partial credit and leaving
  a comment. Everything else is graded automatically.
- **Hide correct answers** until you release them, if you prefer.
- **Messages:** write to one student, chosen students or everyone. Pin announcements to the
  top of students' home pages.
- **Settings:** your school's name and logo, and a class code that students need to sign up.

### For students
- A clean home page with quizzes, scores (best attempt marked), messages and
  announcements.
- **Answers save automatically.** A closed tab or a flat battery loses nothing.
- A quiet time reminder when there's a time limit. When time is up, saved answers are
  handed in.
- Fractions (`3/4`, `1 1/2`) and complex numbers (`3 + 2i`) are understood.
- Results with every answer marked, and the teacher's comments on essays.
- A profile picture, or coloured initials.

### Scoring without the teacher
Quizzes without essays are scored the moment the student submits. Overdue quizzes are
closed and scored automatically, even if the student never comes back.

### For app developers
A REST API at `/api/v2` covers everything above for both students and teachers. Apps sign
in with personal access tokens.
- The documentation is at `/api/v2/docs`.
- The OpenAPI 3.1 description is at `/api/v2/openapi.json`.

---

## Getting started

Requirements: Python 3.10 or newer, MySQL (or MariaDB), and optionally nginx and gunicorn
for production.

```bash
git clone https://github.com/oscarpoppa/qgen.git
cd qgen
pip install -r requirements.txt
cp .env.example .env                     # then edit .env (see below)
flask --app quizapp.py init-db           # a new, empty database
flask --app quizapp.py create-admin you  # your first account (asks for a password)
flask --app quizapp.py run
```

Open http://localhost:5000, log in, and set a **class code** under **Settings** so
students can create their accounts.

**Upgrading an existing qgen database?** Back it up first, then run
`flask --app quizapp.py db upgrade` instead of `init-db`. Existing problems and quizzes keep
working unchanged.

### Settings (`.env`)

| Setting | Needed | What it is |
|---|---|---|
| `DATABASE_URL` | yes | `mysql+pymysql://USER:PASSWORD@HOST/DATABASE`. Write `&` as `%26` and `!` as `%21` in the password. |
| `SECRET_KEY` | yes | A long random string: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `STATIC_DIR` | no | Where uploaded pictures and files go (default: `static/` next to `config.py`) |
| `ANTHROPIC_API_KEY` | no | Turns on "Fill in for me" and "Review with AI" |

`.env` is never committed. The app refuses to start without the two required settings.

### Running it for real

`startapp.sh` starts nginx (in front) and gunicorn (running the app) and checks that the
site answers. It's safe to run again. `stopapp.sh` stops both.

Run this every few minutes from cron if you want overdue quizzes closed even when nobody is
using the site:

```bash
flask --app quizapp.py close-expired
```

---

## Writing a problem: a quick tour

| | |
|---|---|
| **Question** | `[who] rides a train at [speed] mph for [hours] hours. How far does [who] travel?` |
| **Values** | `speed`: Whole number, 40 to 80, in steps of 5 · `hours`: Whole number, 2 to 5 · `who`: Pick from list `Maria, Ahmed, Li` |
| **Answer** | `speed * hours` |

Every student sees different numbers and a different name, and each answer is graded
against that student's version.

- **Pick one / Pick several:** write one choice per line and put `*` before correct ones.
  Choices can use values too, like `*[a + b]`. "Show only 4" gives each student a different
  4 drawn from a bigger pool. Pick several can also accept *other correct combinations*,
  such as "tick two numbers that add up to 10".
- **True/False:** the answer can be a comparison like `a > b`, so it's true for some
  students and false for others.
- **Pictures:** add several and each student gets one at random. Give them labels and use
  `[picture]` in the answer ("What animal is this?").
- **Math:** `+ - * / ^`, parentheses, `sqrt`, `abs`, `round(x, 2)`, `min`, `max`.
  With complex numbers switched on you also get `i`, `re`, `im` and `conj`.

The problem page includes an example of every question type.

---

## Development

```bash
python -m pytest -q tests                   # the whole suite; no database or API key needed
python scripts/seed_demo.py --env .env      # demo students, problems and quizzes
```

The tests cover every question type, the math engine's safety limits, the full
teacher-student cycle, the REST API, database delete rules (with foreign keys enforced), and
that the API documentation matches the real routes.

### Where things live

| Path | What's there |
|---|---|
| `app/qgen/friendly.py` | The problem markup: values, `[placeholders]`, the safe math evaluator, plain-language errors |
| `app/qgen/qtypes.py` | The question types: how each is checked, randomized, shown and graded |
| `app/qgen/services.py` | Everything teachers and students can *do*, shared by the web pages and the API |
| `app/qgen/coach.py` | The live helper's checks |
| `app/qgen/layout.py` | A quiz's problem list, including groups |
| `app/qgen/ai_helper.py` | "Fill in for me" and "Review with AI" |
| `app/messages/` | Messages, announcements and automatic notices |
| `app/api/` | The REST API (`/api/v2`) and its documentation |
| `migrations/` | Database changes (Alembic) |
| `tests/` | The test suite |

### Adding a question type
Subclass `QType` in `app/qgen/qtypes.py`: validate, render, make the form field and grade.
Then add it to `REGISTRY`. It automatically appears in the editor's type menu, in quizzes
and in the API.

### Adding a kind of random value
Add it to `KINDS` in `app/qgen/friendly.py`. Teach `_draw` how to pick one,
`validate_values` how to check one, and `_choices_of` how to list every possibility (used for
the before-saving safety check). Then add its settings to `ValueRow` in `forms.py` and to
`problem_form.html`.

### Adding an API endpoint
Put the logic in a service function, add a thin route in `app/api/`, and add a line to
`ENDPOINTS` in `app/api/docs.py`. A test fails if an endpoint is missing from the
documentation.

---

## Security notes
- Passwords are hashed. API tokens are stored only as SHA-256 fingerprints and can be
  revoked. Repeated wrong passwords through the API are throttled.
- Students' answers and problem text are always shown as text, never as HTML or template
  code.
- Uploaded pictures are verified and re-encoded. Profile photos lose hidden metadata such as
  GPS location.
- Everything that changes data needs a form or request carrying the site's own session
  token (protection against cross-site request forgery). Plain links never delete anything.
