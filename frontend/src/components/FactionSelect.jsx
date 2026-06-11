import { useLang } from '../i18n.jsx';

// Enemy faction picker grouped by Grand Alliance, tinted with each
// faction's theme color. Descriptions come localized from the API.
const ALLIANCE_ORDER = ['Order', 'Chaos', 'Death', 'Destruction'];
const ALLIANCE_ICON = {
  Order: '🛡️',
  Chaos: '🐙',
  Death: '💀',
  Destruction: '🪓',
};

export default function FactionSelect({ factions, value, onChange, points, onPoints }) {
  const { lang, t } = useLang();
  const desc = (f) => (lang === 'ko' ? f.description_ko : f.description) || f.description;
  const allianceDesc = (f) =>
    (lang === 'ko' ? f.alliance_description_ko : f.alliance_description) ||
    f.alliance_description;

  const groups = ALLIANCE_ORDER.map((a) => ({
    alliance: a,
    items: factions.filter((f) => f.alliance === a),
  })).filter((g) => g.items.length > 0);

  const selected = factions.find((f) => f.slug === value);

  return (
    <div className="faction-select">
      <div className="panel-title">{t('chooseFaction')}</div>
      {groups.map((g) => (
        <div key={g.alliance} className="alliance-group">
          <div className="alliance-name" style={{ color: g.items[0].alliance_color }}>
            {ALLIANCE_ICON[g.alliance]} {t('grandAlliance')}: {g.alliance}
          </div>
          <div className="alliance-desc">{allianceDesc(g.items[0])}</div>
          <div className="faction-chips">
            {g.items.map((f) => (
              <button
                key={f.slug}
                className={`chip ${value === f.slug ? 'chip-active' : ''}`}
                title={desc(f)}
                style={{
                  borderColor: f.color,
                  background: value === f.slug ? f.color : 'transparent',
                }}
                onClick={() => onChange(f.slug)}
              >
                {f.name}
              </button>
            ))}
          </div>
        </div>
      ))}
      {selected && <div className="faction-desc">{desc(selected)}</div>}
      <div className="row">
        <label>
          {t('points')}:{' '}
          <select value={points} onChange={(e) => onPoints(Number(e.target.value))}>
            <option value={1000}>1000</option>
            <option value={1500}>1500</option>
            <option value={2000}>2000</option>
          </select>
        </label>
      </div>
    </div>
  );
}
