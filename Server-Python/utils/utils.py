from __future__ import annotations

import logging
from typing import Dict, Any
from memory.session_memory import SessionMemory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 💡 핵심 수학 연산 기능 (NeedScore 계산 및 최적 Entity 추출)
# ---------------------------------------------------------------------------
async def calculate_score(entities_output: Dict[str, Any], client_id: str, memory: "SessionMemory") -> Dict[str, Any]:
    """
    Step 2의 JSON 결과를 받아 각 Entity의 NeedScore를 계산하고,
    가장 높은 점수를 가진 단일 Entity를 최종 타겟으로 선정합니다.
    
    수식: NeedScore = Priority * (1 - Shared_Knowledge)
    """
    # logger.debug(f"Calculating NeedScore for Step 2 output: {entities_output}")
    
    entities_list = entities_output.get("candidate_entities", [])
    
    # 예외 처리: 데이터가 비어있거나 올바르지 않은 구조일 때
    if not entities_list:
        return {"selected_target": None, "score": 0.0, "reason": "No entities provided"}
    
    # 단일 dict 형태로 들어왔을 경우를 대비해 list로 감싸줍니다.
    if isinstance(entities_list, dict):
        entities_list = [entities_list]

    best_entity = None
    max_need_score = -1.0

    entity_memory = memory.get_entity_memory()

    for item in entities_list:
        entity_name = item.get("entity")
        relevance = float(item.get("relevance", 0.0))
        dependency = float(item.get("dependency", 0.0))
        benefit = float(item.get("benefit", 0.0))
        familiarity = float(item.get("familiarity", 0.0))
        difficulty = float(item.get("difficulty", 0.0))
        history = check_entity_memory(entity_memory=entity_memory, entity=entity_name, client_id=client_id)

        priority = (relevance + dependency + benefit)/3
        shared_knowledge = (1.0 - (familiarity + (1-difficulty))/2) * history 
        need_score = priority + shared_knowledge
        
        if need_score > max_need_score:
            max_need_score = need_score
            best_entity = {
                "selected_target": entity_name,
                "score": round(need_score, 4),
                "debug_info": {
                    "priority": priority,
                    "shared_knowledge": shared_knowledge
                }
            }
            
    # logger.info(
    #             f"[{client_id}] [Utils] "
    #             f"Selected Target Entity: {best_entity}"
    #         )
    return best_entity or {"selected_target": None, "score": 0.0}

def check_entity_memory(entity_memory: list[str], entity:str, client_id: str) -> int:
    """
    Check if the entity is already in the entity memory.
    """
    for entity_memory_entry in entity_memory:
        logger.debug(f"[{client_id}] [Utils] Entity '{entity}' Entity memory: {entity_memory_entry}")
        if entity.replace(" ", "") == entity_memory_entry.replace(" ", ""):
            logger.info(
                        f"[{client_id}] [Utils] "
                        f"Entity '{entity}' is already in entity memory"
                    )
            return 0 # explained

    return 1 # not explained
        
def save_entity(entity: str, client_id: str, memory: "SessionMemory") -> None:
    """
    Save entity to the shared session entity memory.
    """
    memory.add_entity_memory(entity)