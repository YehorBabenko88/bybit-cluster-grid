"""Bounded JSON-only values for offline VM metadata; no I/O or attestation."""
import json
import math


def check_value(value):
    stack=[(value,0)];nodes=0;chars=0
    while stack:
        item,depth=stack.pop();nodes+=1
        if nodes>4096 or depth>24:raise ValueError('VM_JSON_BUDGET_EXCEEDED')
        kind=type(item)
        if kind is dict:
            if len(item)>256:raise ValueError('VM_JSON_BUDGET_EXCEEDED')
            for key,child in item.items():
                if type(key) is not str:raise ValueError('VM_JSON_TYPE_INVALID')
                stack.append((key,depth+1));stack.append((child,depth+1))
        elif kind is list:
            if len(item)>256:raise ValueError('VM_JSON_BUDGET_EXCEEDED')
            stack.extend((child,depth+1) for child in item)
        elif kind is str:
            chars+=len(item)
            if chars>65536 or any(0xD800<=ord(c)<=0xDFFF for c in item):
                raise ValueError('VM_JSON_TEXT_INVALID')
        elif kind is int:
            if item.bit_length()>256:raise ValueError('VM_JSON_NUMBER_INVALID')
        elif kind is float:
            if not math.isfinite(item):raise ValueError('VM_JSON_NONFINITE')
        elif kind not in (bool,type(None)):
            raise ValueError('VM_JSON_TYPE_INVALID')
    return value


def load(raw):
    if type(raw) is not str or len(raw)>65536:raise ValueError('VM_JSON_SIZE_INVALID')
    try:
        if len(raw.encode('utf-8'))>65536:raise ValueError('VM_JSON_SIZE_INVALID')
    except UnicodeError:raise ValueError('VM_JSON_TEXT_INVALID') from None
    # Bound nesting BEFORE entering the recursive stdlib parser, respecting strings.
    depth=0;quoted=False;escaped=False
    for c in raw:
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c in '[{':
            depth+=1
            if depth>24:raise ValueError('VM_JSON_BUDGET_EXCEEDED')
        elif c in ']}':depth-=1
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('VM_JSON_DUPLICATE_KEY')
            result[key]=value
        return result
    def number(text):
        if len(text)>80:raise ValueError('VM_JSON_NUMBER_INVALID')
        return int(text)
    def constant(_):raise ValueError('VM_JSON_NONFINITE')
    try:
        return check_value(json.loads(raw,object_pairs_hook=pairs,parse_int=number,parse_constant=constant))
    except (RecursionError,json.JSONDecodeError):raise ValueError('VM_JSON_INVALID') from None


def canonical(value):
    check_value(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
