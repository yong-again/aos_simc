import { useEffect, useState } from 'react';
import { getWarscrollKo } from '../api';
import { useLang } from '../i18n.jsx';

// client-side cache: "slug:id" -> translated abilities (server caches too)
const koCache = new Map();

// Side panel showing the selected unit's full warscroll details.
// In Korean mode, ability text is translated on demand via the backend
// (Gemini, cached) and shown in place of the English rules text.
export default function UnitPanel({ unit, warscroll, color }) {
  const { lang, t } = useLang();
  const [koAbilities, setKoAbilities] = useState(null);
  const [koLoading, setKoLoading] = useState(false);

  const ws = warscroll;
  const cacheKey = ws ? `${ws.faction_slug}:${ws.id}` : null;

  useEffect(() => {
    setKoAbilities(null);
    if (lang !== 'ko' || !ws || !ws.abilities?.length) return;
    if (koCache.has(cacheKey)) {
      setKoAbilities(koCache.get(cacheKey));
      return;
    }
    let cancelled = false;
    setKoLoading(true);
    getWarscrollKo(ws.faction_slug, ws.id)
      .then((res) => {
        koCache.set(cacheKey, res.abilities);
        if (!cancelled) setKoAbilities(res.abilities);
      })
      .catch(() => {}) // fall back to English silently
      .finally(() => !cancelled && setKoLoading(false));
    return () => {
      cancelled = true;
    };
  }, [lang, cacheKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!unit) {
    return (
      <div className="unit-panel">
        <div className="panel-title">{t('unitDetails')}</div>
        <p className="muted">{t('unitHint')}</p>
      </div>
    );
  }

  const abilityAt = (i) => {
    const en = ws.abilities[i];
    const ko = koAbilities?.[i];
    if (lang === 'ko' && ko) {
      return { name: ko.name, original: en.name, timing: ko.timing || en.timing,
               declare: ko.declare, effect: ko.effect || en.effect };
    }
    return { name: en.name, timing: en.timing, declare: en.declare, effect: en.effect };
  };

  return (
    <div className="unit-panel">
      <div className="panel-title" style={{ color }}>
        {unit.name}
      </div>
      <div className="muted">
        {unit.faction} · {unit.side === 'player' ? t('yourArmy') : t('aiOpponent')} ·{' '}
        {unit.points} {t('pts')}
      </div>
      {ws && (
        <>
          <div className="statline">
            <div><span>{t('move')}</span>{ws.move || '-'}</div>
            <div><span>{t('health')}</span>{ws.health || '-'}</div>
            <div><span>{t('save')}</span>{ws.save || '-'}</div>
            <div><span>{t('control')}</span>{ws.control || '-'}</div>
          </div>
          {[[t('rangedWeapons'), ws.ranged_weapons], [t('meleeWeapons'), ws.melee_weapons]].map(
            ([label, weapons]) =>
              weapons?.length > 0 && (
                <div key={label}>
                  <div className="section-title">{label}</div>
                  <table className="weapons">
                    <thead>
                      <tr>
                        <th>Name</th><th>Rng</th><th>Atk</th><th>Hit</th>
                        <th>Wnd</th><th>Rnd</th><th>Dmg</th>
                      </tr>
                    </thead>
                    <tbody>
                      {weapons.map((w) => (
                        <tr key={w.name}>
                          <td>{w.name}</td>
                          <td>{w.range || '-'}</td>
                          <td>{w.attacks}</td>
                          <td>{w.hit}</td>
                          <td>{w.wound}</td>
                          <td>{w.rend || '-'}</td>
                          <td>{w.damage}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
          )}
          {ws.abilities?.length > 0 && (
            <div>
              <div className="section-title">
                {t('abilities')}
                {koLoading && <span className="muted"> (번역 중…)</span>}
              </div>
              {ws.abilities.map((_, i) => {
                const a = abilityAt(i);
                return (
                  <div key={i} className="ability">
                    <b>{a.name}</b>
                    {a.original && (
                      <span className="ability-original"> ({a.original})</span>
                    )}
                    {a.timing && <span className="ability-timing"> — {a.timing}</span>}
                    {a.declare && (
                      <div className="ability-effect">
                        <b>{lang === 'ko' ? '선언' : 'Declare'}:</b> {a.declare}
                      </div>
                    )}
                    <div className="ability-effect">{a.effect}</div>
                  </div>
                );
              })}
            </div>
          )}
          {ws.keywords?.length > 0 && (
            <div className="keywords">
              {ws.keywords.map((k) => (
                <span key={k} className="kw">{k}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
