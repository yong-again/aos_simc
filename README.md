# AoS 2D Battle Simulator

워해머 에이지 오브 지그마(AoS) 4판 룰 기반 웹 2D 미니어처 게임 시뮬레이터.
사용자가 로스터를 업로드하면 가상의 AI 상대와 맵에서 대결하는 과정을 시각화합니다.

## 구조

```
backend/               Python (FastAPI)
  app/
    factions.py        대동맹/팩션 레지스트리 + 테마 색상
    scraper/wahapedia.py   Wahapedia 워스크롤 크롤러/파서 (JSON 캐시: app/data/)
    models/roster.py   로스터 Pydantic 스키마 (Gemini response_schema 겸용)
    services/roster_parser.py  Gemini Structured Output 로스터 파싱 / AI 로스터 생성
    services/merge.py  로스터 유닛 ↔ 워스크롤 DB 이름 매칭(퍼지) 결합
    sim/combat.py      AoS4 공격 시퀀스 주사위 연산 (Hit→Wound→Save→Ward→Damage)
    sim/engine.py      전투 엔진: 이동/사격/돌격/근접 페이즈, 휴리스틱 AI, 이벤트 로그
    main.py            FastAPI 엔드포인트
frontend/              React + Vite, 2D Canvas
  src/components/      RosterInput, JsonTree, FactionSelect,
                       BattlefieldCanvas(배치 드래그앤드롭/툴팁), UnitPanel
  src/game/scale.js    인치→픽셀 물리 스케일링 (60"×44" 전장, 16px/inch)
```

## 실행

### Backend

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# backend/.env 파일에 GEMINI_API_KEY를 입력하세요 (로스터 파싱/AI 로스터 생성에 필요)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

환경 변수는 `backend/.env`(자동 로드)와 `frontend/.env`(`VITE_API_BASE`)로 관리합니다.

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 (Node 18+ 필요, nvm use 24)
```

### 워스크롤 데이터 수집 (선택)

엔드포인트 호출 시 자동으로 팩션별 크롤링 후 `backend/app/data/`에 캐시됩니다.
전체 팩션을 미리 받으려면:

```bash
cd backend && .venv/bin/python -m app.scraper.wahapedia
```

## API

| Endpoint | 설명 |
|---|---|
| `GET /api/factions` | 23개 팩션 + 대동맹/테마 색상·설명 |
| `GET /api/factions/{slug}/warscrolls` | 팩션 워스크롤 DB (`?force=true` 재크롤링) |
| `POST /api/roster/parse` | 로스터 텍스트 → JSON (Gemini) + 워스크롤 결합 |
| `POST /api/roster/parse-file` | .txt 업로드 버전 |
| `POST /api/roster/generate` | AI 상대 로스터 자동 구성 (Gemini) |
| `POST /api/setup` | 배치 UI용 유닛 uid/기본 위치 |
| `POST /api/simulate` | 전체 전투 시뮬레이션 → 이벤트 스트림 + 결과 |

## 게임 흐름

1. **Setup** — 로스터 붙여넣기/.txt 업로드 → Gemini 파싱 → JSON 트리 미리보기.
   상대 로스터는 두 방식 중 선택: 팩션 선택 → AI 자동 생성, 또는 아군과
   동일하게 텍스트 붙여넣기/.txt 업로드 → 파싱
2. **Deployment** — 아군 배치 구역(하단 12") 내 드래그 앤 드롭 배치
3. **모드 A** — 페이즈 단위 재생 (Play/Step/Next phase), 캔버스 애니메이션
4. **모드 B** — 즉시 최종 결과: 승패, 생존 유닛, 턴별 전투 기록

유닛 도형: 히어로 = 원형, 일반 유닛 = 사각형, 팩션 테마 색상.
클릭/호버 시 워스크롤 스탯·무기·어빌리티·키워드가 사이드 패널/툴팁에 표시됩니다.
