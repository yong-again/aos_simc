import { useEffect, useMemo, useRef, useState } from 'react';
import './App.css';
import {
  generateRoster,
  getFactions,
  parseRoster,
  runSimulation,
  setupBattle,
} from './api';
import BattlefieldCanvas from './components/BattlefieldCanvas';
import FactionSelect from './components/FactionSelect';
import JsonTree from './components/JsonTree';
import RosterInput from './components/RosterInput';
import UnitPanel from './components/UnitPanel';
import { buildLog, formatEvent } from './game/logText';
import { useLang } from './i18n.jsx';

let fxId = 0;

// Collects every warscroll embedded in a merged roster, keyed by unit name.
function warscrollIndex(...rosters) {
  const idx = {};
  for (const r of rosters) {
    if (!r) continue;
    const entries = [
      ...(r.regiments || []).flatMap((reg) => [reg.hero, ...(reg.units || [])]),
      ...(r.auxiliaries || []),
    ];
    for (const e of entries) if (e?.warscroll) idx[e.name] = e.warscroll;
  }
  return idx;
}

export default function App() {
  const { lang, setLang, t } = useLang();
  const [stage, setStage] = useState('setup'); // setup | deploy | battle | result
  const [factions, setFactions] = useState([]);
  const [error, setError] = useState('');

  // setup stage
  const [playerRoster, setPlayerRoster] = useState(null);
  const [enemyRoster, setEnemyRoster] = useState(null);
  const [enemyFaction, setEnemyFaction] = useState('');
  const [enemySource, setEnemySource] = useState('generate'); // generate | paste
  const [points, setPoints] = useState(2000);
  const [busy, setBusy] = useState('');

  // battle stage
  const [units, setUnits] = useState([]);
  const [selected, setSelected] = useState(null);
  const [result, setResult] = useState(null);
  const [mode, setMode] = useState('A');
  const [phaseLabel, setPhaseLabel] = useState('');
  const [roundNo, setRoundNo] = useState(0);
  const [feed, setFeed] = useState([]);
  const [effects, setEffects] = useState([]);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1); // playback speed multiplier
  const eventIdxRef = useRef(0);
  const playingRef = useRef(false);

  useEffect(() => {
    getFactions().then(setFactions).catch((e) => setError(String(e.message)));
  }, []);

  const factionColors = useMemo(
    () => Object.fromEntries(factions.map((f) => [f.name, f.color])),
    [factions]
  );
  const wsIndex = useMemo(
    () => warscrollIndex(playerRoster, enemyRoster),
    [playerRoster, enemyRoster]
  );
  const unitNames = useMemo(() => {
    const m = {};
    for (const u of result?.units || []) m[u.uid] = u.name;
    for (const u of units) m[u.uid] = u.name;
    return m;
  }, [result, units]);

  const pushEffects = (newFx) => {
    const now = Date.now();
    setEffects((prev) => [
      ...prev.filter((fx) => now - fx.born < fx.ttl),
      // effect lifetimes shrink with playback speed so they don't pile up
      ...newFx.map((fx) => ({ id: ++fxId, born: now, ...fx, ttl: fx.ttl / speed })),
    ]);
  };

  const guard = async (label, fn) => {
    setBusy(label);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(String(e.message));
    } finally {
      setBusy('');
    }
  };

  const handleParse = (text) =>
    guard('parse', async () => setPlayerRoster(await parseRoster(text)));

  const handleParseEnemy = (text) =>
    guard('parseEnemy', async () => setEnemyRoster(await parseRoster(text)));

  const handleGenerate = () =>
    guard('generate', async () =>
      setEnemyRoster(await generateRoster(enemyFaction, points))
    );

  const toDeployment = () =>
    guard('setup', async () => {
      const setup = await setupBattle(playerRoster, enemyRoster);
      setUnits(
        setup.units.map((u) => ({
          ...u,
          maxHealth: u.models * u.health_per_model,
          health: u.models * u.health_per_model,
          alive: true,
        }))
      );
      setStage('deploy');
    });

  const moveUnit = (uid, x, y) =>
    setUnits((us) => us.map((u) => (u.uid === uid ? { ...u, x, y } : u)));

  const startBattle = (chosenMode) =>
    guard('simulate', async () => {
      const deployment = units
        .filter((u) => u.side === 'player')
        .map((u) => ({ uid: u.uid, x: u.x, y: u.y }));
      const res = await runSimulation(playerRoster, enemyRoster, deployment);
      setResult(res);
      setMode(chosenMode);
      setFeed([]);
      eventIdxRef.current = 0;
      if (chosenMode === 'B') {
        setStage('result');
      } else {
        setStage('battle');
        setRoundNo(0);
        setPhaseLabel(t('deployment'));
      }
    });

  // ---- Mode A playback ------------------------------------------------
  const applyEvent = (ev) => {
    switch (ev.type) {
      case 'round':
        setRoundNo(ev.round_no);
        setPhaseLabel(
          `${t('round')} ${ev.round_no} — ${t('firstLabel')}: ${
            ev.first === 'player' ? t('your') : t('enemy')
          }`
        );
        break;
      case 'turn':
        setPhaseLabel(ev.side === 'player' ? t('yourTurn') : t('enemyTurn'));
        break;
      case 'phase': {
        const label = `${ev.side === 'player' ? t('your') : t('enemy')} ${
          t(`phase_${ev.phase}`) || ev.phase
        }`;
        setPhaseLabel(label);
        pushEffects([{ kind: 'banner', text: label, ttl: 1100 }]);
        break;
      }
      case 'move':
      case 'charge':
        setUnits((us) =>
          us.map((u) => (u.uid === ev.uid ? { ...u, x: ev.to[0], y: ev.to[1] } : u))
        );
        break;
      case 'retreat':
        // falls back out of combat and pays D3 mortal damage
        setUnits((us) =>
          us.map((u) =>
            u.uid === ev.uid
              ? {
                  ...u,
                  x: ev.to[0],
                  y: ev.to[1],
                  health: Math.max(0, u.health - (ev.damage || 0)),
                  alive: !ev.slain,
                }
              : u
          )
        );
        break;
      case 'attack':
        if (ev.damage > 0) {
          setUnits((us) =>
            us.map((u) =>
              u.uid === ev.target
                ? {
                    ...u,
                    health: Math.max(0, u.health - ev.damage),
                    alive: !ev.slain,
                  }
                : u
            )
          );
        }
        break;
      case 'state':
        setUnits((us) =>
          us.map((u) => {
            const s = ev.units.find((x) => x.uid === u.uid);
            return s ? { ...u, ...s } : u;
          })
        );
        break;
      case 'miscast':
        if (ev.damage > 0) {
          setUnits((us) =>
            us.map((u) =>
              u.uid === ev.uid
                ? { ...u, health: Math.max(0, u.health - ev.damage), alive: !ev.slain }
                : u
            )
          );
        }
        break;
      case 'defense':
        setUnits((current) => {
          const target = current.find((u) => u.uid === ev.uid);
          if (target) {
            pushEffects([
              { kind: 'ward', at: { x: target.x, y: target.y }, ttl: 700 },
            ]);
          }
          return current;
        });
        break;
      case 'command':
        // Rally heals: green floating number + health restore
        if (ev.healed > 0) {
          setUnits((current) => {
            const target = current.find((u) => u.uid === ev.uid);
            if (target) {
              pushEffects([
                {
                  kind: 'damage', at: { x: target.x, y: target.y },
                  text: `+${ev.healed}`, color: '#6dc36d', ttl: 900,
                },
              ]);
            }
            return current.map((u) =>
              u.uid === ev.uid
                ? { ...u, health: Math.min(u.maxHealth, u.health + ev.healed) }
                : u
            );
          });
        }
        break;
      case 'end':
        setPhaseLabel(t('battleOver'));
        break;
      default:
        break;
    }
    const line = formatEvent(ev, unitNames, lang);
    if (line) {
      const cat = ev.category || 'SYSTEM';
      const text = cat === 'PHASE' ? line : `[R${ev.round}] ${line}`;
      setFeed((f) => [...f.slice(-60), { cat, text }]);
    }

    // visual effects for attacks
    if (ev.type === 'attack') {
      setUnits((current) => {
        const target = current.find((u) => u.uid === ev.target);
        if (target) {
          const fx = [];
          if (ev.kind === 'shoot') {
            fx.push({ kind: 'tracer', fromUid: ev.uid, toUid: ev.target, ttl: 650 });
          } else if (ev.kind === 'mortal' || ev.kind === 'spell') {
            // mortal wounds: purple arcane slash, no save possible
            fx.push({
              kind: 'slash', toUid: ev.target, color: '#c084fc',
              at: { x: target.x, y: target.y }, ttl: 600,
            });
          } else {
            fx.push({ kind: 'slash', toUid: ev.target, at: { x: target.x, y: target.y }, ttl: 500 });
          }
          fx.push({
            kind: 'damage',
            toUid: ev.target,
            at: { x: target.x, y: target.y },
            text: ev.damage > 0 ? `-${ev.damage}` : 'MISS',
            miss: !ev.damage,
            ttl: 900,
          });
          if (ev.slain) {
            fx.push({ kind: 'death', at: { x: target.x, y: target.y }, ttl: 900 });
          }
          pushEffects(fx);
        }
        return current;
      });
    }
  };

  const stepEvents = (count = 1, untilPhase = false) => {
    const events = result?.events || [];
    let applied = 0;
    while (eventIdxRef.current < events.length) {
      const ev = events[eventIdxRef.current];
      if (untilPhase && applied > 0 && (ev.type === 'phase' || ev.type === 'round')) break;
      applyEvent(ev);
      eventIdxRef.current += 1;
      applied += 1;
      if (!untilPhase && applied >= count) break;
    }
    if (eventIdxRef.current >= events.length) {
      setPlaying(false);
      playingRef.current = false;
    }
  };

  useEffect(() => {
    playingRef.current = playing;
    if (!playing) return;
    const timer = setInterval(() => {
      if (!playingRef.current) return;
      stepEvents(1);
    }, 550 / speed);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, result, speed]);

  const selectedWarscroll = selected ? wsIndex[selected.name] : null;
  const selectedColor = selected ? factionColors[selected.faction] : undefined;

  // ---- render ----------------------------------------------------------
  return (
    <div className="app">
      <header>
        <h1>{t('appTitle')}</h1>
        <button onClick={() => setLang(lang === 'ko' ? 'en' : 'ko')}>
          {lang === 'ko' ? 'English' : '한국어'}
        </button>
        {stage !== 'setup' && (
          <button onClick={() => window.location.reload()}>{t('newBattle')}</button>
        )}
      </header>
      {error && <div className="error">{error}</div>}

      {stage === 'setup' && (
        <div className="setup-grid">
          <div className="col">
            <RosterInput
              title={t('pasteYourRoster')}
              onParse={handleParse}
              parsing={busy === 'parse'}
            />
            {playerRoster && (
              <JsonTree data={playerRoster} title={t('parsedPreview')} />
            )}
          </div>
          <div className="col">
            <div className="row source-toggle">
              <button
                className={enemySource === 'generate' ? 'primary' : ''}
                onClick={() => setEnemySource('generate')}
              >
                {t('generateWithAI')}
              </button>
              <button
                className={enemySource === 'paste' ? 'primary' : ''}
                onClick={() => setEnemySource('paste')}
              >
                {t('pasteOpponent')}
              </button>
            </div>
            {enemySource === 'generate' ? (
              <>
                <FactionSelect
                  factions={factions}
                  value={enemyFaction}
                  onChange={setEnemyFaction}
                  points={points}
                  onPoints={setPoints}
                />
                <button
                  className="primary"
                  disabled={!enemyFaction || busy === 'generate'}
                  onClick={handleGenerate}
                >
                  {busy === 'generate' ? t('generating') : t('generateRoster')}
                </button>
              </>
            ) : (
              <RosterInput
                title={t('pasteOpponentRoster')}
                onParse={handleParseEnemy}
                parsing={busy === 'parseEnemy'}
              />
            )}
            {enemyRoster && (
              <JsonTree data={enemyRoster} title={t('opponentRoster')} />
            )}
            <button
              className="primary big"
              disabled={!playerRoster || !enemyRoster || busy === 'setup'}
              onClick={toDeployment}
            >
              {t('proceedDeploy')}
            </button>
          </div>
        </div>
      )}

      {(stage === 'deploy' || stage === 'battle') && (
        <div className="battle-grid">
          <div>
            {stage === 'deploy' && (
              <div className="bar">
                <b>{t('deployment')}</b> — {t('deployHint')}
                <button
                  className="primary"
                  disabled={busy === 'simulate'}
                  onClick={() => startBattle('A')}
                >
                  {t('modeA')}
                </button>
                <button
                  className="primary"
                  disabled={busy === 'simulate'}
                  onClick={() => startBattle('B')}
                >
                  {t('modeB')}
                </button>
              </div>
            )}
            {stage === 'battle' && (
              <div className="bar">
                <b>{phaseLabel}</b>
                <span className="muted">{t('round')} {roundNo}/5</span>
                <button onClick={() => setPlaying((p) => !p)}>
                  {playing ? t('pause') : t('play')}
                </button>
                <label className="speed-control">
                  {t('speed')}{' '}
                  <select
                    value={speed}
                    onChange={(e) => setSpeed(Number(e.target.value))}
                  >
                    <option value={0.5}>0.5×</option>
                    <option value={1}>1×</option>
                    <option value={2}>2×</option>
                    <option value={4}>4×</option>
                  </select>
                </label>
                <button onClick={() => stepEvents(1)}>{t('step')}</button>
                <button onClick={() => stepEvents(0, true)}>{t('nextPhase')}</button>
                <button
                  onClick={() => {
                    setPlaying(false);
                    setStage('result');
                  }}
                >
                  {t('skipToResult')}
                </button>
              </div>
            )}
            <BattlefieldCanvas
              units={units}
              factionColors={factionColors}
              deploying={stage === 'deploy'}
              onMoveUnit={moveUnit}
              onSelectUnit={setSelected}
              selectedUid={selected?.uid}
              effects={effects}
            />
            {stage === 'battle' && (
              <div className="feed">
                {feed.slice(-8).map((entry, i) => (
                  <div key={i} className={`log-line log-${entry.cat}`}>
                    {entry.text}
                  </div>
                ))}
              </div>
            )}
          </div>
          <UnitPanel unit={selected} warscroll={selectedWarscroll} color={selectedColor} />
        </div>
      )}

      {stage === 'result' && result && (
        <div className="result">
          <h2>
            {result.winner === 'player'
              ? t('victory')
              : result.winner === 'enemy'
              ? t('defeat')
              : t('draw')}
          </h2>
          <p>{t('battleLasted', result.rounds_played)}</p>
          <div className="result-grid">
            {['player', 'enemy'].map((side) => (
              <div key={side} className="col">
                <div className="panel-title">
                  {side === 'player' ? t('yourSurvivors') : t('enemySurvivors')}
                </div>
                {result.survivors[side].length === 0 && (
                  <p className="muted">{t('wipedOut')}</p>
                )}
                <ul>
                  {result.survivors[side].map((u) => (
                    <li key={u.uid}>
                      {u.name} — {u.models} {t('models')}, {u.health} HP
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="panel-title">{t('battleLog')}</div>
          <div className="battle-log">
            {buildLog(result.events, unitNames, lang).map((e, i) => (
              <div key={i} className={`log-line log-${e.category}`}>
                {e.category === 'PHASE' ? e.text : `[R${e.round}] ${e.text}`}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
