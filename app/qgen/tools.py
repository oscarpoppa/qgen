#!/bin/env python
from re import findall, search
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, SelectMultipleField, SelectField
#from wtforms.validators import DataRequired
import random
import copy

## utility

def get_targets(raw):
    mainpatt = r'({{([^}{]*)}})'
    return {a[0]:a[1] for a in findall(mainpatt, raw)}

def shuffle_list(lst):
    mylst = copy.copy(lst) #no clobber
    random.shuffle(mylst)
    return mylst

def pick_n_from_list(lst, n, excludelst=None):
    if not excludelst:
        excludelst = []
    mylst = [a for a in lst if a not in excludelst]
    return random.sample(mylst, n) 

def pick_list_from_pools(rightpool, wrongpool, rightnum=1, listsize=4):
    wrongnum = listsize - rightnum
    if len(rightpool) < rightnum \
    or len(wrongpool) < wrongnum \
    or wrongnum < 1 \
    or rightnum > listsize:
        raise ValueError('size constraint violation')
    ret = [(a, True) for a in random.sample(rightpool, rightnum)]
    ret += [(a, False) for a in random.sample(wrongpool, wrongnum)]
    mixret = shuffle_list(ret) #order preserved
    retdict = {a[0]:a[1] for a in mixret} #for searchability; order can't be guaranteed
    return mixret, retdict

#parse spec stuff


def get_3col(lst, symbols):
    # symbol:expr:flag
    expr_patt = r'(?P<symbol>\w+)\s*:\s*(?P<expr>.*)\s*:\s*(?P<flag>\w*)'
    for mrkup in lst:
        mo = search(expr_patt, mrkup)
        if not mo: 
            return
        mdict = mo.groupdict()
        #raw entry : colon-separated string "...:...:..."
        symbols[mrkup] = (mdict['symbol'], mdict['expr'], mdict['flag'])
    
def get_2col(lst, symbols):
    pass

def get_1col(lst, symbols):
    pass
    
def parse_spec(qraw, araw): #raw markup in
    symbols = {}
    targdct = get_targets(qraw)
    print(targdct)
    for r, s in targdct.items():
        get_3col(targdct, symbols)
    print(targdct)
    print(symbols)

class SpecParser():
    def __init__(self, qraw, araw):
        self.qraw = qraw
        self.araw = araw
        self.targets = {}
        self.symbols = {}

    def run(self):
        self.targets = self.get_targets() #all raw symbols : stripped markup
        self.get_3col(self.targets)
        self.get_2col(self.targets)
        #all vars defined
        self.get_1col(self.targets)

    def get_targets(self): #'{{a:1+2:inv}}': 'a:1+2:inv', '{{a}}': 'a'}
        mainpatt = r'({{([^}{]*)}})'
        return {a[0]:a[1] for a in findall(mainpatt, self.qraw+self.araw)}

    def get_3col(self, dct):
        print(dct)
        expr_patt = r'^\s*(?P<symbol>\w+)\s*:\s*(?P<expr>.*)\s*:\s*(?P<flag>\w*\s*$)'
        #expr_patt = r'(?P<symbol>[^:\s]+)\s*:\s*(?P<expr>[^:\s]*)\s*:\s*(?P<flag>[^:\s]*)\s*'
        for raw, strip in dct.items():
            mo = search(expr_patt, strip)
            if not mo: 
                continue
            mdict = mo.groupdict()
            #raw entry : colon-separated string "sym:expr:flag"
            self.symbols[raw] = (mdict['symbol'], mdict['expr'], mdict['flag'])

    def get_2col(self, dct):
        expr_patt = r'^\s*(?P<symbol>[^:]+)\s*:\s*(?P<expr>[^:]*)\s*$'
        for raw, strip in dct.items():
            mo = search(expr_patt, strip)
            if not mo: 
                continue
            mdict = mo.groupdict()
            #raw entry : colon-separated string "sym:expr"
            self.symbols[raw] = (mdict['symbol'], mdict['expr'], None)

    def get_1col(self, dct):
        expr_patt = r'^\s*(?P<expr>[^:]*\s*$)'
        for raw, strip in dct.items():
            mo = search(expr_patt, strip)
            if not mo: 
                continue
            mdict = mo.groupdict()
            #raw entry : colon-separated string "sym:expr"
            self.symbols[raw] = (None, mdict['expr'], None)





#submit    
#transcript
#problems
#   

if __name__ == '__main__':
    wrong = ['lion', 'bear', 'giraffe', 'dog', 'horse', 'parrot', 'seal', 'fly']
    right = ['camel', 'ocelot', 'brown recluse']
    l,d = pick_list_from_pools(right, wrong, 1, 5)
    print(l)
    print(d)
