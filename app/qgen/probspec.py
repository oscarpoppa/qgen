from random import randint as ri
from re import sub, search, findall, escape

allowed_funcs = ('ri',)

def ismath(string):
    notmath_patt = r'[^\(\)\^\+\-\/\*\d\s]'
    bad_m = findall(notmath_patt, string)
    if len(bad_m):
        return False
    return True

def get_targets(prob, ansr):
    mainpatt = r'{{([^}{]*)}}'
    return findall(mainpatt, prob) + findall(mainpatt, ansr)

# function dependent
def primary_symbol(string, symbols):
    func_patt = r'(?P<symbol>\w+)\s*:\s*(?P<callable>(?P<func>\w+)\((?P<args>.*)\))'
    mo = search(func_patt, string)
    if not mo:
        return None
    mdict = mo.groupdict()
    # only allow approved functions in eval
    if not mdict['func'] in allowed_funcs:
        return None
    val = eval(mdict['callable'])
    symbols[mdict['symbol']] = val
    return val

# expression dependent
def secondary_symbol(string, symbols):
    expr_patt = r'(?P<symbol>\w+)\s*:\s*(?P<expr>.*)'
    mo = search(expr_patt, string)
    if not mo:
        return None
    mdict = mo.groupdict()
    mystr = mdict['expr']
    for k,v in symbols.items():
        mystr = sub(k, str(v), mystr) 
    # only allow math symbols in eval
    if not ismath(mystr):
        return None
    val = eval(mystr)
    symbols[mdict['symbol']] = val
    return val

# bare expression
def bare_expr(string, symbols):
    mystr = string
    for k,v in symbols.items():
        mystr = sub(k, str(v), mystr) 
    # only allow math symbols in eval
    if not ismath(mystr):
        return string
    return eval(mystr)

def process_spec(prob, ansr):
    symbols = {}
    repl = {}
    #primaries
    for j in get_targets(prob, ansr):
        repl[j] = primary_symbol(j, symbols)
    #secondaries
    for k,v in repl.items():
        if ':' in k and v is None:
            repl[k] = secondary_symbol(k, symbols)
    #bare expressions 
    for k,v in repl.items():
        if v is None:
            repl[k] = bare_expr(k, symbols)
    for k,v in repl.items():
        prob = sub(escape(r'{{'+k+r'}}'), str(v), prob)
        ansr = sub(escape(r'{{'+k+r'}}'), str(v), ansr)
    return prob, ansr

def gen_cprob(cquiz, vprob, ordinal):
    cp, ca = process_spec(vprob.raw_prob, vprob.raw_ansr)
    nucprob = CProblem(ordinal=ordinal, cquiz_id=cquiz.id, conc_prob=cp, conc_ansr=ca, vproblem_id=vprob.id)
    nucprob.save()
    return nucprob

