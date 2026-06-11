import { useRef, useState } from 'react';
import { useLang } from '../i18n.jsx';

const SAMPLE = `My Stormcast Army (2000 points)
Stormcast Eternals

General's Regiment
Lord-Aquilor (140) - General
  Liberators (110)
  Vanquishers (100)

Regiment 1
Lord-Vigilant on Gryph-stalker (170)
  Prosecutors (150)
`;

// Roster paste / .txt upload input, as required by the spec.
// Reused for both the player's and the opponent's roster.
export default function RosterInput({ onParse, parsing, title }) {
  const { t } = useLang();
  const [text, setText] = useState('');
  const fileRef = useRef();

  const handleFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setText(String(reader.result));
    reader.readAsText(file);
  };

  return (
    <div className="roster-input">
      <div className="panel-title">{title ?? t('pasteYourRoster')}</div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t('rosterPlaceholder')}
        rows={14}
        spellCheck={false}
      />
      <div className="row">
        <button onClick={() => fileRef.current.click()}>{t('uploadTxt')}</button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,text/plain"
          style={{ display: 'none' }}
          onChange={handleFile}
        />
        <button onClick={() => setText(SAMPLE)}>{t('loadSample')}</button>
        <button
          className="primary"
          disabled={!text.trim() || parsing}
          onClick={() => onParse(text)}
        >
          {parsing ? t('parsing') : t('parseRoster')}
        </button>
      </div>
    </div>
  );
}
