import { createContext, useContext, useState } from 'react';

// Lightweight i18n: UI chrome strings in English and Korean.
// Backend battle-log text stays in English; faction descriptions come
// localized from the API (description / description_ko).
const STRINGS = {
  en: {
    appTitle: 'AoS 2D Battle Simulator',
    newBattle: 'New battle',
    // roster input
    pasteYourRoster: '1. Paste your roster',
    pasteOpponentRoster: '2. Paste opponent roster',
    rosterPlaceholder: 'Paste plain-text roster from New Recruit / army builder…',
    uploadTxt: 'Upload .txt',
    loadSample: 'Load sample',
    parseRoster: 'Parse roster',
    parsing: 'Parsing…',
    parsedPreview: 'Parsed roster preview',
    opponentRoster: 'Opponent roster',
    // opponent source
    generateWithAI: '🤖 Generate with AI',
    pasteOpponent: '📋 Paste opponent roster',
    chooseFaction: '2. Choose AI opponent faction',
    grandAlliance: 'Grand Alliance',
    points: 'Points',
    generateRoster: 'Generate AI opponent roster',
    generating: 'Generating…',
    proceedDeploy: 'Proceed to deployment →',
    // deployment / battle
    deployment: 'Deployment',
    deployHint: 'drag your units (blue zone), then choose a mode:',
    modeA: '▶ Mode A: Turn-by-turn',
    modeB: '⏩ Mode B: Fast result',
    round: 'Round',
    play: '▶ Play',
    pause: '⏸ Pause',
    step: 'Step',
    nextPhase: 'Next phase',
    skipToResult: 'Skip to result',
    speed: 'Speed',
    yourTurn: 'Your turn',
    enemyTurn: 'Enemy turn',
    your: 'Your',
    enemy: 'Enemy',
    battleOver: 'Battle over',
    firstLabel: 'first',
    phase_movement: 'Movement Phase',
    phase_shooting: 'Shooting Phase',
    phase_charge: 'Charge Phase',
    phase_combat: 'Combat Phase',
    // unit panel / tooltip
    unitDetails: 'Unit details',
    unitHint: 'Hover or click a unit on the battlefield.',
    yourArmy: 'Your army',
    aiOpponent: 'AI opponent',
    yourUnit: 'Your unit',
    enemyUnit: 'Enemy',
    move: 'Move',
    health: 'Health',
    save: 'Save',
    control: 'Control',
    rangedWeapons: 'Ranged weapons',
    meleeWeapons: 'Melee weapons',
    abilities: 'Abilities',
    models: 'models',
    model: 'model',
    pts: 'pts',
    clickForWarscroll: 'Click for full warscroll',
    // result
    victory: '🏆 Victory!',
    defeat: '💀 Defeat',
    draw: '🤝 Draw',
    battleLasted: (n) => `Battle lasted ${n} round(s).`,
    yourSurvivors: 'Your survivors',
    enemySurvivors: 'Enemy survivors',
    wipedOut: 'Wiped out',
    battleLog: 'Battle log',
  },
  ko: {
    appTitle: 'AoS 2D 전투 시뮬레이터',
    newBattle: '새 전투',
    // roster input
    pasteYourRoster: '1. 내 로스터 붙여넣기',
    pasteOpponentRoster: '2. 상대 로스터 붙여넣기',
    rosterPlaceholder: 'New Recruit 등 아미 빌더에서 복사한 텍스트 로스터를 붙여넣으세요…',
    uploadTxt: '.txt 업로드',
    loadSample: '샘플 불러오기',
    parseRoster: '로스터 파싱',
    parsing: '파싱 중…',
    parsedPreview: '파싱된 로스터 미리보기',
    opponentRoster: '상대 로스터',
    // opponent source
    generateWithAI: '🤖 AI로 생성',
    pasteOpponent: '📋 상대 로스터 붙여넣기',
    chooseFaction: '2. AI 상대 팩션 선택',
    grandAlliance: '대동맹',
    points: '포인트',
    generateRoster: 'AI 상대 로스터 생성',
    generating: '생성 중…',
    proceedDeploy: '배치 단계로 →',
    // deployment / battle
    deployment: '배치',
    deployHint: '아군 유닛을 파란 구역에 드래그한 뒤 모드를 선택하세요:',
    modeA: '▶ 모드 A: 턴 단위 진행',
    modeB: '⏩ 모드 B: 빠른 결과',
    round: '라운드',
    play: '▶ 재생',
    pause: '⏸ 일시정지',
    step: '한 단계',
    nextPhase: '다음 페이즈',
    skipToResult: '결과 보기',
    speed: '속도',
    yourTurn: '내 턴',
    enemyTurn: '상대 턴',
    your: '아군',
    enemy: '적',
    battleOver: '전투 종료',
    firstLabel: '선공',
    phase_movement: '이동 페이즈',
    phase_shooting: '사격 페이즈',
    phase_charge: '돌격 페이즈',
    phase_combat: '근접 전투 페이즈',
    // unit panel / tooltip
    unitDetails: '유닛 정보',
    unitHint: '전장의 유닛에 마우스를 올리거나 클릭하세요.',
    yourArmy: '내 군대',
    aiOpponent: 'AI 상대',
    yourUnit: '아군 유닛',
    enemyUnit: '적 유닛',
    move: '이동',
    health: '체력',
    save: '방어',
    control: '통제',
    rangedWeapons: '원거리 무기',
    meleeWeapons: '근접 무기',
    abilities: '어빌리티',
    models: '모델',
    model: '모델',
    pts: '포인트',
    clickForWarscroll: '클릭하면 전체 워스크롤 표시',
    // result
    victory: '🏆 승리!',
    defeat: '💀 패배',
    draw: '🤝 무승부',
    battleLasted: (n) => `전투는 ${n}라운드 동안 진행되었습니다.`,
    yourSurvivors: '아군 생존 유닛',
    enemySurvivors: '적 생존 유닛',
    wipedOut: '전멸',
    battleLog: '전투 기록',
  },
};

const LangContext = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(
    () => localStorage.getItem('lang') || 'ko'
  );
  const setLang = (l) => {
    localStorage.setItem('lang', l);
    setLangState(l);
  };
  const t = (key, ...args) => {
    const v = STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
    return typeof v === 'function' ? v(...args) : v;
  };
  return (
    <LangContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LangContext.Provider>
  );
}

export const useLang = () => useContext(LangContext);
