// Builds localized battle-log lines from the structured simulation
// events. English uses the backend-generated text as-is; Korean is
// composed here from the events' structured fields.
//
// Every event carries a `category` (PHASE/HERO/MOVE/SHOOT/CHARGE/COMBAT/
// DEFENSE/EFFECT/SYSTEM) which the UI uses for per-line colors/icons.
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

const PHASE_KO = {
  hero: '히어로 페이즈',
  movement: '이동 페이즈',
  shooting: '사격 페이즈',
  charge: '돌격 페이즈',
  combat: '근접 전투 페이즈',
  end: '종료 페이즈',
};

// roll stats: negative delta improves the target number (4+ -> 3+)
const ROLL_STATS = new Set(['hit', 'wound', 'save']);

function describeEffectKo(d) {
  const stat = STAT_KO[d.stat] || d.stat;
  if (d.mode === 'disable') {
    return `${d.ability} → ${stat} 무효화 (시전: ${d.source_name})`;
  }
  if (d.mode === 'set') {
    const shown = ['ward', 'save', 'hit', 'wound'].includes(d.stat)
      ? `${d.amount}+`
      : d.amount;
    return `${d.ability} → ${stat} = ${shown} (시전: ${d.source_name})`;
  }
  if (ROLL_STATS.has(d.stat)) {
    const dir = d.amount < 0 ? '강화' : '약화';
    return `${d.ability} → ${stat} 굴림 ${Math.abs(d.amount)} ${dir} (시전: ${d.source_name})`;
  }
  const sign = d.amount > 0 ? '+' : '';
  return `${d.ability} → ${stat} ${sign}${d.amount} (시전: ${d.source_name})`;
}

// applied-effect suffix on attack lines, signs flipped for display
// (internal hit -1 = easier roll = shown as 명중+1)
function appliedSuffixKo(applied) {
  if (!applied?.length) return '';
  const parts = applied.map((d) => {
    const shown = ROLL_STATS.has(d.stat) ? -d.amount : d.amount;
    const sign = shown > 0 ? '+' : '';
    return `'${d.ability}' ${STAT_KO[d.stat] || d.stat}${sign}${shown}`;
  });
  return ` (적용 효과: ${parts.join(', ')})`;
}

