// Builds localized battle-log lines from the structured simulation
// events. English uses the backend-generated text as-is; Korean is
// composed here from the events' structured fields.
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
    case 'attack': {
      const label = ev.kind === 'shoot' ? '사격' : '근접';
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
