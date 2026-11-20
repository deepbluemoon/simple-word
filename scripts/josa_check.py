import json,re,sys
# 목적격 조사 을/를만: 받침 있으면 '을', 없으면 '를'. 앞 글자가 한글이고 뒤가 공백·문장부호인 경우.
R=re.compile(r"([가-힣])(을|를)(?=[\s,.!?·)]|$)")
def errs(t):
    n=0
    for ch,j in R.findall(t):
        if ch+j=="마을": continue
        bat=(ord(ch)-0xAC00)%28!=0
        n+= (bat and j=="를") or (not bat and j=="을")
    return n
PH=re.compile(r"<[A-Z]+\d*>|\[[A-Z]+_?\d+\]|⟨|⟩")
for f in sys.argv[1:]:
    rows=[json.loads(l) for l in open(f)]
    e=sum(errs(r["out"])>0 for r in rows); s=sum(errs(r["src"])>0 for r in rows); p=sum(bool(PH.search(r["out"])) for r in rows)
    print(f.split('/')[-1], len(rows), e, round(e/len(rows),4), "src", s, "ph_left", p)
