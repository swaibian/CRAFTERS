/**
 * ToolPicker (TC-A-01): app cards; select arms the dropzone.
 *
 * Why (story #1): the user picks which Craft app the file opens in before
 * dropping. Pilot apps enabled; the rest render disabled "soon".
 */

export interface AppDef {
  id: string;
  name: string;
  enabled: boolean;
  hint: string;
}

export const APPS: AppDef[] = [
  { id: 'photocraft', name: 'PhotoCraft', enabled: true, hint: 'Raster images' },
  { id: 'gridcraft', name: 'GridCraft', enabled: true, hint: 'Spreadsheets & data' },
  { id: 'pdfcraft', name: 'PdfCraft', enabled: true, hint: 'PDF documents' },
  { id: 'vectorcraft', name: 'VectorCraft', enabled: false, hint: 'Soon' },
  { id: 'filmcraft', name: 'FilmCraft', enabled: false, hint: 'Soon' },
  { id: 'lightcraft', name: 'LightCraft', enabled: false, hint: 'Soon' },
  { id: 'effectcraft', name: 'EffectCraft', enabled: false, hint: 'Soon' },
  { id: 'designcraft', name: 'DesignCraft', enabled: false, hint: 'Soon' },
  { id: 'wordcraft', name: 'WordCraft', enabled: false, hint: 'Soon' },
  { id: 'soundcraft', name: 'SoundCraft', enabled: false, hint: 'Soon' },
  { id: 'deckcraft', name: 'DeckCraft', enabled: false, hint: 'Soon' },
  { id: 'cadcraft', name: 'CADCraft', enabled: false, hint: 'Soon' },
];

export function ToolPicker({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (appId: string) => void;
}) {
  return (
    <div className="picker" role="radiogroup" aria-label="Select Craft app">
      {APPS.map((app) => (
        <button
          key={app.id}
          type="button"
          role="radio"
          aria-checked={selected === app.id}
          disabled={!app.enabled}
          title={app.enabled ? app.hint : `${app.name} — coming soon`}
          className={selected === app.id ? 'app-card selected' : 'app-card'}
          onClick={() => onSelect(app.id)}
        >
          <span className="app-name">{app.name}</span>
          <span className="app-hint">{app.enabled ? app.hint : 'soon'}</span>
        </button>
      ))}
    </div>
  );
}
