"""Campus aliases and ranked fuzzy lookup; aliases never create coordinates."""
import re
import unicodedata
from difflib import SequenceMatcher


def normalize(text):
    text=unicodedata.normalize('NFKC',text).lower()
    for typo,name in [('名远','明远'),('修院','修远'),('宏远','鸿远')]:text=text.replace(typo,name)
    digits={'一':'1','二':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','零':'0','〇':'0'}
    def number(m):
        s=m.group()
        if '十' in s:
            a,b=s.split('十',1);return str(int(digits.get(a,'1'))*10+int(digits.get(b,'0')))
        return ''.join(digits.get(c,c) for c in s)
    text=re.sub('[一二三四五六七八九零〇十]+',number,text)
    return re.sub(r'[\s·栋区号楼学生教学公寓宿舍]+','',text)


def aliases(item):
    name=item['name'];result=set(item.get('aliases',[]))
    match=re.search(r'明远教学楼([A-E])栋',name)
    if match:
        letter=match[1];number=ord(letter)-ord('A')+1
        result.update([f'明远{number}',f'明远{number}区',f'明远{letter}区',f'明远{letter}栋'])
    match=re.search(r'(修远|鸿远)教学楼([一二三四五1-5])区',name)
    if match:
        number=normalize(match[2]);result.update([f'{match[1]}{number}',f'{match[1]}{number}区',f'{match[1]}{number}号楼'])
    # Dormitories: people say "15号楼" without the park prefix; map it to the numbered building.
    match=re.search(r'^(.*?)(\d{1,2})\s*号\s*(?:学生)?(?:公寓|宿舍楼|宿舍)',name)
    if match:
        prefix,number=match.group(1).strip(),str(int(match.group(2)))
        result.update([f'{number}号楼',f'{number}栋',f'{number}号公寓'])
        if prefix:result.update([f'{prefix}{number}号楼',f'{prefix}{number}栋',f'{prefix}{number}号'])
    match=re.search(r'^教师公寓(\d{1,2})\s*#',name)
    if match:
        number=str(int(match.group(1)))
        result.update([f'教师公寓{number}号楼',f'教师公寓{number}栋',f'教师公寓{number}号',f'{number}号楼',f'{number}栋'])
    return sorted(result)


def search_places(items,query):
    key=normalize(query)
    if not key:return items[:100]
    ranked=[]
    for item in items:
        terms=[normalize(item['name'])]+[normalize(a) for a in item.get('aliases',[])]
        best=None
        for term in terms:
            if key==term:score=(0,0)
            elif term.startswith(key):score=(1,len(term)-len(key))
            elif key in term:score=(2,len(term)-len(key))
            else:
                family=next((name for name in ('修远','明远','鸿远') if key.startswith(name)),None)
                if family and any(term.startswith(name) for name in ('修远','明远','鸿远') if name!=family):continue
                ratio=SequenceMatcher(None,key,term).ratio()
                if len(key)<3 or ratio<.66:continue
                # Keep different campus buildings distinct when a number is specified.
                numbers=re.findall(r'\d+',key)
                if numbers and numbers!=re.findall(r'\d+',term):continue
                score=(3,1-ratio)
            best=min(best,score) if best is not None else score
        if best is not None:ranked.append((best,item['name'],str(item['id']),item))
    ranked.sort(key=lambda x:x[:3])
    return [x[3] for x in ranked[:100]]
