"""Machine-readable ability schema.

Used as the Gemini ``response_schema`` when converting scraped
plain-text warscroll abilities into structured buff/debuff parameters
that the combat engine can apply automatically.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AbilityModifier(BaseModel):
    stat: str = Field(
        description="'hit', 'wound', 'rend', 'damage', 'save', 'ward', "
        "'move', 'mortal_wound', 'control' 중 하나"
    )
    modifier_type: str = Field(
        description="'add', 'subtract', 'set', 'inflict' 중 하나 "
        "(예: 명중 1증가면 add, 모탈뎀 1점이면 inflict)"
    )
    value: str = Field(description="'1', 'D3', 'D6' 등 변화하는 수치")
    target_type: str = Field(
        description="'self', 'enemy_in_combat', 'enemy_within_12', "
        "'friendly_within_12' 중 하나"
    )
    condition: Optional[str] = Field(
        default=None,
        description="발동 조건. 예: 'if charged this turn'. 없으면 null",
    )


class StructuredAbility(BaseModel):
    name: str = Field(description="어빌리티의 원래 이름")
    activation_type: str = Field(
        description="상시 적용이면 'passive', 특정 시점에 선택해서 발동하면 'active'"
    )
    timing: str = Field(
        description="'any_phase', 'hero_phase', 'movement_phase', "
        "'shooting_phase', 'charge_phase', 'combat_phase', 'end_of_turn' 중 하나"
    )
    modifiers: List[AbilityModifier] = Field(
        description="이 어빌리티가 유발하는 스탯 변화들의 목록"
    )
