from fastapi import FastAPI, Query

from search import load_search_engine

app = FastAPI()
engine = None


def get_engine():
    global engine
    if engine is None:
        engine = load_search_engine('vector_store')
    return engine


@app.get('/search')
def search_endpoint(query: str = Query(..., description='Search query'), top_n: int = 5):
    engine = get_engine()
    results = engine.search(query, top_n)
    return {'query': query, 'results': results}
