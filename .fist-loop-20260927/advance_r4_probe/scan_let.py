import sys, os
sys.path.insert(0, os.getcwd())
from cypyc.parser.parser import Parser, ASTNode
from cypyc.parser.lexer import Lexer

CHILD = ('body','stmts','statements','blocks','clauses','items','fields','value','target','targets','then_body','else_body','orelse','finalbody','handlers','arms','patterns','params','args','functions','defs','init','loop','cases')

def kids(n):
    out=[]
    for f in CHILD:
        v=getattr(n,f,None)
        if isinstance(v,list):
            out+= [c for c in v if isinstance(c,ASTNode)]
        elif isinstance(v,ASTNode):
            out.append(v)
    return out

def collect(node, letnames, assigns, scopes, depth=0):
    """letnames: names bound by let (immutable) in this scope chain
       assigns: list of (name,line) assignments"""
    for c in kids(node):
        pass
    # walk statements sequentially with simple scope model
    def walk(n, letscope):
        for c in kids(n):
            k = c.kind
            if k == 'LetStmt':
                walk(c, letscope)
                nm = getattr(c,'name',None)
                if isinstance(nm,str) and not getattr(c,'mutable',True):
                    letscope = dict(letscope); letscope[nm]=c.line
            elif k == 'Assign':
                t = c.target
                nm = getattr(t,'id',None) or (t if isinstance(t,str) else None)
                if isinstance(nm,str) and nm in letscope:
                    assigns.append((nm, getattr(c,'line',0), letscope[nm]))
                walk(c, letscope)
            elif k in ('FuncDef','ClassDef','StructDef','TraitDef','ImplStmt'):
                inner={}
                walk(c, inner)
            else:
                walk(c, letscope)
    walk(node, {})

files=[]
for root in sys.argv[1:]:
    for dp,dn,fn in os.walk(root):
        if '__pycache__' in dp: continue
        for f in fn:
            if f.endswith('.cypy'): files.append(os.path.join(dp,f))
bad=[]
parsed=0
for p in sorted(files):
    try:
        src=open(p,encoding='utf-8').read()
        m=Parser(Lexer(src).tokenize()).parse()
    except Exception as e:
        continue
    parsed+=1
    a=[]
    collect(m,set(),a,{})
    if a: bad.append((p,a))
print(f'files_found={len(files)} parsed={parsed} files_with_let_reassign={len(bad)}')
tot=0
for p,a in bad:
    tot+=len(a)
    print(f'  {p}: ' + ', '.join(f'{n}@{l}(let@{dl})' for n,l,dl in a))
print('total_let_reassign_sites=',tot)
