# Project Overview

워해머 에이지 오브 지그마(AoS) 4판 룰을 기반으로 하는 웹 기반 2D 미니어처 게임 시뮬레이터를 개발합니다. 사용자가 로스터를 업로드하면, 가상의 AI 상대와 맵에서 대결하는 과정을 시각적으로 보여줍니다.

# Data Sources (Critical)

게임 룰과 유닛 스탯은 반드시 다음 웹사이트의 데이터를 파싱하거나 참조하여 게임 로직에 반영해야 합니다.

- 유닛 워스크롤 및 스탯: https://wahapedia.ru/aos4/factions/{팩션명}/warscrolls.html
- 게임 코어 룰: https://wahapedia.ru/aos4/the-rules/the-core-rules/

# Grand Alliances & Factions

에이지 오브 지그마의 세계관은 4개의 대동맹과 하위 팩션으로 이루어져 있습니다. UI의 팩션 선택 메뉴를 구성하거나 진영별 도형의 고유 테마 색상을 설정할 때 다음의 분류를 반드시 적용하세요.

1. Order (질서와 문명): Stormcast Eternals, Cities of Sigmar, Seraphon, Sylvaneth
2. Chaos (혼돈과 파괴): Blades of Khorne, Disciples of Tzeentch, Maggotkin of Nurgle, Hedonites of Slaanesh, Skaven
3. Death (죽음과 영혼): Ossiarch Bonereapers, Soulblight Gravelords, Nighthaunt
4. Destruction (야만과 본능): Ironjawz, Kruleboyz, Gloomspite Gitz, Ogor Mawtribes

# Tech Stack

- Backend: Python
- Frontend: React.js (배치 및 이동 시각화를 위한 2D Canvas API 활용)
- AI & NLP: 상대 로스터 자동 구성 및 데이터 정제에 Google Gemini API 사용

# Core Features & Requirements

1. 로스터 입력 및 Text-to-JSON 파싱

- 인터페이스: 사용자는 'New Recruit' 등 아미 빌더 앱에서 복사한 순수 텍스트(Plain Text) 형태의 로스터를 프론트엔드의 텍스트 에어리어(Text Area)에 직접 붙여넣거나 .txt 파일로 업로드할 수 있어야 합니다.
- 데이터 파싱: 파이썬 백엔드는 전달받은 비정형 텍스트를 Google Gemini API를 활용하여 정형화된 JSON 객체로 변환(Parsing)해야 합니다.
- 파싱 시 목표로 하는 JSON 스키마 구조는 다음과 같이 계층적으로 구성하세요: { "army_name": "string", "faction": "string", "total_points": "number", "regiments": [ { "hero": { "name": "string", "points": "number", "is_general": "boolean", "options": ["string"] }, "units": [ { "name": "string", "points": "number", "options": ["string"], "is_reinforced": "boolean" } ] } ], "auxiliaries": [], "faction_terrain": "string" }
- 데이터 매핑: 텍스트에서 JSON으로 파싱이 완료되면, 추출된 각 유닛의 이름(name)을 기반으로 Wahapedia에서 수집한 워스크롤 DB와 매칭하여 이동력, 체력, 방어력, 무기 스탯 등의 실질적인 게임 데이터를 해당 유닛 객체에 결합(Merge)하세요.

2. UI 및 유닛 표시 (인터페이스)

- 유닛은 2D 도형(원형 또는 사각형)으로 맵에 렌더링됩니다.
- 각 도형은 소속된 대동맹(Order, Chaos, Death, Destruction)과 팩션을 상징하는 고유의 테마 색상으로 칠해져야 합니다.
- 유닛 도형을 클릭하거나 마우스를 올리면 수집된 해당 유닛의 세부 스탯과 보유 기술이 툴팁이나 사이드 패널에 표시되어야 합니다.

3. 전장 맵 및 배치 (Deployment)

- 실제 게임의 인치(inch) 단위를 화면의 픽셀(px) 단위로 변환하는 물리적 스케일링 로직을 구현하세요.
- 게임 시작 전, 사용자가 마우스 드래그 앤 드롭으로 아군 배치 구역 내에 유닛을 자유롭게 배치할 수 있는 기능을 제공하세요.

4. 시뮬레이터 실행 모드

- 모드 A (턴 단위 진행): 이동, 사격, 돌격, 근접 전투 페이즈를 1턴씩 끊어서 시각적으로 유닛이 움직이고 공격하는 과정을 보여줍니다.
- 모드 B (빠른 결과): 애니메이션을 생략하고 즉시 게임 종료 시점까지 백엔드에서 시뮬레이션한 뒤, 최종 결과(승패, 남은 유닛)와 각 턴의 주요 전투 기록을 텍스트로 출력합니다.

5. 전투 및 AI 로직

- 전투 결과는 Wahapedia 코어 룰을 바탕으로 확률 기반 연산 또는 몬테카를로 시뮬레이션을 적용해 데미지를 계산합니다.
- AI 상대는 거리 계산을 통해 가장 가까운 적을 향해 이동하고 사거리 내에서 공격을 수행하는 기본 휴리스틱 알고리즘으로 작동합니다.

# Instructions for Claude Code

- 먼저 Wahapedia URL 구조를 분석하여 워스크롤 데이터를 파이썬 백엔드로 가져오는 크롤링 및 파싱 로직부터 설계하세요.
- 데이터가 준비되면 프론트엔드 캔버스 렌더링, 팩션 선택 메뉴 및 배치 시스템, 턴 진행 상태 관리, 전투 연산 로직 순으로 개발을 진행해 주세요.
- 로스터 텍스트를 처리할 때, Gemini API의 Structured Output(또는 response_schema) 기능을 사용하여 텍스트가 항상 일관된 Pydantic 모델 형태의 JSON으로 반환되도록 백엔드 파싱 유틸리티를 작성하세요. 
- 텍스트 입력 창과 파싱 결과를 트리 구조로 미리보기 할 수 있는 UI 패널을 프론트엔드에 구성해 주세요.