import { useState } from 'react';

// Collapsible tree preview of the parsed roster JSON.
function Node({ name, value, depth }) {
  const [open, setOpen] = useState(depth < 3);
  const indent = { paddingLeft: depth * 14 };

  if (value !== null && typeof value === 'object') {
    const isArray = Array.isArray(value);
    const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value);
    if (name === 'warscroll' && value && depth > 0 && !open) {
      // keep big merged warscroll objects collapsed by default
    }
    return (
      <div>
        <div className="tree-row tree-branch" style={indent} onClick={() => setOpen(!open)}>
          <span className="tree-caret">{open ? '▾' : '▸'}</span>
          <span className="tree-key">{name}</span>
          <span className="tree-meta">{isArray ? `[${value.length}]` : '{…}'}</span>
        </div>
        {open &&
          entries.map(([k, v]) => (
            <Node key={k} name={String(k)} value={v} depth={depth + 1} />
          ))}
      </div>
    );
  }

  return (
    <div className="tree-row" style={indent}>
      <span className="tree-key">{name}: </span>
      <span className={`tree-val tree-${typeof value}`}>
        {value === null ? 'null' : JSON.stringify(value)}
      </span>
    </div>
  );
}

export default function JsonTree({ data, title }) {
  if (!data) return null;
  return (
    <div className="json-tree">
      {title && <div className="panel-title">{title}</div>}
      <Node name="roster" value={data} depth={0} />
    </div>
  );
}
