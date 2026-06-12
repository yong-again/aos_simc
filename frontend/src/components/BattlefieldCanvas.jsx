import { useEffect, useRef, useState } from 'react';
import { useLang } from '../i18n.jsx';
import {
  BOARD_H_IN,
  BOARD_W_IN,
  CANVAS_H,
  CANVAS_W,
  ZONE_DEPTH_IN,
  inToPx,
  pxToIn,
} from '../game/scale';

const EASE = 0.16; // per-frame easing toward the unit's true position

// Marker footprint from the warscroll base size: single-model units use
// their actual base; multi-model units grow with the square root of the
// surviving model count (footprint area ∝ models).
export function unitRadii(u) {
  const baseW = (u.base_w || 2) / 2;
  const baseH = (u.base_h || 2) / 2;
  const scale = Math.sqrt(Math.max(u.models, 1));
  const clamp = (v) => Math.min(Math.max(v, 0.45), 3.2);
  return { rw: clamp(baseW * scale), rh: clamp(baseH * scale) };
}

function tracePolygon(ctx, cx, cy, rw, rh, sides, rotation = -Math.PI / 2) {
  ctx.beginPath();
  for (let i = 0; i < sides; i++) {
    const a = rotation + (i * 2 * Math.PI) / sides;
    const x = cx + Math.cos(a) * rw;
    const y = cy + Math.sin(a) * rh;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
}

function drawBoard(ctx, deploying) {
  ctx.fillStyle = '#2e3b2e';
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.strokeStyle = 'rgba(255,255,255,0.07)';
  ctx.lineWidth = 1;
  for (let x = 0; x <= BOARD_W_IN; x += 6) {
    ctx.beginPath();
    ctx.moveTo(inToPx(x), 0);
    ctx.lineTo(inToPx(x), CANVAS_H);
    ctx.stroke();
  }
  for (let y = 0; y <= BOARD_H_IN; y += 6) {
    ctx.beginPath();
    ctx.moveTo(0, inToPx(y));
    ctx.lineTo(CANVAS_W, inToPx(y));
    ctx.stroke();
  }
  if (deploying) {
    ctx.fillStyle = 'rgba(180, 60, 60, 0.12)';
    ctx.fillRect(0, 0, CANVAS_W, inToPx(ZONE_DEPTH_IN));
    ctx.fillStyle = 'rgba(80, 140, 220, 0.14)';
    ctx.fillRect(0, CANVAS_H - inToPx(ZONE_DEPTH_IN), CANVAS_W, inToPx(ZONE_DEPTH_IN));
    ctx.strokeStyle = 'rgba(120, 170, 255, 0.6)';
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(
      0.5, CANVAS_H - inToPx(ZONE_DEPTH_IN) + 0.5, CANVAS_W - 1, inToPx(ZONE_DEPTH_IN) - 1
    );
    ctx.setLineDash([]);
  }
}

function drawUnit(ctx, u, pos, colors, selected, now) {
  const px = inToPx(pos.x);
  const py = inToPx(pos.y);
  const { rw, rh } = unitRadii(u);
  const rwp = inToPx(rw);
  const rhp = inToPx(rh);
  const color = colors[u.faction] || (u.side === 'player' ? '#4a90d9' : '#c0504d');

  ctx.save();
  if (u.alive === false) {
    // fallen units linger as fading markers
    ctx.globalAlpha = 0.18;
  }
  ctx.shadowColor = 'rgba(0,0,0,0.5)';
  ctx.shadowBlur = 4;
  ctx.fillStyle = color;
  if (selected) {
    // pulsing selection ring
    const pulse = 2 + Math.sin(now / 180) * 1.2;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = pulse;
  } else {
    ctx.strokeStyle = u.side === 'player' ? '#bcd6f5' : '#f2c1bf';
    ctx.lineWidth = 1.5;
  }

  // shape encodes unit type: WAR MACHINE = triangle, MONSTER = hexagon,
  // hero = circle/ellipse, regular unit = rectangle (warscroll base ratio)
  if (u.is_war_machine) {
    tracePolygon(ctx, px, py, rwp, rhp, 3);
    ctx.fill();
    ctx.stroke();
  } else if (u.is_monster) {
    tracePolygon(ctx, px, py, rwp, rhp, 6, 0);
    ctx.fill();
    ctx.stroke();
  } else if (u.is_hero) {
    ctx.beginPath();
    ctx.ellipse(px, py, rwp, rhp, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    // hero crown dot
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.beginPath();
    ctx.arc(px, py - rhp * 0.55, Math.min(rwp, rhp) * 0.16, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.fillRect(px - rwp, py - rhp, rwp * 2, rhp * 2);
    ctx.strokeRect(px - rwp, py - rhp, rwp * 2, rhp * 2);
  }
  ctx.restore();

  if (u.alive === false) return;

  if (u.models > 1) {
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${Math.min(inToPx(0.7), rhp * 0.9)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(u.models), px, py);
  }

  if (u.maxHealth && u.health < u.maxHealth) {
    const w = rwp * 2;
    ctx.fillStyle = '#222';
    ctx.fillRect(px - rwp, py - rhp - 6, w, 4);
    ctx.fillStyle = u.health / u.maxHealth > 0.5 ? '#6dc36d' : '#d9534f';
    ctx.fillRect(px - rwp, py - rhp - 6, (w * Math.max(u.health, 0)) / u.maxHealth, 4);
  }
}

// age: 0..1 normalized lifetime
function drawEffect(ctx, fx, age, pos) {
  const fade = 1 - age;
  switch (fx.kind) {
    case 'tracer': {
      // shooting: bright projectile line attacker -> target
      const from = pos(fx.fromUid) || fx.from;
      const to = pos(fx.toUid) || fx.to;
      if (!from || !to) return;
      const fxp = inToPx(from.x ?? from[0]);
      const fyp = inToPx(from.y ?? from[1]);
      const txp = inToPx(to.x ?? to[0]);
      const typ = inToPx(to.y ?? to[1]);
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.strokeStyle = '#ffe07a';
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 6]);
      ctx.lineDashOffset = -age * 90;
      ctx.beginPath();
      ctx.moveTo(fxp, fyp);
      ctx.lineTo(txp, typ);
      ctx.stroke();
      ctx.setLineDash([]);
      // projectile head
      const hx = fxp + (txp - fxp) * Math.min(age * 1.6, 1);
      const hy = fyp + (typ - fyp) * Math.min(age * 1.6, 1);
      ctx.fillStyle = '#fff3b8';
      ctx.beginPath();
      ctx.arc(hx, hy, 3.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      break;
    }
    case 'slash': {
      // melee: crossed slash marks over the target
      const p = pos(fx.toUid) || fx.at;
      if (!p) return;
      const cx = inToPx(p.x ?? p[0]);
      const cy = inToPx(p.y ?? p[1]);
      const len = inToPx(1.1) * (0.6 + age * 0.6);
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.strokeStyle = fx.color || '#ff8a5c';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx - len, cy - len);
      ctx.lineTo(cx + len, cy + len);
      ctx.moveTo(cx + len, cy - len);
      ctx.lineTo(cx - len, cy + len);
      ctx.stroke();
      ctx.restore();
      break;
    }
    case 'damage': {
      // floating damage number rising above the target
      const p = pos(fx.toUid) || fx.at;
      if (!p) return;
      const cx = inToPx(p.x ?? p[0]);
      const cy = inToPx(p.y ?? p[1]) - inToPx(1.4) - age * 22;
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.fillStyle = fx.miss ? '#aab4c0' : '#ffd34d';
      ctx.font = `bold ${fx.miss ? 12 : 16}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.strokeStyle = 'rgba(0,0,0,0.7)';
      ctx.lineWidth = 3;
      ctx.strokeText(fx.text, cx, cy);
      ctx.fillText(fx.text, cx, cy);
      ctx.restore();
      break;
    }
    case 'ward': {
      // ward save: protective blue ring pulsing around the defender
      const p = fx.at;
      if (!p) return;
      const cx = inToPx(p.x ?? p[0]);
      const cy = inToPx(p.y ?? p[1]);
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.strokeStyle = '#6db3f2';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(cx, cy, inToPx(1.0) + Math.sin(age * Math.PI) * inToPx(0.5), 0, Math.PI * 2);
      ctx.stroke();
      ctx.font = `${inToPx(1.0)}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('🛡️', cx, cy - inToPx(1.8));
      ctx.restore();
      break;
    }
    case 'death': {
      // expanding shockwave ring + skull
      const p = fx.at;
      if (!p) return;
      const cx = inToPx(p.x ?? p[0]);
      const cy = inToPx(p.y ?? p[1]);
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.strokeStyle = '#ff5d5d';
      ctx.lineWidth = 3 * fade;
      ctx.beginPath();
      ctx.arc(cx, cy, inToPx(0.6) + age * inToPx(2.2), 0, Math.PI * 2);
      ctx.stroke();
      ctx.font = `${inToPx(1.4)}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('💀', cx, cy - age * 8);
      ctx.restore();
      break;
    }
    case 'banner': {
      // centered phase banner
      ctx.save();
      const a = age < 0.15 ? age / 0.15 : age > 0.75 ? (1 - age) / 0.25 : 1;
      ctx.globalAlpha = a * 0.92;
      ctx.fillStyle = 'rgba(10, 12, 16, 0.65)';
      const w = CANVAS_W * 0.46;
      ctx.fillRect((CANVAS_W - w) / 2, CANVAS_H / 2 - 26, w, 52);
      ctx.fillStyle = '#f0e6c8';
      ctx.font = 'bold 22px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(fx.text, CANVAS_W / 2, CANVAS_H / 2);
      ctx.restore();
      break;
    }
    default:
      break;
  }
}

export default function BattlefieldCanvas({
  units,
  factionColors,
  deploying,
  onMoveUnit,
  onSelectUnit,
  selectedUid,
  effects = [],
}) {
  const { t } = useLang();
  const canvasRef = useRef();
  const [hover, setHover] = useState(null);
  const dragRef = useRef(null);
  const displayPosRef = useRef(new Map()); // uid -> eased {x, y}
  const stateRef = useRef({ units, factionColors, deploying, selectedUid, effects });
  stateRef.current = { units, factionColors, deploying, selectedUid, effects };

  // continuous render loop: eases unit positions and animates effects
  useEffect(() => {
    let raf;
    const tick = () => {
      const ctx = canvasRef.current?.getContext('2d');
      if (!ctx) return;
      const { units, factionColors, deploying, selectedUid, effects } = stateRef.current;
      const now = performance.now();
      const positions = displayPosRef.current;

      for (const u of units) {
        let p = positions.get(u.uid);
        if (!p) {
          p = { x: u.x, y: u.y };
          positions.set(u.uid, p);
        }
        // while dragging, follow the cursor exactly
        const k = dragRef.current === u.uid ? 1 : EASE;
        p.x += (u.x - p.x) * k;
        p.y += (u.y - p.y) * k;
      }

      drawBoard(ctx, deploying);
      const pos = (uid) => positions.get(uid);
      // dead units first so live ones draw on top
      for (const u of units)
        if (u.alive === false)
          drawUnit(ctx, u, positions.get(u.uid), factionColors, false, now);
      for (const u of units)
        if (u.alive !== false)
          drawUnit(ctx, u, positions.get(u.uid), factionColors, u.uid === selectedUid, now);

      const nowMs = Date.now();
      for (const fx of effects) {
        const age = (nowMs - fx.born) / fx.ttl;
        if (age >= 0 && age <= 1) drawEffect(ctx, fx, age, pos);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const unitAt = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const x = pxToIn(e.clientX - rect.left);
    const y = pxToIn(e.clientY - rect.top);
    const hit = [...units]
      .reverse()
      .find((u) => {
        if (u.alive === false) return false;
        const { rw, rh } = unitRadii(u);
        // elliptical hit test matching the marker footprint
        const dx = (u.x - x) / (rw * 1.15);
        const dy = (u.y - y) / (rh * 1.15);
        return dx * dx + dy * dy <= 1;
      });
    return { hit, x, y };
  };

  const onMouseDown = (e) => {
    const { hit } = unitAt(e);
    if (hit) onSelectUnit?.(hit);
    if (deploying && hit && hit.side === 'player') dragRef.current = hit.uid;
  };

  const onMouseMove = (e) => {
    const { hit, x, y } = unitAt(e);
    if (dragRef.current) {
      const cx = Math.min(Math.max(x, 1), BOARD_W_IN - 1);
      const cy = Math.min(Math.max(y, BOARD_H_IN - ZONE_DEPTH_IN + 1), BOARD_H_IN - 1);
      onMoveUnit(dragRef.current, cx, cy);
      setHover(null);
      return;
    }
    if (hit) {
      const rect = canvasRef.current.getBoundingClientRect();
      setHover({ unit: hit, left: e.clientX - rect.left + 14, top: e.clientY - rect.top + 14 });
    } else {
      setHover(null);
    }
  };

  const endDrag = () => (dragRef.current = null);

  return (
    <div className="board-wrap" style={{ width: CANVAS_W }}>
      <canvas
        ref={canvasRef}
        width={CANVAS_W}
        height={CANVAS_H}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={() => {
          endDrag();
          setHover(null);
        }}
        style={{ cursor: deploying ? 'grab' : 'pointer' }}
      />
      {hover && (
        <div className="tooltip" style={{ left: hover.left, top: hover.top }}>
          <b>{hover.unit.name}</b>
          <div>
            {hover.unit.side === 'player' ? t('yourUnit') : t('enemyUnit')} ·{' '}
            {hover.unit.models} {hover.unit.models > 1 ? t('models') : t('model')} ·{' '}
            {hover.unit.health ?? hover.unit.maxHealth} HP
          </div>
          <div className="tooltip-hint">{t('clickForWarscroll')}</div>
        </div>
      )}
    </div>
  );
}
