"""Versioned, deterministic local text indexing. No model, database or transport."""
from collections import Counter
import math,re
from base.app.companion.assets.references import digest

VERSION='local-text-index.1'
TOKENIZER='english-word-cjk-1-2gram.1'
METHODS=['literal.v1','bm25.v1']

def tokens(text):
    result=re.findall(r'[a-z0-9]+',text.casefold())
    for run in re.findall(r'[\u3400-\u9fff]+',text):
        result.extend(run);result.extend(run[i:i+2] for i in range(len(run)-1))
    return result

def chunks(text,size,overlap):
    for start in range(0,len(text),size-overlap):
        end=min(start+size,len(text))
        if text[start:end].strip():yield start,end,text[start:end]
        if end==len(text):break

def config(size=700,overlap=100):
    return {'implementation':VERSION,'tokenizer':TOKENIZER,'chunk_characters':size,'overlap_characters':overlap,
            'methods':METHODS,'bm25':{'k1':1.2,'b':0.75},'embedding':None,
            'model_dependency':'none; changing the language model does not reinterpret this index'}

def rank(documents,query,method,k):
    if method not in METHODS:raise ValueError('Unsupported retrieval method')
    rows=[(doc,part) for doc in documents for part in doc['chunks']]
    terms=set(tokens(query));frequency=Counter();lengths=[];counts=[]
    for _,part in rows:
        c=Counter(tokens(part['text']));counts.append(c);lengths.append(sum(c.values()));frequency.update(c.keys())
    average=sum(lengths)/max(len(rows),1);matches=[]
    for i,(doc,part) in enumerate(rows):
        if method=='literal.v1':score=float(part['text'].casefold().count(query.casefold()))
        else:
            score=0.
            for term in terms:
                tf=counts[i][term]
                if tf:
                    # Positive IDF BM25; Robertson/Zaragoza, DOI 10.1561/1500000019.
                    idf=math.log(1+(len(rows)-frequency[term]+.5)/(frequency[term]+.5))
                    score+=idf*tf*2.2/(tf+1.2*(.25+.75*lengths[i]/max(average,1)))
        if score>0:matches.append((score,doc['key'],part['start'],doc,part))
    matches.sort(key=lambda x:(-x[0],x[1],x[2]))
    results=[];seen=set()
    for score,_,_,doc,part in matches:
        if doc['key'] in seen:continue
        seen.add(doc['key'])
        results.append({'document_key':doc['key'],'title':doc['title'],'text':part['text'],'score':round(score,6),
            'source_ref':{**doc['source_ref'],'start':part['start'],'end':part['end']},'kind':doc['kind'],
            'quality':doc['quality'],'source':doc['source']})
        if len(results)==k:break
    return results

def document_key(source):
    return next(prefix+source[field] for prefix,field in [('material:','material_id'),('page:','page_id'),('task:','task_id')] if source.get(field))

def content_identity(documents,cfg,scope):
    return digest({'scope':scope,'config':cfg,'sources':[{k:d[k] for k in ['key','source_ref','text_hash']} for d in documents]})
