from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, PasswordField, BooleanField, SubmitField, FileField
from app.qgen.models import VQuiz
from app.models import User

block_top = """
{% extends "base.html" %}

{% block content %}
"""

form_top = """
    <form action="" method="post">
        {{ form.hidden_tag() }}
"""

form_bottom = """
        {{ form.submit() }}
    </form>
"""

block_bottom = """
{% endblock %}
"""

block_header = """
<b>{{ title }}<br><br></b>
"""

prob_capsule = """
    {}. {} {}<br>{}<br><br>
"""

fieldname_base = 'Number{}'


def renderable_factory(cquiz):
    ftypes = {'text':StringField, 'txt':StringField, 'string':StringField}
    ttlst = [block_header]
    phash = {p.ordinal:p for p in cquiz.cproblems}
    skeys = sorted(phash.keys())
    imgtmpl = '<br><img src="/static/{}" style="width:35%"/><br><br>'
    class OTF(FlaskForm):
        submit = SubmitField('Submit')
        @property
        def result_template(self): # AKA transcript
            date_header = '<b>Started:</b> {}<br><b>Completed:</b> {}<br>'.format(cquiz.startdate, cquiz.compdate)
            head_chunks = [block_header, date_header]
            prob_chunks = []
            num_correct = 0
            for idx in range(1, int(self.count)+1):
                field_name = fieldname_base.format(idx)
                submitted_ansr = getattr(self, field_name).data or 'None'
                correct_ansr = getattr(self, field_name+'_ansr')
                problem = getattr(self, field_name+'_prob')
                right_or_wrong = 'W'
                try:
                    if submitted_ansr != 'None' and abs(float(submitted_ansr) - float(correct_ansr)) < 0.1:
                        num_correct += 1
                        right_or_wrong = 'R'
                except:
                    pass
                summary = '({}) Your answer: {} : Correct answer: {}'.format(right_or_wrong, submitted_ansr, correct_ansr)
                pimg = phash[idx].vproblem.image
                if pimg:
                    img = imgtmpl.format(pimg)
                else:
                    img = ''
                prob_chunks += prob_capsule.format(idx, img, problem, summary)
            pimg = cquiz.vquiz.image
            if pimg:
                img = imgtmpl.format(pimg)
            else:
                img = ''
            self.score = 100*num_correct/self.count
            head_chunks += '<br><b>Score:</b> {}%<br><br>'.format(100*num_correct/self.count)
            all_chunks = head_chunks + prob_chunks
            #add to object
            prob_section = ''.join(all_chunks)
            return block_top+img+prob_section+block_bottom
    for ordinal in skeys:
        problem = phash[ordinal]
        field_name = fieldname_base.format(ordinal)
        inpstr = '{{ '+'form.{}'.format(field_name)+' }}'
        pimg = problem.vproblem.image
        if pimg:
            img = imgtmpl.format(pimg)
        else:
            img = ''
        ttlst += prob_capsule.format(ordinal, img, problem.conc_prob, inpstr)
        ftype = ftypes[problem.vproblem.form_elem]
        setattr(OTF, field_name, ftype(field_name)) 
        setattr(OTF, field_name+'_ansr', problem.conc_ansr) 
        setattr(OTF, field_name+'_prob', problem.conc_prob) 
    setattr(OTF, 'count', len(cquiz.cproblems))
    ttext = ''.join(ttlst)
    pimg = cquiz.vquiz.image
    if pimg:
        img = imgtmpl.format(pimg)
    else:
        img = ''
    templ = block_top+img+form_top+ttext+form_bottom+block_bottom
    return templ, OTF

def assign_form_factory():
    class A(FlaskForm):
        submit = SubmitField('Submit')
    users = User.query.all()
    vquizzes = VQuiz.query.all()
    setattr(A,'user', SelectField('Assign CQuiz to User', choices=[(a.id, a.username) for a in users]))
    setattr(A,'vquiz', SelectField('Using VQuiz', choices=[(a.id, a.title) for a in vquizzes]))
    return A
