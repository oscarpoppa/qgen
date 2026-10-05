"""Awards a student earns from their finished quizzes, worked out from their attempts each
time (nothing is stored), so a regrade or a deleted attempt is always reflected:

  Perfect score  a quiz whose score that counts is 100% (by its retake rule, so with
                 "average" a 100% retake after a 50% isn't enough); one per quiz
  Milestones     1, 5, 10 and 25 different quizzes finished
  Streak         3, 5 and 10 finished attempts in a row at 90% or more
  Comeback       a retake at least 20 points higher than the try before it (one per quiz)

Attempts still being graded don't count until they're graded."""
from .models import CQuiz, combined_score

MILESTONES = (1, 5, 10, 25)
STREAKS = (3, 5, 10)
STREAK_SCORE = 90
COMEBACK_POINTS = 20


def _perfect(score):
    return score is not None and score >= 99.995


def _rule(user, vquiz):
    """How this student's attempts at a quiz combine: their own rule if a teacher set one
    (on their latest attempt that has one, as the results pages do), else the quiz's."""
    rows = CQuiz.query.filter(CQuiz.assignee == user.id, CQuiz.vquiz_id == vquiz.id).order_by(CQuiz.id.desc()).all()
    return next((c.own_retake_rule for c in rows if c.own_retake_rule), None) or vquiz.retake_rule


def _finished(user):
    """Their graded attempts, in the order they were handed in."""
    rows = CQuiz.query.filter(CQuiz.assignee == user.id, CQuiz.completed.is_(True), CQuiz.score.isnot(None)).all()
    return sorted(rows, key=lambda c: (c.compdate is None, c.compdate or 0, c.id))


def earned(user):
    """[{'kind', 'icon', 'title', 'detail', 'when' (datetime or None), 'quiz' (or None)}],
    newest first."""
    done = _finished(user)
    out = []
    #perfect scores: quizzes whose score that counts (its retake rule, or this student's own
    #rule if a teacher set one) is 100% now; dated when it last became 100%
    by_quiz = {}
    for c in done:
        by_quiz.setdefault(c.vquiz_id, []).append(c)
    for attempts in by_quiz.values():
        rule = _rule(user, attempts[0].vquiz)
        scores = [c.score for c in attempts]
        if not _perfect(combined_score(rule, scores)):
            continue
        since = attempts[-1]
        for i in range(len(attempts), 0, -1):
            if not _perfect(combined_score(rule, scores[:i])):
                break
            since = attempts[i - 1]
        out.append({'kind': 'perfect', 'icon': '🌟', 'title': 'Perfect score', 'detail': '100% on "{}"'.format(since.vquiz.title),
                    'when': since.compdate, 'quiz': since.vquiz})
    #milestones: different quizzes finished
    seen = set()
    for c in done:
        if c.vquiz_id in seen:
            continue
        seen.add(c.vquiz_id)
        if len(seen) in MILESTONES:
            n = len(seen)
            out.append({'kind': 'milestone', 'icon': '🏁' if n == 1 else '🏆', 'quiz': None, 'when': c.compdate,
                        'title': 'First quiz' if n == 1 else '{} quizzes'.format(n),
                        'detail': 'Finished your first quiz' if n == 1 else 'Finished {} different quizzes'.format(n)})
    #streaks: in a row at 90% or more; each length once, when first reached
    run, reached = 0, set()
    for c in done:
        run = run + 1 if c.score >= STREAK_SCORE else 0
        if run in STREAKS and run not in reached:
            reached.add(run)
            out.append({'kind': 'streak', 'icon': '🔥', 'quiz': None, 'when': c.compdate,
                        'title': '{} in a row'.format(run),
                        'detail': '{} quizzes in a row at {}% or more'.format(run, STREAK_SCORE)})
    #comebacks: a retake well above the try before it
    before, came_back = {}, set()
    for c in done:
        prev = before.get(c.vquiz_id)
        if prev is not None and c.score - prev >= COMEBACK_POINTS and c.vquiz_id not in came_back:
            came_back.add(c.vquiz_id)
            out.append({'kind': 'comeback', 'icon': '🚀', 'title': 'Comeback', 'quiz': c.vquiz, 'when': c.compdate,
                        'detail': 'Up {:.0f} points on "{}" ({:.0f}% → {:.0f}%)'.format(c.score - prev, c.vquiz.title, prev, c.score)})
        before[c.vquiz_id] = c.score
    out.sort(key=lambda a: (a['when'] is not None, a['when'] or 0), reverse=True)
    return out


def still_to_earn(user, have):
    """The awards they could earn next, for the Home page: the next milestone and streak,
    and (if they have none yet) the first perfect score and comeback."""
    kinds = {a['kind'] for a in have}
    titles = {a['title'] for a in have}
    out = []
    if 'perfect' not in kinds:
        out.append({'icon': '🌟', 'title': 'Perfect score', 'detail': 'Have 100% as the score that counts on a quiz'})
    nxt = next((n for n in MILESTONES if ('First quiz' if n == 1 else '{} quizzes'.format(n)) not in titles), None)
    if nxt:
        out.append({'icon': '🏁' if nxt == 1 else '🏆', 'title': 'First quiz' if nxt == 1 else '{} quizzes'.format(nxt),
                    'detail': 'Finish your first quiz' if nxt == 1 else 'Finish {} different quizzes'.format(nxt)})
    nxt = next((n for n in STREAKS if '{} in a row'.format(n) not in titles), None)
    if nxt:
        out.append({'icon': '🔥', 'title': '{} in a row'.format(nxt), 'detail': 'Score {}% or more on {} quizzes in a row'.format(STREAK_SCORE, nxt)})
    if 'comeback' not in kinds:
        out.append({'icon': '🚀', 'title': 'Comeback', 'detail': 'Do {} points better on a retake'.format(COMEBACK_POINTS)})
    return out
