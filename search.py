import logging
from typing import List, Dict

from utils.embedding import embed_text, EMBED_DIM
from vector_store import VectorStore

logging.basicConfig(level=logging.INFO)


class SearchEngine:
    def __init__(self, store: VectorStore):
        self.store = store

    def search(self, query: str, top_n: int = 5) -> List[Dict]:
        logging.info('Search query: %s', query)
        vector = embed_text(query)
        results = self.store.search(vector, top_n)
        output: List[Dict] = []
        for score, meta in results:
            output.append({
                'score': score,
                'text': meta['text'],
                'citation': {
                    'filename': meta['filename'],
                    'page_number': meta['page_number'],
                    'lines': [meta['line_start'], meta['line_end']],
                },
            })
        return output


def load_search_engine(store_path: str) -> SearchEngine:
    store = VectorStore.load(store_path)
    return SearchEngine(store)
