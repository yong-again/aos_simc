// Builds localized battle-log lines from the structured simulation
// events. English uses the backend-generated text as-is; Korean is
// composed here from the events' structured fields.
const STAT_KO = {
  hit: '명중',
  wound: '상처',
  save: '방어',
  ward: '워드',
  rend: '렌드',
  damage: '피해',
  move: '이동력',
  control: '통제',
  mortal_wound: '모탈 운드',
};

// roll stats: negative delta improves the target number (4+ -> 3+)
const ROLL_STATS = new Set(['hit', 'wound', 'save']);

function describeEffectKo(d) {
  const stat = STAT_KO[d.stat] || d.stat;
  if (d.mode === 'disable') {
    return `${d.ability} → ${stat} 무효화 (시전: ${d.source_name})`;
  }
  if (d.mode === 'set') {
    return `${d.ability} → ${stat} ${d.amount}+ 부여 (시전: ${d.source_name})`;
  }
  if (ROLL_STATS.has(d.stat)) {
    const dir = d.amount < 0 ? '강화' : '약화';
    return `${d.ability} → ${stat} 굴림 ${Math.abs(d.amount)} ${dir} (시전: ${d.source_name})`;
  }
  const sign = d.amount > 0 ? '+' : '';
  return `${d.ability} → ${stat} ${sign}${d.amount} (시전: ${d.source_name})`;
}

export function formatEvent(ev, names, lang) {
  const n = (uid) => names[uid] || uid;
  if (lang !== 'ko') return ev.text || null;

  switch (ev.type) {
    case 'deploy':
      return '양군 배치 완료';
    case 'round':
      return `${ev.round_no}라운드 시작 — 선공: ${ev.first === 'player' ? '아군' : '적'}`;
    case 'move':
      return `[이동] ${n(ev.uid)} → ${n(ev.target)} 방향으로 ${ev.dist}" 이동`;
    case 'charge':
      return `[돌격] ${n(ev.uid)} → ${n(ev.target)} 돌격 성공! (2D6=${ev.roll})`;
    case 'charge_failed':
      return `[돌격] ${n(ev.uid)} 돌격 실패 (2D6=${ev.roll})`;
    case 'effects':
      return `[효과] ${n(ev.uid)}: ${ev.effects.map(describeEffectKo).join('; ')}`;
    case 'attack': {
      const label =
        ev.kind === 'shoot' ? '사격' : ev.kind === 'mortal' ? '모탈' : '근접';
      if (ev.kind === 'mortal') {
        return (
          `[모탈] ${n(ev.uid)} → ${n(ev.target)}: 모탈 운드 ${ev.damage}` +
          (ev.ability ? ` (${ev.ability})` : '') +
          (ev.slain ? ` — ${n(ev.target)} 파괴!` : '')
        );
      }
      if (!ev.damage) return `[${label}] ${n(ev.uid)} → ${n(ev.target)}: 피해 없음`;
      return (
        `[${label}] ${n(ev.uid)} → ${n(ev.target)}: 피해 ${ev.damage}` +
        (ev.slain ? ` — ${n(ev.target)} 파괴!` : '')
      );
    }
    case 'end': {
      const w =
        ev.winner === 'player' ? '아군 승리' : ev.winner === 'enemy' ? '적 승리' : '무승부';
      return `전투 종료 — ${w} (잔존 포인트: 아군 ${ev.player_points} vs 적 ${ev.enemy_points})`;
    }
    default:
      return null; // phase/turn/state events carry no log line
  }
}

export function buildLog(events, names, lang) {
  const lines = [];
  for (const ev of events) {
    const line = formatEvent(ev, names, lang);
    if (line) lines.push(`[R${ev.round}] ${line}`);
  }
  return lines;
}
