import json,sys,time,urllib.request,re
SAMPLES=[
"본 사업은 관내 거주 만 65세 이상 기초생활수급자를 대상으로 하며, 신청을 희망하는 자는 구비서류를 지참하여 주소지 관할 행정복지센터에 방문 접수하여야 합니다.",
"과태료 부과 사전통지서를 송달받은 날부터 20일 이내에 의견제출 기한 내 자진납부 시 과태료의 100분의 20에 해당하는 금액을 감경합니다.",
"동절기 수도계량기 동파 방지를 위하여 계량기함 내부를 보온재로 충전하여 주시기 바라며, 동파 발생 시 수용가 부담으로 교체됨을 알려드립니다.",
]
PROMPT="""다음 공문서 문장을 초등학생도 이해할 수 있는 쉬운 한국어로 바꿔 주세요.
규칙: 어려운 한자어·법률 용어는 쉬운 말로 풀기, 문장은 짧게, 숫자·날짜·대상·조건 같은 정보는 빠짐없이 유지, 설명이나 머리말 없이 바꾼 문장만 출력.
원문: {x}
쉬운 말:"""
def gen(model,x):
    body=json.dumps({"model":model,"prompt":PROMPT.format(x=x),"stream":False,"think":False,"options":{"temperature":0.2,"num_predict":400}}).encode()
    r=urllib.request.Request("http://localhost:11434/api/generate",body,{"Content-Type":"application/json"})
    t=time.time(); d=json.load(urllib.request.urlopen(r,timeout=600)); 
    tps=d.get("eval_count",0)/max(d.get("eval_duration",1)/1e9,1e-9)
    return d["response"].strip(), time.time()-t, tps
out=[]
for m in sys.argv[1:]:
    gen(m,"안녕")  # warm-up
    for i,x in enumerate(SAMPLES):
        y,sec,tps=gen(m,x); y=re.sub(r'<think>.*?</think>','',y,flags=re.S).strip()
        out.append({"model":m,"i":i,"sec":round(sec,1),"tok_s":round(tps,1),"out":y}); print(json.dumps(out[-1],ensure_ascii=False),flush=True)
