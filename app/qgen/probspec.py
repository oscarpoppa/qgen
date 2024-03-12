from random import randint as ri, choice as ch
from re import sub, search, findall, escape
from flask import flash, current_app

def func_ok_or_raise(string):
    allowed_funcs = ('ri', 'ch')
    if not string in allowed_funcs:
        raise ValueError('Unauthorized function specified--eval denied: "{}"'.format(string))

def is_math_or_raise(string):
    notmath_patt = r'[^\(\)\^\+\-\/\*\d\s\.]'
    bad_m = findall(notmath_patt, string)
    if len(bad_m):
        raise ValueError('Potentially dangerous expression--eval denied: "{}" : {}'.format(string, bad_m))

# list of all patterns
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
    func_ok_or_raise(mdict['func'])
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
    is_math_or_raise(mystr)
    val = eval(mystr)
    symbols[mdict['symbol']] = val
    return val

# bare expression
def bare_expr(string, symbols):
    mystr = string
    for k,v in symbols.items():
        mystr = sub(k, str(v), mystr) 
    # only allow math symbols in eval
    is_math_or_raise(mystr)
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
    #pattern substitution
    for k,v in repl.items():
        #remove definition-only invisible patterns
        if search('\s*:\s*inv\s*', k):
            prob = sub(escape(r'{{'+k+r'}}'), '', prob)
            continue 
        prob = sub(escape(r'{{'+k+r'}}'), str(v), prob)
        ansr = sub(escape(r'{{'+k+r'}}'), str(v), ansr)
    #aesthetics...
    #turn '...+/- -...' into '...-/+ ...'  
    prob = sub('\+\s*\-', '- ', prob)
    prob = sub('\-\s*\-', '+ ', prob)
    #turn '+ 0x' into ''
    prob = sub('[\+\-]\s*0[a-zA-Z]+', '', prob)
    #turn '+ 1x' into '+ x'
    prob = sub('([\+\-]\s*)1([a-zA-Z]+)', '\\1\\2', prob)
    return prob, ansr

