from .forms import SelMultStatic as SMS, SelOneStatic as SOS
from functools import partial
from random import shuffle
from re import sub, findall, escape

# since choice_lst is hidden in true_false_fact
TRUE = 1
FALSE = 0

def eval_expression(expr, globs, locs):
    return eval(expr, globs, locs)

# expect qstring to look like 'If {{p[0]}} has $5 and {{p[1]}} has $10, who has more?'
# expect answer_lst to look like "['p[1]', 'George',...]"
# var_lst_dct looks like "{'lst1':[...], 'lst2':[...],...}". lists should contain strings
# returns randomized, parsed string, list of correct answers, and elements used
def parse_spec_to_qa(qstring, var_lst_dct, answer_lst):
    strip_patt = r'({{([^}{]*)}})'
    extract_patt = r'(\w+)\[(\d+)\]'
    cvar_lst_dct = var_lst_dct.copy() #don't clobber arg
    for lst in cvar_lst_dct.values():
        shuffle(lst)
    usedset = set()
    raw_kern_lst = findall(strip_patt, qstring)
    # question
    for pair in raw_kern_lst:
        raw, kern = pair
        key_idx_lst = findall(extract_patt, kern)
        if not key_idx_lst:
            aretlist.append(kern)
            usedset.add(kern)
            continue
        key, idx = key_idx_lst[0]
        elem = cvar_lst_dct[key][int(idx)]
        if key.endswith('_xpr'):
            elem = str(eval_expression(elem, globals(), locals()))
        qstring = sub(escape(raw), elem, qstring)
        usedset.add(elem)
    # answer
    aretlist = []
    for kern in answer_lst:
        key_idx_lst = findall(extract_patt, kern)
        if not key_idx_lst:
            aretlist.append(kern)
            usedset.add(kern)
            continue
        key, idx = key_idx_lst[0]
        elem = cvar_lst_dct[key][int(idx)]
        if key.endswith('_xpr'):
            elem = str(eval_expression(elem, globals(), locals()))
        kern = sub(escape(kern), elem, kern)
        usedset.add(elem)
        aretlist.append(kern)
    usedlst = [a for a in usedset]
    return qstring, aretlist, usedlst

# list of words -> list of indices from full list
def get_indices_from_elems(result_elem_lst, right_elem_lst):
    ret_idx_lst = []    
    for elem in right_elem_lst:
        if elem in result_elem_lst:
           ret_idx_lst.append(result_elem_lst.index(elem))
    return sorted(ret_idx_lst)

# pass in list of elements and desired result list length--n 
# return random selection of elements in a list of desired length
def pick_rand_n_from_list(pool, result_size):
    clst = pool.copy() #don't clobber arg
    shuffle(clst)
    return clst[:result_size]

# pass in wrongpool list of elements and rightpool list of elements
# pass in desired return list size--result_size
# pass in number desired from rightpool--right_size
# return a list of size result_size with right_size right elements and remainder wrong elements
# also return list of correct answer indices in return list
def pick_rand_n_from_list_with_answer(wrongpool, rightpool, result_size, right_size=1): 
    wpc = wrongpool.copy() #don't clobber argument
    rpc = rightpool.copy() #don't clobber argument
    shuffle(wpc)
    shuffle(rpc)
    rights = rpc[:right_size]
    wrongs = wpc[:result_size-right_size]
    ret_final_lst = rights + wrongs
    shuffle(ret_final_lst)
    ret_correct_idx_lst = [ret_final_lst.index(a) for a in rights]
    return {'all':ret_final_lst, 'correct':sorted(ret_correct_idx_lst)}

# returns form containing question, answer, selfield (select-one field)
def select_one_static_form_factory(question, choice_lst, answer_idx, *args, **kwargs):
    form = SOS()
    form.question=question 
    form.answer=answer_idx
    form.selfield.choices = [(b,a) for b,a in enumerate(choice_lst)]
    return form

# returns form containing question, answer, selfield (select-many field)
def select_multiple_static_form_factory(question, choice_lst, answer_idx_lst, *args, **kwargs):
    form = SMS()
    form.question=question
    form.answer=answer_idx_lst
    form.selfield.choices = [(b,a) for b,a in enumerate(choice_lst)]
    return form

# for True/False (use TRUE and FALSE in call, for convenience)
true_false_static_form_factory = partial(select_one_static_form_factory, choice_lst = ['False', 'True'])

