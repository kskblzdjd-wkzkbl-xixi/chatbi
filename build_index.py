from rag_corpus import CORPUS
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
emb = OllamaEmbeddings(model='bge-m3',base_url='http://127.0.0.1:11434')
texts = [c['text'] for c in CORPUS]
metas = [{'source': c['source'],'topic': c['topic']} for c in CORPUS]
print('正在向量化 22 段语料（首次较慢，勿中断）...')
store = FAISS.from_texts(texts,emb,metadatas=metas)
store.save_local('rag_index')
print('已保存 rag_index/ 索引')
probes = [
    ("合同变更了钱怎么算？", "签证/变更"),
    ("甲方拖着不确认工程量怎么办？", "三方确认"),
    ("哪些付款必须领导签字才能走？", "签证/审批"),
    ("怎么防止对方虚开发票？", "发票管理"),
    ("为什么总价对不上不含税的数？", "税金计算"),
]
for q, expect in probes:
    hits = store.similarity_search_with_score(q,k=3)
    print(f'\n[刁钻题] {q} (应命中：{expect})')
    for i,(doc,score) in enumerate(hits,1):
        print(f"  top{i}: {doc.metadata['topic']} | 得分{score:.3f} | {doc.page_content[:40]}...")


