function IconSvg({ children, className = "", label = "" }) {
  const accessibility = label
    ? { role: "img", "aria-label": label }
    : { "aria-hidden": "true" };

  return (
    <svg className={`svg-icon ${className}`.trim()} viewBox="0 0 48 48" fill="none" {...accessibility}>
      {children}
    </svg>
  );
}

function CodeGlyph() {
  return (
    <>
      <path d="M18 16 10 24l8 8" />
      <path d="m30 16 8 8-8 8" />
      <path d="m27 12-6 24" />
    </>
  );
}

export function BrandIcon() {
  return (
    <IconSvg className="brand-svg" label="Code Learning">
      <path className="brand-logo-blue" d="M14 10h13L18 24l10 14H16L5 24 14 10Z" />
      <rect className="brand-logo-dark" x="31" y="10" width="13" height="6" rx="1" />
      <rect className="brand-logo-dark" x="31" y="21" width="11" height="6" rx="1" />
      <rect className="brand-logo-green" x="29" y="34" width="15" height="5" rx="1" />
    </IconSvg>
  );
}

export function ModeIcon({ type }) {
  switch (type) {
    case "analysis":
      return (
        <IconSvg className="mode-svg">
          <rect x="8" y="10" width="25" height="24" rx="6" />
          <path d="M15 18h11M15 24h8M15 30h5" />
          <circle className="svg-fill-dot" cx="32" cy="31" r="5" />
          <path d="m36 35 5 5" />
        </IconSvg>
      );
    case "code-block":
      return (
        <IconSvg className="mode-svg">
          <rect x="9" y="10" width="30" height="28" rx="7" />
          <path d="M9 20h30" />
          <path d="M18 28h12" />
          <path d="M18 34h8" />
          <circle className="svg-fill-dot" cx="16" cy="15" r="2" />
        </IconSvg>
      );
    case "code-arrange":
      return (
        <IconSvg className="mode-svg">
          <rect x="10" y="9" width="22" height="8" rx="3" />
          <rect x="16" y="21" width="22" height="8" rx="3" />
          <rect x="10" y="33" width="22" height="8" rx="3" />
          <path d="M36 11v8l4-4-4-4Z" className="svg-fill-dot" />
          <path d="M12 25H7l4 4 4-4h-3Z" className="svg-fill-dot" />
        </IconSvg>
      );
    case "auditor":
      return (
        <IconSvg className="mode-svg">
          <path d="M24 7 38 13v10c0 9-5.8 15.2-14 18-8.2-2.8-14-9-14-18V13l14-6Z" />
          <path d="m17 24 5 5 10-11" />
        </IconSvg>
      );
    case "refactoring-choice":
      return (
        <IconSvg className="mode-svg">
          <circle cx="13" cy="14" r="5" />
          <circle cx="35" cy="14" r="5" />
          <circle cx="24" cy="36" r="5" />
          <path d="M17 17c4 5 6 9 7 14" />
          <path d="M31 17c-4 5-6 9-7 14" />
          <path d="M13 19v13h6" />
        </IconSvg>
      );
    case "code-blame":
      return (
        <IconSvg className="mode-svg">
          <path d="M11 12h26" />
          <path d="M14 24h20" />
          <path d="M11 36h26" />
          <circle className="svg-fill-dot" cx="17" cy="12" r="4" />
          <circle cx="29" cy="24" r="4" />
          <path d="M37 31v8" />
          <path d="M37 42h.01" />
        </IconSvg>
      );
    case "single-file-analysis":
      return (
        <IconSvg className="mode-svg">
          <path d="M15 7h13l8 8v26H15V7Z" />
          <path d="M28 7v9h8" />
          <CodeGlyph />
        </IconSvg>
      );
    case "multi-file-analysis":
      return (
        <IconSvg className="mode-svg">
          <path d="M14 10h20v25H14z" />
          <path d="M9 15h20v25H9z" />
          <path d="M19 22h8M19 29h6" />
          <circle className="svg-fill-dot" cx="33" cy="13" r="3" />
        </IconSvg>
      );
    case "fullstack-analysis":
      return (
        <IconSvg className="mode-svg">
          <path d="m24 7 16 8-16 8-16-8 16-8Z" />
          <path d="m8 24 16 8 16-8" />
          <path d="m8 33 16 8 16-8" />
          <circle className="svg-fill-dot" cx="24" cy="15" r="3" />
        </IconSvg>
      );
    default:
      return (
        <IconSvg className="mode-svg">
          <CodeGlyph />
        </IconSvg>
      );
  }
}
