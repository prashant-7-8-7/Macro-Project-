from typing import List, Dict

def reciprocal_rank_fusion(list1: List[Dict], list2: List[Dict], k: int = 60) -> List[Dict]:
    """
    Blends two ranked lists of dictionaries using Reciprocal Rank Fusion (RRF).
    Expects dictionaries to have a unique 'id'.
    Formula: RRF_score = 1 / (k + rank)
    """
    rrf_scores = {}
    items_map = {}
    
    # Process list 1 (e.g. Keyword Search)
    for rank, item in enumerate(list1):
        item_id = item['id']
        items_map[item_id] = item
        rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
        
    # Process list 2 (e.g. Semantic Search)
    for rank, item in enumerate(list2):
        item_id = item['id']
        items_map[item_id] = item
        rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
        
    # Sort by RRF score descending
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    # Reconstruct list with new rank scores
    fused_list = []
    for item_id in sorted_ids:
        item = items_map[item_id].copy()
        item['rank_score'] = rrf_scores[item_id]
        fused_list.append(item)
        
    return fused_list