export function formatEvent(ev, names, lang) {
  const n = (uid) => names[uid] || uid;
  // silent events exist only to drive canvas animation (e.g. the move
  // that follows a Redeploy command) — the command line is the log
  if (ev.silent) return null;
  if (lang !== 'ko') return ev.text || null;

  switch (ev.type) {
    case 'deploy':
      return '양군 배치 완료';
    case 'round': {
      const ud = ev.underdog
        ? ` (언더독 ${ev.underdog === 'player' ? '아군' : '적'} +1 CP)`
        : '';
      return `${ev.round_no}라운드 시작 — 선공: ${ev.first === 'player' ? '아군' : '적'}${ud}`;
    }
    case 'phase': {
      const side = ev.side === 'player' ? '아군' : '적';
      return `=== [R${ev.round}] ${side} ${PHASE_KO[ev.phase] || ev.phase} ===`;
    }
    case 'move':
      return `[이동] ${n(ev.uid)} → ${n(ev.target)} 방향으로 ${ev.dist}" 이동`;
    case 'retreat':
      return (
        `[후퇴] ${n(ev.uid)} 전투 이탈 — 모탈 피해 ${ev.damage}` +
        (ev.slain ? ` — ${n(ev.uid)} 파괴!` : '')
      );
    case 'cast':
      if (!ev.success && ev.roll < ev.needed) {
        return `[마법] ${n(ev.uid)} 아케인 볼트 시전 실패 (2D6=${ev.roll}, 필요 ${ev.needed}+)`;
      }
      return (
        `[마법] ${n(ev.uid)} → ${n(ev.target)}: 아케인 볼트 시전 (2D6=${ev.roll})` +
        (ev.success ? '' : ' — 언바인드됨')
      );
    case 'miscast':
      return (
        `[미스캐스트 발생!] ${n(ev.uid)} 주사위 1이 2개 (${ev.dice.join(',')}) — ` +
        `모탈 피해 ${ev.damage}, 이번 페이즈 시전 불가` +
        (ev.slain ? ` — ${n(ev.uid)} 파괴!` : '')
      );
    case 'unbind':
      return (
        `[언바인드] ${n(ev.uid)} 시전 방해 시도 (2D6=${ev.roll} vs ${ev.against}) — ` +
        (ev.success ? '성공!' : '실패')
      );
    case 'chant': {
      if (ev.roll === 1 && !ev.success) {
        return `[기도] ${n(ev.uid)} 챈팅 실패 (1D6=1) — 의식 포인트 ${ev.lost} 상실 (잔여 ${ev.points})`;
      }
      if (ev.success) {
        const parts = [`1D6=${ev.roll}${ev.bonus ? `+${ev.bonus}` : ''}`];
        if (ev.spent) parts.push(`의식 포인트 ${ev.spent} 소모`);
        return `[기도] ${n(ev.uid)} '${ev.prayer}' 발동! (${parts.join(', ')})`;
      }
      return `[기도] ${n(ev.uid)} 의식 포인트 누적 (1D6=${ev.roll}, 합계 ${ev.points})`;
    }
    case 'summon':
      return ev.success
        ? `[소환] ${n(ev.uid)} → '${ev.manifestation}' 소환 성공 (시전 ${ev.roll})`
        : `[소환] ${n(ev.uid)} '${ev.manifestation}' 소환 실패 (시전 ${ev.roll}, 필요 ${ev.needed}+)`;
    case 'banish':
      return (
        `[추방] ${n(ev.uid)} → ${n(ev.target)} 추방 시도 ` +
        `(2D6=${ev.roll}${ev.bonus ? `+${ev.bonus}` : ''} vs ${ev.needed}) — ` +
        (ev.success ? '추방됨!' : '잔존')
      );
    case 'manifestation_removed': {
      const REASON_KO = {
        banished: '추방됨',
        'its summoner was slain': '소환자 사망',
      };
      return `[소환물 제거] ${n(ev.uid)} (${REASON_KO[ev.reason] || ev.reason})`;
    }
    case 'terrain_power':
      if (ev.damage !== undefined && ev.roll === 1) {
        return (
          `[지형] ${n(ev.uid)} Place of Power 역류 (D6=1) — 모탈 피해 ${ev.damage}` +
          (ev.slain ? ` — ${n(ev.uid)} 파괴!` : '')
        );
      }
      return (
        `[지형] ${n(ev.uid)} Place of Power 공명 (D6=${ev.roll}) — ` +
        (ev.buff === 'plus1' ? '이번 턴 시전/챈팅 +1' : '이번 턴 WIZARD(1) 취급 (언바인드/추방 가능)')
      );
    case 'cover':
      return `[지형] ${n(ev.uid)} 엄폐 중 (${ev.terrain}) — 명중 -1`;
    case 'visibility':
      return `[시야] ${n(ev.uid)} → ${n(ev.target)} 사격 불가 (${ev.terrain}에 가려짐)`;
    case 'terrain_move':
      return `[지형] ${n(ev.uid)} 이동 제한: ${ev.notes.join(', ')}`;
    case 'cp_reset':
      return `${ev.round_no}라운드 종료 — 미사용 CP 소멸`;
    case 'charge':
      return `[돌격] ${n(ev.uid)} → ${n(ev.target)} 돌격 성공! (2D6=${ev.roll})`;
    case 'charge_failed':
      return `[돌격] ${n(ev.uid)} 돌격 실패 (2D6=${ev.roll})`;
    case 'effects':
      return `[효과] ${n(ev.uid)}: ${ev.effects.map(describeEffectKo).join('; ')}`;
    case 'defense':
      return (
        `[방어] ${n(ev.uid)}가 'Ward ${ev.ward}' 효과로 피해 ${ev.negated}점 무효화!` +
        ` (최종 피해: ${ev.final_damage})`
      );
    case 'command': {
      const CMD_KO = {
        'Rally': '랠리',
        'All-out Attack': '총공격',
        'All-out Defence': '총방어',
        'Forward to Victory': '승리를 향하여',
        'Redeploy': '재배치',
        'Covering Fire': '엄호 사격',
        'Counter-charge': '역돌격',
      };
      const DETAIL_KO = {
        'Rally': () =>
          `${ev.revived ? `모델 ${ev.revived}기 부활, ` : ''}총 ${ev.healed} 회복`,
        'All-out Attack': () => '명중 +1',
        'All-out Defence': () => '방어 +1',
        'Forward to Victory': () => '돌격 재굴림',
        'Redeploy': () => `${ev.roll}" 후퇴`,
        'Covering Fire': () => '명중 -1로 리액션 사격',
        'Counter-charge': () => `요격 돌격 (2D6=${ev.roll})`,
      };
      const detail = (DETAIL_KO[ev.command] || (() => ''))();
      return `[커맨드] ${n(ev.uid)} — '${CMD_KO[ev.command] || ev.command}'${detail ? ` (${detail}, ` : ' ('}남은 CP ${ev.cp_left})`;
    }
    case 'cp_status':
      return `${ev.side === 'player' ? '아군' : '적'} 턴 종료 — 남은 CP ${ev.cp}`;
    case 'attack': {
      const label =
        ev.kind === 'shoot' ? '사격'
        : ev.kind === 'mortal' ? '모탈'
        : ev.kind === 'spell' ? '마법'
        : '근접';
      const applied = appliedSuffixKo(ev.applied);
      if (ev.kind === 'mortal') {
        return (
          `[모탈] ${n(ev.uid)} → ${n(ev.target)}: 모탈 운드 ${ev.damage}` +
          (ev.ability ? ` (${ev.ability})` : '') +
          (ev.slain ? ` — ${n(ev.target)} 파괴!` : '')
        );
      }
      if (!ev.damage)
        return `[${label}] ${n(ev.uid)} → ${n(ev.target)}: 피해 없음${applied}`;
      return (
        `[${label}] ${n(ev.uid)} → ${n(ev.target)}: 피해 ${ev.damage}${applied}` +
        (ev.slain ? ` — ${n(ev.target)} 파괴!` : '')
      );
    }
    case 'end': {
      const w =
        ev.winner === 'player' ? '아군 승리' : ev.winner === 'enemy' ? '적 승리' : '무승부';
      return `전투 종료 — ${w} (잔존 포인트: 아군 ${ev.player_points} vs 적 ${ev.enemy_points})`;
    }
    default:
      return null; // turn/state events carry no log line
  }
}

// Returns log entries as objects so the UI can color them by category:
// [{round, category, text}]
export function buildLog(events, names, lang) {
  const lines = [];
  for (const ev of events) {
    const text = formatEvent(ev, names, lang);
    if (text) {
      lines.push({ round: ev.round, category: ev.category || 'SYSTEM', text });
    }
  }
  return lines;
}
